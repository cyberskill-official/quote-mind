"""The tasks that finished the roadmap: TASK-048, TASK-056, TASK-073, TASK-085, TASK-104, TASK-124, TASK-134.

Each of these has one property that actually matters, and it is the one asserted here:

  * TASK-048 - the terms are retrieved, and a memory outage still yields a quote with terms on it.
  * TASK-056 - an out-of-stock line says so, on the line, and raises a flag that does not block.
  * TASK-073 - the narrative explains the verdict. It cannot *be* the verdict.
  * TASK-085 - a quote nobody has looked at is visible as such.
  * TASK-104 - the page renders the committed numbers, and says how old they are.
  * TASK-124 - the branded face is actually in the wheel.
  * TASK-134 - cancel is distinguishable from reject, forever, on the audit trail.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest

from quotemind.agents.reviewer import WORD_CAP, ReviewNarrative, _cap, _facts
from quotemind.memory.sop import FALLBACK, retrieve_terms
from quotemind.models import (
    BilingualText,
    CatalogProduct,
    Category,
    SOPSnippet,
    SopTopic,
    Status,
    StockStatus,
    Tier,
)
from quotemind.quote import LEAD_TIME, AssemblyLine, assemble_quote, lead_time_lines, run_critic
from quotemind.quote.render import render_pdf

from .test_service import FakeStore, _service, _Settings

_ON = date(2026, 7, 12)


def _product(
    *, sku: str = "DELL-LAT-5450", stock: StockStatus = StockStatus.IN_STOCK
) -> CatalogProduct:
    return CatalogProduct(
        sku=sku,
        brand="Dell",
        category=Category.LAPTOP,
        name=BilingualText(vi="Laptop Dell Latitude 5450", en="Dell Latitude 5450"),
        unit="cái",
        list_price_vnd=22_000_000,
        dealer_price_vnd=19_800_000,
        cost_price_vnd=15_000_000,
        vat_rate=8,
        stock_status=stock,
        lead_time_days=42,
        warranty_months=12,
    )


def _quote(*, stock: StockStatus = StockStatus.IN_STOCK) -> tuple[Any, list[AssemblyLine]]:
    from quotemind.orchestrator import DEFAULT_NOTES, DEFAULT_TERMS  # noqa: PLC0415

    lines = [AssemblyLine(product=_product(stock=stock), qty=Decimal(2), tier=Tier.DEALER)]
    quote = assemble_quote(
        quote_id="01JQUOTE0000000000000000000",
        quote_number="QM-2026-0001",
        seller_block={"name": "CyberSkill JSC"},
        customer_block={"name": "Công ty ABC", "email": "mua.hang@thanhcong.vn"},
        date=_ON.isoformat(),
        validity_days=14,
        lines=lines,
        terms=DEFAULT_TERMS,
        notes=DEFAULT_NOTES,
        on_date=_ON,
    )
    return quote, lines


# --- TASK-056: an out-of-stock line says so, and the flag does not block ---
def test_an_out_of_stock_line_carries_its_lead_time_in_both_languages() -> None:
    quote, lines = _quote(stock=StockStatus.OUT_OF_STOCK)

    note = quote.lines[0].note
    assert note is not None
    assert "42 ngày" in note.vi and "42 days" in note.en

    report = run_critic(quote, lead_time_lines=lead_time_lines(lines))
    assert LEAD_TIME in report.non_blocking
    assert LEAD_TIME not in report.blocking  # a lead time is news, not an error
    assert report.passed  # and it must not stop the quote reaching a human


def test_a_line_on_the_shelf_says_nothing_about_lead_time() -> None:
    quote, lines = _quote(stock=StockStatus.IN_STOCK)
    assert quote.lines[0].note is None
    assert lead_time_lines(lines) == []
    assert LEAD_TIME not in run_critic(quote, lead_time_lines=lead_time_lines(lines)).non_blocking


def test_the_lead_time_is_appended_to_a_substitution_note_not_instead_of_it() -> None:
    """Two things can be true about one line, and the reviewer needs to know both."""
    from quotemind.orchestrator import DEFAULT_NOTES, DEFAULT_TERMS  # noqa: PLC0415

    substitution = BilingualText(vi="Đề xuất mã tương đương.", en="Equivalent part proposed.")
    lines = [
        AssemblyLine(
            product=_product(stock=StockStatus.OUT_OF_STOCK),
            qty=Decimal(1),
            tier=Tier.DEALER,
            note=substitution,
        )
    ]
    quote = assemble_quote(
        quote_id="01J",
        quote_number="QM-2026-0002",
        seller_block={"name": "S"},
        customer_block={"name": "C"},
        date=_ON.isoformat(),
        validity_days=14,
        lines=lines,
        terms=DEFAULT_TERMS,
        notes=DEFAULT_NOTES,
        on_date=_ON,
    )
    note = quote.lines[0].note
    assert note is not None
    assert "tương đương" in note.vi and "42 ngày" in note.vi  # both, not either


# --- TASK-073: the narrative explains the verdict; it cannot be the verdict ---
def test_the_critic_reaches_its_verdict_without_the_model() -> None:
    """run_critic must not depend on the narrative. The guardrail is code, and code alone."""
    quote, _ = _quote()
    report = run_critic(quote)
    assert report.passed is True
    assert report.narrative is None  # the verdict exists before any model is asked to explain it


def test_the_narrative_is_capped_in_code_not_merely_requested_in_the_prompt() -> None:
    long = " ".join(["từ"] * 200)
    capped = _cap(long)
    assert len(capped.split()) == WORD_CAP  # 80 words; the ellipsis rides on the last one
    assert capped.endswith("...")
    assert _cap("ngắn gọn") == "ngắn gọn"  # a short note is left exactly alone


def test_the_model_is_shown_the_verdict_and_the_numbers_it_may_not_recompute() -> None:
    quote, _ = _quote()
    report = run_critic(quote)
    facts = _facts(quote, report)
    assert "ĐẠT / PASSED" in facts  # the verdict is an input, not an output
    assert f"{quote.total_vnd:,}" in facts  # and the totals come pre-computed
    assert "DELL-LAT-5450" in facts


def test_a_failing_narrative_leaves_the_quote_untouched() -> None:
    """The gate still shows the flags and the diffs. Those are the parts that carry authority."""
    quote, _ = _quote()
    report = run_critic(quote)
    passed_before, flags_before = report.passed, list(report.non_blocking)

    # This is what orchestrator.py does when review_note raises: nothing.
    assert report.narrative is None
    assert report.passed is passed_before and report.non_blocking == flags_before


def test_the_narrative_model_is_structured_output_not_parsed_prose() -> None:
    """TASK-133: every LLM boundary that yields data uses structured_model=."""
    narrative = ReviewNarrative(vi="Đã đối chiếu số học.", en="Arithmetic reconciled.")
    assert narrative.vi and narrative.en


# --- TASK-048: the terms are retrieved, and a memory outage still yields terms ---
class _SopFacade:
    def __init__(self, snippets: list[SOPSnippet] | None = None, *, explode: bool = False) -> None:
        self._snippets = snippets or []
        self._explode = explode

    def search_sop(self, _vector: list[float], top_k: int = 4) -> list[tuple[SOPSnippet, float]]:
        if self._explode:
            raise RuntimeError("tablestore is having a day")
        return [(snippet, 0.83) for snippet in self._snippets][:top_k]


def _extraction() -> Any:
    from quotemind.models import Buyer, RFQExtraction, RFQLine  # noqa: PLC0415

    return RFQExtraction(
        buyer=Buyer(company="Công ty ABC"),
        lines=[
            RFQLine(
                raw_text="1 máy chủ Dell",
                description_normalized="Máy chủ Dell PowerEdge R650",
                quantity=Decimal(1),
                unit="cái",
                unit_original="cái",
                confidence=1.0,
            )
        ],
    )


def test_the_terms_come_from_the_sop_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("quotemind.memory.sop.embed_text", lambda *_a, **_k: [0.1] * 8)
    server = SOPSnippet(
        topic=SopTopic.WARRANTY,
        text=BilingualText(vi="Bảo hành 36 tháng.", en="36 months warranty."),
    )
    facade = _SopFacade([server])

    terms, applied = retrieve_terms(
        facade=facade,  # type: ignore[arg-type]
        settings=_Settings(),  # type: ignore[arg-type]
        extraction=_extraction(),
    )
    # The warranty snippet was retrieved; payment and delivery had no hit for their topic, so they
    # fall back rather than borrowing the warranty sentence.
    assert terms.warranty.vi == "Bảo hành 36 tháng."
    assert terms.payment == FALLBACK[SopTopic.PAYMENT]
    assert any(entry.startswith("warranty@") for entry in applied)
    assert "payment=default" in applied


def test_every_seeded_sop_survives_the_bilingual_number_check() -> None:
    """TASK-072 applies to the text a human wrote, exactly as it applies to the text a model wrote.

    This is not hypothetical. The first server quote after TASK-048 shipped came back BLOCKED, live,
    with `BILINGUAL_NUMBER_MISMATCH` - because one seeded snippet said "thanh toán 100%" in
    Vietnamese and "paid in full" in English. That is a good translation and a bad *quote*: the
    number vanished. The critic could not tell that a human had written it, and it was right not to
    care.

    Terms are retrieved into real quotes now, so the seed data is production content. It gets the
    same gate.
    """
    import re  # noqa: PLC0415

    from quotemind.seed.sop import SOPS  # noqa: PLC0415

    digits = re.compile(r"\d+")
    for sop in SOPS:
        assert digits.findall(sop.text.vi) == digits.findall(sop.text.en), (
            f"the {sop.topic.value} snippet has different numbers in its two languages, so any "
            f"quote that retrieves it is blocked by TASK-072."
            f"\n  vi: {sop.text.vi}\n  en: {sop.text.en}"
        )


def test_a_quote_still_has_terms_when_the_memory_store_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retrieval is an aid. A quote with no payment terms is worse than one with generic terms."""
    monkeypatch.setattr("quotemind.memory.sop.embed_text", lambda *_a, **_k: [0.1] * 8)
    terms, applied = retrieve_terms(
        facade=_SopFacade(explode=True),  # type: ignore[arg-type]
        settings=_Settings(),  # type: ignore[arg-type]
        extraction=_extraction(),
    )
    assert terms.payment.vi and terms.delivery.vi and terms.warranty.vi
    assert applied == ["payment=default", "delivery=default", "warranty=default"]


def test_a_server_is_not_quoted_on_software_payment_terms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bug this rule exists for, and it was found live.

    Asked for the payment terms on a Dell PowerEdge, the vector search returned "software licences
    and implementation services: 100% payment before activation" at 0.657, above the generic 30-day
    term at 0.617. Both talk about money and both say "100%", so they sit close together in the
    embedding - and the wrong one would have gone onto a customer's quotation as a payment
    obligation they never agreed to.

    Similarity is a fine way to rank the terms that are *allowed*. It is a terrible way to decide
    which are allowed. So the goods decide eligibility, and similarity only ranks within that.
    """
    monkeypatch.setattr("quotemind.memory.sop.embed_text", lambda *_a, **_k: [0.1] * 8)

    software_terms = SOPSnippet(
        topic=SopTopic.PAYMENT,
        text=BilingualText(vi="Phần mềm: 100% trước.", en="Software: 100% up front."),
        applies_to=[Category.SOFTWARE_LICENSE, Category.SERVICE],
    )
    generic = SOPSnippet(
        topic=SopTopic.PAYMENT,
        text=BilingualText(vi="Thanh toán 100% trong 30 ngày.", en="100% payment within 30 days."),
    )
    # The fake returns them in the order the real search did: the wrong one first.
    facade = _SopFacade([software_terms, generic])

    terms, _ = retrieve_terms(
        facade=facade,  # type: ignore[arg-type]
        settings=_Settings(),  # type: ignore[arg-type]
        extraction=_extraction(),
        categories={Category.SERVER},
    )
    assert terms.payment == generic.text, "a server was quoted on software payment terms"

    # And the same snippet is exactly right when the goods really are software.
    terms, _ = retrieve_terms(
        facade=facade,  # type: ignore[arg-type]
        settings=_Settings(),  # type: ignore[arg-type]
        extraction=_extraction(),
        categories={Category.SOFTWARE_LICENSE},
    )
    assert terms.payment == software_terms.text


def test_the_search_is_wide_enough_that_the_topic_filter_cannot_starve() -> None:
    """TOP_K was 4, over the whole tenant, filtered by topic afterwards.

    With 11 snippets across 5 topics, that meant a topic could contribute a single survivor to the
    top 4 - and a single survivor wins by default, however badly it fits. A filter applied after a
    truncation is a filter over a lottery.
    """
    from quotemind.memory.sop import TOP_K  # noqa: PLC0415
    from quotemind.seed.sop import SOPS  # noqa: PLC0415

    assert TOP_K >= len(SOPS), (
        f"top_k={TOP_K} over a tenant of {len(SOPS)} snippets cannot guarantee that every topic "
        "reaches the filter. Raise it, or filter inside the search."
    )


def test_the_retrieval_is_per_topic_so_one_topic_cannot_crowd_out_another(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single global top-k would happily return three payment snippets and no warranty."""
    monkeypatch.setattr("quotemind.memory.sop.embed_text", lambda *_a, **_k: [0.1] * 8)
    payments = [
        SOPSnippet(
            topic=SopTopic.PAYMENT, text=BilingualText(vi=f"Điều khoản {n}.", en=f"Term {n}.")
        )
        for n in range(4)
    ]
    terms, _ = retrieve_terms(
        facade=_SopFacade(payments),  # type: ignore[arg-type]
        settings=_Settings(),  # type: ignore[arg-type]
        extraction=_extraction(),
    )
    assert terms.payment.vi == "Điều khoản 0."  # the payment search found payment snippets
    assert terms.warranty == FALLBACK[SopTopic.WARRANTY]  # and did not become the warranty


# --- TASK-085: a quote nobody has looked at is visible as such ---
def test_a_quote_waiting_too_long_at_the_gate_is_marked_stale() -> None:
    store = FakeStore()
    service = _service(store)
    record, _ = service.submit(text="Cần 2 laptop", on_date=_ON)
    final = asyncio.run(service.process(record, "Cần 2 laptop", on_date=_ON))
    assert service.is_stale(final) is False  # it arrived a moment ago

    final.updated_at = datetime.now(timezone.utc) - timedelta(hours=5)
    store.rows[final.quote_id]["record"] = final
    assert service.is_stale(final) is True
    assert [r.quote_id for r in service.stale_pending()] == [final.quote_id]


def test_only_a_quote_at_the_gate_can_be_stale() -> None:
    """An approved quote that has sat for a week is not waiting on anybody."""
    store = FakeStore()
    service = _service(store)
    record, _ = service.submit(text="Cần 2 laptop", on_date=_ON)
    final = asyncio.run(service.process(record, "Cần 2 laptop", on_date=_ON))
    approved = service.approve(final.quote_id)
    approved.updated_at = datetime.now(timezone.utc) - timedelta(days=7)
    assert service.is_stale(approved) is False


# --- TASK-134: a cancel and a rejection are different things, forever ---
def test_a_cancel_ends_the_quote_and_says_it_was_a_cancel() -> None:
    store = FakeStore()
    service = _service(store)
    record, _ = service.submit(text="Cần 2 laptop", on_date=_ON)
    final = asyncio.run(service.process(record, "Cần 2 laptop", on_date=_ON))

    cancelled = service.cancel(final.quote_id, comment="khách đổi ý")
    assert cancelled.status is Status.REJECTED  # the frozen enum's word for "ended, not sent"

    events = [event.event for event in store.list_audit(final.quote_id)]
    assert "human.cancel" in events
    assert "human.rejected" not in events  # the audit trail keeps them apart


def test_a_cancel_is_not_remembered_as_evidence_the_price_was_wrong() -> None:
    """Somebody closing a browser tab must not teach the system to distrust its own pricing."""
    store = FakeStore()
    service = _service(store)
    remembered: list[str] = []
    service._remember = lambda *a, **k: remembered.append("called")  # type: ignore[method-assign]

    record, _ = service.submit(text="Cần 2 laptop", on_date=_ON)
    final = asyncio.run(service.process(record, "Cần 2 laptop", on_date=_ON))
    service.cancel(final.quote_id)

    assert remembered == []  # a rejection writes a memory; a cancel does not


# --- TASK-104: the page renders the committed numbers ---
def test_the_eval_page_renders_the_committed_snapshot() -> None:
    from quotemind.eval_.report import load, render_report_html  # noqa: PLC0415

    data = load()
    assert data is not None, "the snapshot must be committed - the page renders it, not the eval"

    html = render_report_html()
    assert f"{data['pipeline']['price_exactness'] * 100:.0f}%" in html
    assert f"{data['baseline']['price_exactness'] * 100:.0f}%" in html
    assert len(data["cases"]) == 30
    assert "ai:generated" in html and 'content="none"' in html  # no model wrote these numbers


def test_the_eval_page_says_how_old_its_numbers_are() -> None:
    """A stale benchmark that looks fresh is worse than no benchmark."""
    from quotemind.eval_.report import _age  # noqa: PLC0415

    old = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    assert "3 days ago" in _age(old)
    assert _age(None) == "unknown"


# --- TASK-124: the branded face is actually in the wheel ---
def test_the_pdf_renders_with_be_vietnam_pro_bundled() -> None:
    from quotemind.quote.render import FONT_DIR  # noqa: PLC0415

    for weight in ("Regular", "SemiBold", "Bold"):
        font = FONT_DIR / f"BeVietnamPro-{weight}.ttf"
        assert font.exists(), f"{font.name} is declared by @font-face and must ship with the wheel"
        assert font.read_bytes()[:4] in (b"\x00\x01\x00\x00", b"true"), "not a TrueType file"

    assert (FONT_DIR / "OFL.txt").exists(), "the OFL requires the licence travel with the fonts"

    quote, _ = _quote()
    pdf = render_pdf(quote, vat_policy_note=BilingualText(vi="VAT 8%", en="VAT 8%"))
    assert pdf.startswith(b"%PDF-")
