"""Pipeline orchestration (FR-130).

Wires the whole RFQ-to-quote path: parse -> validate -> resolve customer -> retrieve + fuse + select
-> assemble -> critic -> render. The model appears at exactly two points (extraction and catalog
selection); every number and every gate between them is deterministic code.
"""

from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal

from pydantic import BaseModel, Field

from .agents.matcher import select_sku
from .agents.parser import extract_text_rfq
from .agents.planner import QuotePlan
from .agents.reviewer import WORD_CAP, review_note
from .agents.vision import extract_image_rfq, extract_scanned_rfq
from .config.models import (
    MODEL_CRITIC,
    MODEL_EMBED,
    MODEL_PARSER_TEXT,
    MODEL_PARSER_VISION,
    MODEL_PLANNER,
)
from .config.settings import Settings
from .memory.embedding import embed_text
from .memory.recall import recall_episodes
from .memory.sop import retrieve_terms
from .memory.store import MemoryFacade
from .models import (
    BilingualText,
    CatalogProduct,
    CriticReport,
    CustomerProfile,
    DocType,
    EpisodicRecall,
    LineSource,
    MatchResult,
    MatchStatus,
    PlanRecord,
    Quote,
    QuoteTerms,
    RFQExtraction,
    new_ulid,
)
from .obs.otel import OP_CHAT, OP_EMBEDDINGS, OP_EXECUTE_TOOL
from .obs.trace import TraceDocument, Tracer
from .parsing import parse_excel, validation_reasons
from .parsing.pdf import extract_pdf_text, is_scanned
from .pricing import vat_policy_note
from .quote import (
    AssemblyLine,
    assemble_quote,
    format_quote_number,
    lead_time_lines,
    run_critic,
)
from .quote.render import render_html
from .tools import build_match_result, fuse_candidates, resolve_customer
from .tools.customer import CustomerResolution

TOP_K = 8  # FR-042: vector_search top_k=8

# FR-048 landed, so the *pipeline* no longer uses these: the terms on a real quote are retrieved
# from the `sop` tenant by what is being quoted (memory/sop.py). These remain as the offline default
# for the eval harness and the unit tests, which run without a memory store - and as the sentences
# memory/sop.py falls back to when the tenant is empty.
DEFAULT_TERMS = QuoteTerms(
    payment=BilingualText(
        vi="Thanh toán 100% trong vòng 30 ngày kể từ ngày nhận hàng.",
        en="100% payment within 30 days of delivery.",
    ),
    delivery=BilingualText(
        vi="Giao hàng trong vòng 7 ngày làm việc.", en="Delivery within 7 working days."
    ),
    warranty=BilingualText(
        vi="Bảo hành chính hãng 12 tháng.", en="12 months manufacturer warranty."
    ),
)
DEFAULT_NOTES = BilingualText(
    vi="Báo giá do QuoteMind lập, đã được kiểm tra số học tự động.",
    en="Quotation prepared by QuoteMind and automatically arithmetic-checked.",
)

_STATUS_TO_SOURCE = {
    MatchStatus.MATCHED: LineSource.MATCHED,
    MatchStatus.NEEDS_CONFIRMATION: LineSource.SUBSTITUTED,
}


class PipelineResult(BaseModel):
    """What one RFQ produced: the quote if it got that far, else the clarification reasons."""

    extraction: RFQExtraction
    matches: list[MatchResult] = Field(default_factory=list)
    resolution: CustomerResolution | None = None
    quote: Quote | None = None
    critic: CriticReport | None = None
    html: str | None = None
    clarification_reasons: list[str] = Field(default_factory=list)
    trace: TraceDocument | None = None
    plan: PlanRecord | None = None  # FR-131
    episodic: list[EpisodicRecall] = Field(default_factory=list)  # FR-045
    episodic_truncated: bool = False  # FR-049: the budget dropped something


def _recall_query(extraction: RFQExtraction) -> str:
    """What this RFQ is *about*, as one string, for the episodic vector search (FR-045)."""
    parts = [extraction.buyer.company or ""]
    parts.extend(line.description_normalized for line in extraction.lines)
    return " ".join(part for part in parts if part).strip()


def _customer_block(resolution: CustomerResolution, extraction: RFQExtraction) -> dict[str, object]:
    if resolution.profile is not None:
        profile = resolution.profile
        return {
            "name": profile.name,
            "mst": profile.mst,
            "address": profile.address,
            "contact": profile.contact,
            # Carried so dispatch (FR-092) knows where to send without re-reading the tenant.
            "email": profile.emails[0] if profile.emails else None,
        }
    buyer = extraction.buyer
    return {
        "name": buyer.company or "Khách hàng mới / New customer",
        "mst": buyer.mst,
        "contact": buyer.contact,
        "email": buyer.email,
    }


async def _match_line(
    description: str,
    facade: MemoryFacade,
    settings: Settings,
    line_ref: int,
    tracer: Tracer,
) -> tuple[MatchResult, dict[str, CatalogProduct]]:
    """Retrieve (vector + full text), fuse deterministically, let the model pick, then band it."""
    with tracer.step("CatalogMatcher", "embed", model=MODEL_EMBED, operation=OP_EMBEDDINGS) as step:
        query_vector = embed_text(description, settings, usage=step)
        step.note(f"embedded line {line_ref}")

    with tracer.step(
        "CatalogMatcher", "retrieve", tool="vector_search", operation=OP_EXECUTE_TOOL
    ) as step:
        vector_hits = facade.search_catalog_vector(query_vector, top_k=TOP_K)
        step.memory([product.sku for product, _ in vector_hits])
        step.note(f"{len(vector_hits)} vector candidates")

    with tracer.step(
        "CatalogMatcher", "retrieve", tool="full_text_search", operation=OP_EXECUTE_TOOL
    ) as step:
        text_hits = facade.search_catalog_text(description, limit=TOP_K)
        step.memory([product.sku for product, _ in text_hits])
        step.note(f"{len(text_hits)} full-text candidates")

    products: dict[str, CatalogProduct] = {}
    for product, _ in [*vector_hits, *text_hits]:
        products.setdefault(product.sku, product)

    fused = fuse_candidates(
        [product.sku for product, _ in vector_hits], [product.sku for product, _ in text_hits]
    )

    with tracer.step("CatalogMatcher", "select", model=MODEL_PLANNER) as step:
        selection = await select_sku(
            description, [products[sku] for sku in fused], settings, usage=step
        )
        step.note(f"selected {selection.sku or 'none'} @ {selection.confidence:.2f}")
        step.content(prompt=description, response=selection.model_dump_json())

    match = build_match_result(
        line_ref,
        fused,
        selection.sku,
        selection.confidence,
        specs_conflict=selection.specs_conflict,
    )
    return match, products


async def quote_from_text(
    text: str,
    *,
    settings: Settings,
    facade: MemoryFacade,
    seller_block: dict[str, object],
    sequence: int,
    on_date: date_type | None = None,
    customer_email: str | None = None,
    customer_hint: str | None = None,
    with_usd: bool = False,
    tracer: Tracer | None = None,
) -> PipelineResult:
    """FR-130: run one RFQ text end to end and return the quote (or why it needs clarification)."""
    trace = tracer or Tracer(quote_id="")  # tracing is always on; persistence is the caller's call

    with trace.step("DocumentParser", "parse", model=MODEL_PARSER_TEXT) as step:
        extraction = await extract_text_rfq(text, settings, usage=step)
        step.note(f"extracted {len(extraction.lines)} line(s)")
        step.content(prompt=text, response=extraction.model_dump_json())

    return await quote_from_extraction(
        extraction,
        settings=settings,
        facade=facade,
        seller_block=seller_block,
        sequence=sequence,
        on_date=on_date,
        customer_email=customer_email,
        customer_hint=customer_hint,
        with_usd=with_usd,
        tracer=trace,
    )


async def quote_from_excel(
    data: bytes,
    *,
    settings: Settings,
    facade: MemoryFacade,
    seller_block: dict[str, object],
    sequence: int,
    on_date: date_type | None = None,
    customer_email: str | None = None,
    customer_hint: str | None = None,
    with_usd: bool = False,
    tracer: Tracer | None = None,
) -> PipelineResult:
    """FR-035 + FR-130: a spreadsheet RFQ. The extraction is deterministic - no model, no cost."""
    trace = tracer or Tracer(quote_id="")
    with trace.step("DocumentParser", "parse", tool="parse_excel") as step:
        extraction = parse_excel(data)
        step.note(f"extracted {len(extraction.lines)} line(s) from the sheet")

    return await quote_from_extraction(
        extraction,
        settings=settings,
        facade=facade,
        seller_block=seller_block,
        sequence=sequence,
        on_date=on_date,
        customer_email=customer_email,
        customer_hint=customer_hint,
        with_usd=with_usd,
        doc_type=DocType.EXCEL,
        tracer=trace,
    )


async def quote_from_pdf(
    data: bytes,
    *,
    settings: Settings,
    facade: MemoryFacade,
    seller_block: dict[str, object],
    sequence: int,
    on_date: date_type | None = None,
    customer_email: str | None = None,
    customer_hint: str | None = None,
    with_usd: bool = False,
    tracer: Tracer | None = None,
) -> PipelineResult:
    """FR-031/032 + FR-130: a PDF, digital or scanned.

    Digital: the text layer is lifted out and the normal text path runs - no model, no cost.
    Scanned: the pages are rasterised and read by the vision model. Same RFQExtraction either way,
    so everything downstream is identical and neither channel can develop its own idea of a price.
    """
    trace = tracer or Tracer(quote_id="")

    # A scanned PDF has pages but no text layer. Handing it to the text parser would produce a
    # confidently empty quote, so the two are routed apart here rather than papered over.
    if is_scanned(data):
        with trace.step(
            "DocumentParser", "parse", model=MODEL_PARSER_VISION, operation=OP_CHAT
        ) as step:
            extraction = await extract_scanned_rfq(data, settings, usage=step)
            step.note(f"OCR read {len(extraction.lines)} line(s) from the scan")

        return await quote_from_extraction(
            extraction,
            settings=settings,
            facade=facade,
            seller_block=seller_block,
            sequence=sequence,
            on_date=on_date,
            customer_email=customer_email,
            customer_hint=customer_hint,
            with_usd=with_usd,
            doc_type=DocType.PDF_SCAN,
            tracer=trace,
        )

    with trace.step("DocumentParser", "extract", tool="extract_pdf_text") as step:
        text = extract_pdf_text(data)
        step.note(f"{len(text)} characters of embedded text")

    return await quote_from_text(
        text,
        settings=settings,
        facade=facade,
        seller_block=seller_block,
        sequence=sequence,
        on_date=on_date,
        customer_email=customer_email,
        customer_hint=customer_hint,
        with_usd=with_usd,
        tracer=trace,
    )


async def quote_from_image(
    data: bytes,
    *,
    settings: Settings,
    facade: MemoryFacade,
    seller_block: dict[str, object],
    sequence: int,
    on_date: date_type | None = None,
    customer_email: str | None = None,
    customer_hint: str | None = None,
    with_usd: bool = False,
    tracer: Tracer | None = None,
) -> PipelineResult:
    """FR-033: a photographed or screenshotted RFQ. One page, read by the same vision path."""
    trace = tracer or Tracer(quote_id="")

    with trace.step(
        "DocumentParser", "parse", model=MODEL_PARSER_VISION, operation=OP_CHAT
    ) as step:
        extraction = await extract_image_rfq(data, settings, usage=step)
        step.note(f"OCR read {len(extraction.lines)} line(s) from the image")

    return await quote_from_extraction(
        extraction,
        settings=settings,
        facade=facade,
        seller_block=seller_block,
        sequence=sequence,
        on_date=on_date,
        customer_email=customer_email,
        customer_hint=customer_hint,
        with_usd=with_usd,
        doc_type=DocType.IMAGE,
        tracer=trace,
    )


def restate(extraction: RFQExtraction) -> str:
    """Write out what we already read from the document, as plain text.

    A quote's source document is read exactly once. Everything after that works from the
    `RFQExtraction`, and this turns that extraction back into something the parser can read - so a
    revision never has to re-open a file that may no longer exist.
    """
    buyer = extraction.buyer
    header = [
        f"Khách hàng / Customer: {buyer.company}" if buyer.company else "",
        f"MST: {buyer.mst}" if buyer.mst else "",
        f"Email: {buyer.email}" if buyer.email else "",
        f"Liên hệ / Contact: {buyer.contact}" if buyer.contact else "",
    ]
    lines = [
        f"{n}. {line.raw_text or line.description_normalized}"
        f" — SL/Qty: {line.quantity if line.quantity is not None else '?'} {line.unit}".rstrip()
        for n, line in enumerate(extraction.lines, start=1)
    ]
    return "\n".join(
        [*(part for part in header if part), "", "Các dòng hàng / Line items:", *lines]
    ).strip()


async def quote_from_revision(
    extraction: RFQExtraction,
    instruction: str,
    *,
    settings: Settings,
    facade: MemoryFacade,
    seller_block: dict[str, object],
    sequence: int,
    on_date: date_type | None = None,
    customer_email: str | None = None,
    customer_hint: str | None = None,
    with_usd: bool = False,
    doc_type: DocType = DocType.EMAIL_TEXT,
    tracer: Tracer | None = None,
) -> PipelineResult:
    """FR-064: re-draft honouring a human instruction, starting from what we already read.

    The revision amends the *extraction*. It does not re-read the source document, for two reasons.

    The first is a bug this replaces. `revise()` used to concatenate the instruction onto the
    stored `source_text` and re-run the text pipeline - and for a quote that arrived as a
    spreadsheet, a PDF or a photo, `source_text` is a *placeholder* ("[Excel: bao-gia.xlsx]"),
    because the bytes are the document and the text is only what a human sees on the record. So a
    reviewer who asked for "chiết khấu thêm 3%" on a file-sourced quote got back a quote with no
    line items at all. The revision path was the last place still reaching for a source document
    that was never there.

    The second is that re-OCRing a scan on every revision is both expensive and non-deterministic:
    the same page can read differently twice, which means an instruction about a *discount* could
    silently change a *part number*. Reading once is the safer contract.

    The model still only reads. Quantities and discounts move because the parser saw the human say
    so, exactly as at intake; the money is recomputed deterministically afterwards, and the critic
    recomputes it again from the same source data.
    """
    trace = tracer or Tracer(quote_id="")
    amended = f"{restate(extraction)}\n\n[Yêu cầu chỉnh sửa / Revision instruction]\n{instruction}"

    with trace.step("DocumentParser", "revise", model=MODEL_PARSER_TEXT) as step:
        revised = await extract_text_rfq(amended, settings, usage=step)
        step.note(f"{len(extraction.lines)} line(s) in, {len(revised.lines)} out")
        step.content(prompt=amended, response=revised.model_dump_json())

    return await quote_from_extraction(
        revised,
        settings=settings,
        facade=facade,
        seller_block=seller_block,
        sequence=sequence,
        on_date=on_date,
        customer_email=customer_email,
        customer_hint=customer_hint,
        with_usd=with_usd,
        doc_type=doc_type,
        tracer=trace,
    )


async def quote_from_extraction(
    extraction: RFQExtraction,
    *,
    settings: Settings,
    facade: MemoryFacade,
    seller_block: dict[str, object],
    sequence: int,
    on_date: date_type | None = None,
    customer_email: str | None = None,
    customer_hint: str | None = None,
    with_usd: bool = False,
    doc_type: DocType = DocType.EMAIL_TEXT,
    tracer: Tracer | None = None,
    plan: QuotePlan | None = None,
) -> PipelineResult:
    """The shared path after extraction: gate -> customer -> match -> assemble -> critic -> render.

    Every input channel converges here, so text, spreadsheet and PDF RFQs are priced by exactly the
    same code. A channel that had its own pricing path would be a channel that could disagree.
    """
    today = on_date or date_type.today()
    trace = tracer or Tracer(quote_id="")
    reasons = validation_reasons(extraction)
    if reasons:  # FR-034: never proceed to matching
        return PipelineResult(
            extraction=extraction, clarification_reasons=reasons, trace=trace.document()
        )

    # FR-131: plan the non-trivial ones, and say why when we do not.
    plan = plan or QuotePlan()
    plan_record = await plan.open(extraction, doc_type)
    with trace.step("Orchestrator", "plan") as step:
        step.note(
            plan_record.reason
            if plan_record.skipped
            else f"planned {len(plan_record.subtasks) or len(extraction.lines)} subtask(s)"
        )

    # FR-043: candidates from the customers tenant, then the deterministic pick.
    #
    # Every signal we have is searched, and the results are unioned. This used to be an `or` chain -
    # hint, else company name, else the email's domain - which meant the email was consulted *only*
    # when there was no company name at all. A name that failed the fuzzy text search therefore
    # shadowed an exact, unique email match, which is the strongest identifier on the document.
    #
    # It cost a real customer: "Cong ty Thanh Cong" resolved, "Thanh Cong" did not, from the same
    # address. The quote was flagged UNKNOWN_CUSTOMER, priced at list instead of their dealer tier,
    # and their own history was never recalled - because recall needs a resolved customer.
    email = customer_email or extraction.buyer.email
    lookups = [customer_hint, extraction.buyer.company, email.split("@")[-1] if email else None]

    candidates: list[CustomerProfile] = []
    seen: set[str] = set()
    for lookup in lookups:
        if not lookup:
            continue
        for found, _ in facade.search_customers_text(lookup):
            if found.customer_id not in seen:
                seen.add(found.customer_id)
                candidates.append(found)

    resolution = resolve_customer(
        candidates, email=email, name=extraction.buyer.company, hint=customer_hint
    )
    await plan.done(
        "resolve the customer",
        "UNKNOWN_CUSTOMER" if resolution.unknown_customer else f"tier {resolution.tier.value}",
    )

    # FR-045: what happened last time we quoted this customer. It informs the reviewer; it never
    # touches the price - see memory/recall.py for why that line is drawn where it is.
    episodic: list[EpisodicRecall] = []
    truncated = False
    if resolution.profile is not None:
        with trace.step(
            "Orchestrator", "recall", model=MODEL_EMBED, operation=OP_EMBEDDINGS
        ) as step:
            try:
                episodic, truncated = recall_episodes(
                    facade=facade,
                    settings=settings,
                    customer_id=resolution.profile.customer_id,
                    query_text=_recall_query(extraction),
                )
            except Exception as exc:  # noqa: BLE001 - recall is an aid, never a dependency
                step.note(f"recall unavailable: {type(exc).__name__}")
            else:
                step.memory([recall.memory_id for recall in episodic])
                step.note(
                    f"recalled {len(episodic)} episode(s)"
                    + (" (budget truncated)" if truncated else "")
                )

    matches: list[MatchResult] = []
    assembly: list[AssemblyLine] = []
    for line_ref, line in enumerate(extraction.lines, start=1):
        match, products = await _match_line(
            line.description_normalized, facade, settings, line_ref, trace
        )
        matches.append(match)
        if match.sku is None or match.sku not in products:
            continue  # NO_MATCH lines are surfaced to the human, not priced
        assembly.append(
            AssemblyLine(
                product=products[match.sku],
                qty=line.quantity if line.quantity is not None else Decimal(1),
                tier=resolution.tier,
                description=None,  # bilingual drafting (FR-061) refines this later
                unit=None,
                note=match.reason,  # FR-063: substitution/confirmation transparency
                source=_STATUS_TO_SOURCE.get(match.status, LineSource.NO_MATCH),
            )
        )

    await plan.done("match the catalog", f"{len(assembly)}/{len(extraction.lines)} line(s) matched")

    if not assembly:
        plan_record = await plan.close("abandoned", "no line item could be matched")
        return PipelineResult(
            extraction=extraction,
            matches=matches,
            resolution=resolution,
            clarification_reasons=["NO_LINE_ITEMS"],
            trace=trace.document(),
            plan=plan_record,
            episodic=episodic,
            episodic_truncated=truncated,
        )

    # FR-048: the terms this quote carries are *retrieved*, not hardcoded. They used to be a module
    # constant, which meant a made-to-order server was quoted with "delivery within 7 working days"
    # - a promise the business cannot keep, printed on a document a customer is invoiced from.
    #
    # This runs *after* matching, and that ordering is the fix for a second, subtler version of the
    # same bug: retrieval by similarity alone put "software licences: 100% before activation" on a
    # quote for a Dell server. The categories of the matched goods decide which terms are even
    # eligible; similarity then ranks within them. Retrieval proposes, the rule disposes.
    with trace.step("Drafter", "sop", model=MODEL_EMBED, operation=OP_EMBEDDINGS) as step:
        categories = {item.product.category for item in assembly}
        terms, applied = retrieve_terms(
            facade=facade, settings=settings, extraction=extraction, categories=categories
        )
        step.note(f"SOP for {sorted(c.value for c in categories)}: " + ", ".join(applied))

    profile = resolution.profile
    quote = assemble_quote(
        quote_id=new_ulid(),
        quote_number=format_quote_number(today.year, sequence),
        seller_block=seller_block,
        customer_block=_customer_block(resolution, extraction),
        date=today.isoformat(),
        validity_days=settings.quote_validity_days,
        lines=assembly,
        terms=terms,
        notes=DEFAULT_NOTES,
        on_date=today,
        fx_usd_vnd=settings.fx_usd_vnd if with_usd else None,
        project_discount_pct=profile.project_discount_pct if profile is not None else 3.0,
    )
    await plan.done("price deterministically", f"total {quote.total_vnd} VND")

    report = run_critic(
        quote,
        margin_floor_pct=float(settings.margin_floor_pct),
        customer_known=not resolution.unknown_customer,
        lead_time_lines=lead_time_lines(assembly),  # FR-056
    )

    # FR-073: the verdict above is final before this line runs. The model is handed the finished
    # report and asked to *explain* it, in the two languages the quote is written in. It cannot set
    # `passed`, cannot add or drop a flag, and if it fails the quote is unaffected - the gate still
    # shows the flags and the diffs, which are the parts that carry authority.
    with trace.step("Reviewer", "narrate", model=MODEL_CRITIC, operation=OP_CHAT) as step:
        try:
            report.narrative = await review_note(quote, report, settings, usage=step)
        except Exception as exc:  # noqa: BLE001 - a narrative is an aid, never a dependency
            step.note(f"narrative unavailable: {type(exc).__name__}")
        else:
            step.note(f"{len(report.narrative.en.split())} words (cap {WORD_CAP})")

    await plan.done(
        "re-check with the critic",
        f"{len(report.recompute_diffs)} recompute diff(s), {len(report.blocking)} blocking flag(s)",
    )
    html = render_html(quote, vat_policy_note=vat_policy_note(today))

    await plan.done("stop at the human gate", "quote parked for a human decision")
    plan_record = await plan.close("done", f"{quote.quote_number} at the approval gate")

    return PipelineResult(
        extraction=extraction,
        matches=matches,
        resolution=resolution,
        quote=quote,
        critic=report,
        html=html,
        trace=trace.document(),
        plan=plan_record,
        episodic=episodic,
        episodic_truncated=truncated,
    )
