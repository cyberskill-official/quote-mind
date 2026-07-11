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
from .config.models import MODEL_EMBED, MODEL_PARSER_TEXT, MODEL_PLANNER
from .config.settings import Settings
from .memory.embedding import embed_text
from .memory.store import MemoryFacade
from .models import (
    BilingualText,
    CatalogProduct,
    CriticReport,
    LineSource,
    MatchResult,
    MatchStatus,
    Quote,
    QuoteTerms,
    RFQExtraction,
    new_ulid,
)
from .obs.otel import OP_EMBEDDINGS, OP_EXECUTE_TOOL
from .obs.trace import TraceDocument, Tracer
from .parsing import validation_reasons
from .pricing import vat_policy_note
from .quote import AssemblyLine, assemble_quote, format_quote_number, run_critic
from .quote.render import render_html
from .tools import build_match_result, fuse_candidates, resolve_customer
from .tools.customer import CustomerResolution

TOP_K = 8  # FR-042: vector_search top_k=8

# SOP-backed terms and notes land with FR-048/FR-061; these are the documented defaults until then.
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
    with tracer.step(
        "CatalogMatcher", "embed", model=MODEL_EMBED, operation=OP_EMBEDDINGS
    ) as step:
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
    today = on_date or date_type.today()
    trace = tracer or Tracer(quote_id="")  # tracing is always on; persistence is the caller's call

    with trace.step("DocumentParser", "parse", model=MODEL_PARSER_TEXT) as step:
        extraction = await extract_text_rfq(text, settings, usage=step)
        step.note(f"extracted {len(extraction.lines)} line(s)")
        step.content(prompt=text, response=extraction.model_dump_json())
    reasons = validation_reasons(extraction)
    if reasons:  # FR-034: never proceed to matching
        return PipelineResult(
            extraction=extraction, clarification_reasons=reasons, trace=trace.document()
        )

    # FR-043: candidates from the customers tenant, then the deterministic pick.
    email = customer_email or extraction.buyer.email
    lookup = customer_hint or extraction.buyer.company or (email.split("@")[-1] if email else "")
    candidates = [profile for profile, _ in facade.search_customers_text(lookup)] if lookup else []
    resolution = resolve_customer(
        candidates, email=email, name=extraction.buyer.company, hint=customer_hint
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

    if not assembly:
        return PipelineResult(
            extraction=extraction,
            matches=matches,
            resolution=resolution,
            clarification_reasons=["NO_LINE_ITEMS"],
            trace=trace.document(),
        )

    profile = resolution.profile
    quote = assemble_quote(
        quote_id=new_ulid(),
        quote_number=format_quote_number(today.year, sequence),
        seller_block=seller_block,
        customer_block=_customer_block(resolution, extraction),
        date=today.isoformat(),
        validity_days=settings.quote_validity_days,
        lines=assembly,
        terms=DEFAULT_TERMS,
        notes=DEFAULT_NOTES,
        on_date=today,
        fx_usd_vnd=settings.fx_usd_vnd if with_usd else None,
        project_discount_pct=profile.project_discount_pct if profile is not None else 3.0,
    )
    report = run_critic(
        quote,
        margin_floor_pct=float(settings.margin_floor_pct),
        customer_known=not resolution.unknown_customer,
    )
    html = render_html(quote, vat_policy_note=vat_policy_note(today))

    return PipelineResult(
        extraction=extraction,
        matches=matches,
        resolution=resolution,
        quote=quote,
        critic=report,
        html=html,
        trace=trace.document(),
    )
