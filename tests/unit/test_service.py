"""TASK-080/081/083/084/094: the persisted lifecycle, the approval gate, and the audit chain."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from quotemind.config.models import MODEL_PARSER_TEXT
from quotemind.memory.quotes import PAYLOAD_COLUMNS
from quotemind.models import (
    Actor,
    AuditEvent,
    BilingualText,
    Buyer,
    CatalogProduct,
    Category,
    IllegalTransitionError,
    QuoteRecord,
    RFQExtraction,
    RFQLine,
    Status,
    StockStatus,
    Tier,
    verify_chain,
)
from quotemind.models.audit import GENESIS_HASH, make_event
from quotemind.obs.trace import Tracer
from quotemind.orchestrator import DEFAULT_NOTES, DEFAULT_TERMS, PipelineResult
from quotemind.quote import AssemblyLine, assemble_quote, format_quote_number, run_critic
from quotemind.service import ApprovalBlockedError, QuoteService

from .test_dispatch import FakeArtifacts

_ON = date(2026, 7, 11)


class _Settings:
    dashscope_api_key = "sk-test"
    dashscope_base_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    quote_validity_days = 14
    margin_floor_pct = 5
    fx_usd_vnd = 25_400
    mail_from = "quotes@demo.cyberskill.world"
    mail_transport = "stub"
    directmail_smtp_host = "smtpdm-ap-southeast-1.aliyun.com"
    directmail_smtp_port = 465
    directmail_user = None
    directmail_password = None
    trace_content = False  # TASK-111: prompt bodies stay out of the trace by default


class FakeStore:
    """In-memory stand-in for QuoteStore with the same surface."""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        self.audit: dict[str, list[AuditEvent]] = {}
        self.idem: dict[str, str] = {}
        self.counters: dict[int, int] = {}

    def next_sequence(self, year: int) -> int:
        self.counters[year] = self.counters.get(year, 0) + 1
        return self.counters[year]

    def put_quote(self, record: QuoteRecord, **payloads: Any) -> None:
        # The real store keeps an explicit column allowlist, and this fake used to accept anything.
        # That is how `plan_json` and `episodic_json` were written to Tablestore and read back by
        # nobody while every test passed: the double was more permissive than the thing it doubled.
        unknown = set(payloads) - set(PAYLOAD_COLUMNS)
        assert not unknown, (
            f"{sorted(unknown)} is not a column the real QuoteStore persists. "
            "Add it to quotemind.memory.quotes.PAYLOAD_COLUMNS (and to put_quote) or it will be "
            "silently dropped in production."
        )
        row = self.rows.setdefault(record.quote_id, {})
        row["record"] = record.model_copy(deep=True)
        for key, value in payloads.items():
            if value is not None:
                row[key] = value

    def get_quote(self, quote_id: str) -> dict[str, Any] | None:
        row = self.rows.get(quote_id)
        return dict(row) if row else None

    def list_quotes(self, status: Status | None = None, limit: int = 50) -> list[QuoteRecord]:
        records = [row["record"] for row in self.rows.values()]
        if status is not None:
            records = [record for record in records if record.status == status]
        return records[:limit]

    def put_idempotency(self, sha256_payload: str, quote_id: str) -> None:
        self.idem[sha256_payload] = quote_id

    def get_idempotency(self, sha256_payload: str) -> str | None:
        return self.idem.get(sha256_payload)

    def append_audit(
        self, quote_id: str, *, actor: Actor, event: str, payload_json: dict[str, Any] | None = None
    ) -> AuditEvent:
        existing = self.audit.setdefault(quote_id, [])
        entry = make_event(
            quote_id=quote_id,
            seq=existing[-1].seq + 1 if existing else 1,
            actor=actor,
            event=event,
            prev_hash=existing[-1].hash if existing else GENESIS_HASH,
            payload_json=payload_json,
        )
        existing.append(entry)
        return entry

    def list_audit(self, quote_id: str) -> list[AuditEvent]:
        return list(self.audit.get(quote_id, []))


def _product(*, cost: int = 15_000_000) -> CatalogProduct:
    return CatalogProduct(
        sku="DELL-LAT-5450",
        brand="Dell",
        category=Category.LAPTOP,
        name=BilingualText(vi="Laptop Dell Latitude 5450", en="Dell Latitude 5450"),
        unit="cái",
        list_price_vnd=22_000_000,
        dealer_price_vnd=19_800_000,
        cost_price_vnd=cost,
        vat_rate=8,
        stock_status=StockStatus.IN_STOCK,
        lead_time_days=7,
        warranty_months=12,
    )


def _result(sequence: int, *, thin_margin: bool = False) -> PipelineResult:
    """A real assembled + critiqued quote, so the service is tested against genuine artefacts."""
    product = _product(cost=19_700_000 if thin_margin else 15_000_000)
    quote = assemble_quote(
        quote_id="01JQUOTE0000000000000000000",
        quote_number=format_quote_number(2026, sequence),
        seller_block={"name": "CyberSkill JSC"},
        customer_block={
            "name": "Công ty ABC",
            "contact": "Chị Lan",
            "email": "mua.hang@thanhcong.vn",
        },
        date=_ON.isoformat(),
        validity_days=14,
        lines=[AssemblyLine(product=product, qty=Decimal(2), tier=Tier.DEALER)],
        terms=DEFAULT_TERMS,
        notes=DEFAULT_NOTES,
        on_date=_ON,
    )
    critic = run_critic(quote, margin_floor_pct=5.0)
    return PipelineResult(
        extraction=RFQExtraction(
            buyer=Buyer(company="Công ty ABC"),
            lines=[
                RFQLine(
                    raw_text="2 laptop",
                    description_normalized="Laptop Dell Latitude 5450",
                    quantity=Decimal(2),
                    unit="cái",
                    unit_original="cái",
                    confidence=1.0,
                )
            ],
        ),
        quote=quote,
        critic=critic,
        html="<html>quote</html>",
    )


def _service(store: FakeStore, *, thin_margin: bool = False, artifacts: Any = None) -> QuoteService:
    async def pipeline(
        _text: str, *, sequence: int, tracer: Tracer | None = None, **_kwargs: Any
    ) -> PipelineResult:
        result = _result(sequence, thin_margin=thin_margin)
        if tracer is None:
            return result
        # Mimic what the real pipeline records, so the service's trace handling is exercised.
        with tracer.step("DocumentParser", "parse", model=MODEL_PARSER_TEXT) as step:
            step.usage(tokens_in=1200, tokens_out=300)
            step.note("extracted 1 line")
        with tracer.step("CatalogMatcher", "retrieve", tool="vector_search") as step:
            step.memory(["DELL-LAT-5450"])
        return result.model_copy(update={"trace": tracer.document()})

    async def revision_pipeline(
        extraction: Any, instruction: str, *, sequence: int, **_kwargs: Any
    ) -> PipelineResult:
        # TASK-064: the revision amends the *extraction*. Taking a str here is the bug - for a quote
        # that arrived as a file there is no source text to re-read, so the lines only survive if
        # they are handed over as data.
        assert isinstance(extraction, RFQExtraction), (
            f"the revision pipeline got a {type(extraction).__name__}, not an RFQExtraction: "
            "a file-sourced quote has no source document to re-parse"
        )
        assert extraction.lines, "revised a quote whose line items were already gone"
        assert instruction
        return _result(sequence, thin_margin=thin_margin).model_copy(
            update={"extraction": extraction}
        )

    return QuoteService(
        store=store,  # type: ignore[arg-type]
        facade=object(),  # type: ignore[arg-type]
        settings=_Settings(),  # type: ignore[arg-type]
        seller_block={"name": "CyberSkill JSC"},
        pipeline=pipeline,
        revision_pipeline=revision_pipeline,
        artifacts=artifacts if artifacts is not None else FakeArtifacts(),
    )


def test_submit_is_idempotent() -> None:
    store = FakeStore()
    service = _service(store)
    first, created_first = service.submit(text="Cần 2 laptop Dell", on_date=_ON)
    second, created_second = service.submit(text="Cần 2 laptop Dell", on_date=_ON)

    assert created_first is True and created_second is False  # TASK-024
    assert first.quote_id == second.quote_id
    assert first.quote_number == "QM-2026-0001"


def test_pipeline_walks_the_states_and_chains_the_audit() -> None:
    store = FakeStore()
    service = _service(store)
    record, _ = service.submit(text="Cần 2 laptop Dell", on_date=_ON)
    final = asyncio.run(service.process(record, "Cần 2 laptop Dell", on_date=_ON))

    assert final.status == Status.PENDING_APPROVAL
    assert final.totals_json is not None and final.totals_json["total_vnd"] > 0

    events = store.list_audit(final.quote_id)
    names = [event.event for event in events]
    assert names[0] == "intake.received"
    assert "pipeline.parsing" in names and names[-1] == "pipeline.pending_approval"
    assert verify_chain(events) is True  # TASK-094 tamper-evident chain


def test_approve_requires_a_waiver_for_blocking_flags() -> None:
    store = FakeStore()
    service = _service(store, thin_margin=True)
    record, _ = service.submit(text="Cần 2 laptop Dell", on_date=_ON)
    final = asyncio.run(service.process(record, "Cần 2 laptop Dell", on_date=_ON))

    # A policy flag still reaches the human (TASK-071/083) - it is not a hard critic failure.
    assert final.status == Status.PENDING_APPROVAL
    assert "MARGIN_BELOW_FLOOR" in final.flags

    with pytest.raises(ApprovalBlockedError) as exc:
        service.approve(final.quote_id)
    assert exc.value.flags == ["MARGIN_BELOW_FLOOR"]

    approved = service.approve(
        final.quote_id, waive_flags=["MARGIN_BELOW_FLOOR"], reason="strategic account"
    )
    assert approved.status == Status.APPROVED
    waiver = [e for e in store.list_audit(final.quote_id) if e.event == "human.approved"][0]
    assert waiver.payload_json["waived_flags"] == ["MARGIN_BELOW_FLOOR"]  # TASK-083: audited
    assert waiver.actor.kind == "human"


def test_clean_quote_approves_without_a_waiver() -> None:
    store = FakeStore()
    service = _service(store)
    record, _ = service.submit(text="Cần 2 laptop Dell", on_date=_ON)
    final = asyncio.run(service.process(record, "Cần 2 laptop Dell", on_date=_ON))
    assert service.approve(final.quote_id, comment="ok").status == Status.APPROVED


def test_reject_and_illegal_transition() -> None:
    store = FakeStore()
    service = _service(store)
    record, _ = service.submit(text="Cần 2 laptop Dell", on_date=_ON)

    # received -> approved is not a legal edge (TASK-080)
    with pytest.raises(IllegalTransitionError):
        service.approve(record.quote_id)

    final = asyncio.run(service.process(record, "Cần 2 laptop Dell", on_date=_ON))
    assert service.reject(final.quote_id, comment="giá cao").status == Status.REJECTED


def test_dispatch_renders_stores_and_sends_then_marks_sent() -> None:
    store = FakeStore()
    artifacts = FakeArtifacts()
    service = _service(store, artifacts=artifacts)
    record, _ = service.submit(text="Cần 2 laptop Dell", on_date=_ON)
    final = asyncio.run(service.process(record, "Cần 2 laptop Dell", on_date=_ON))
    service.approve(final.quote_id)

    sent = service.dispatch(final.quote_id)
    assert sent.status == Status.SENT

    # TASK-091: a real PDF landed privately under quotes/{quote_number}.pdf
    key = f"quotes/{final.quote_number}.pdf"
    assert artifacts.pdfs[key].startswith(b"%PDF-")
    # TASK-093: the stub transport wrote the same message to the outbox
    assert f"outbox/{final.quote_number}.eml" in artifacts.emls

    event = [e for e in store.list_audit(final.quote_id) if e.event == "dispatch.sent_stub"][0]
    assert event.payload_json["transport"] == "stub"
    assert event.payload_json["pdf_key"] == key
    assert event.payload_json["attached"] is True
    assert verify_chain(store.list_audit(final.quote_id)) is True


def test_dispatch_with_no_recipient_is_a_skip_not_a_failure() -> None:
    """This test used to assert the opposite, and the opposite was a bug.

    It required that a quote with nobody to send it to land in `failed_dispatch`. In production that
    is what an RFQ dropped into the OSS inbox always looks like - a file has no sender - so a human
    would approve a perfectly good quote and watch it turn red. Nothing had failed. Nobody had said
    where to send it.

    The approval stands, the quote stays `approved`, and the skip is recorded with its reason.
    """
    store = FakeStore()
    service = _service(store)
    record, _ = service.submit(text="Cần 2 laptop Dell", on_date=_ON)
    final = asyncio.run(service.process(record, "Cần 2 laptop Dell", on_date=_ON))
    service.approve(final.quote_id)

    # Strip the recipient the pipeline put on the quote: this is an OSS file drop.
    stored = store.rows[final.quote_id]
    quote = json.loads(stored["quote_json"])
    quote["customer_block"].pop("email")
    stored["quote_json"] = json.dumps(quote)

    after = service.dispatch(final.quote_id)
    assert after.status == Status.APPROVED  # NOT failed_dispatch
    skip = [e for e in store.list_audit(final.quote_id) if e.event == "dispatch.skipped"][0]
    assert "no recipient" in skip.payload_json["reason"]

    # And a recipient supplied later sends it, from the same approved state.
    sent = service.dispatch(final.quote_id, recipient="chi.lan@thanhcong.vn")
    assert sent.status == Status.SENT


def test_revise_reruns_and_counts_revisions() -> None:
    store = FakeStore()
    service = _service(store)
    record, _ = service.submit(text="Cần 2 laptop Dell", on_date=_ON)
    final = asyncio.run(service.process(record, "Cần 2 laptop Dell", on_date=_ON))

    revised = asyncio.run(service.revise(final.quote_id, instruction="Giảm giá 5%", on_date=_ON))
    assert revised.status == Status.PENDING_APPROVAL
    assert revised.revision == 1
    names = [event.event for event in store.list_audit(final.quote_id)]
    assert "human.revise" in names and names[-1] == "revision.pending_approval"


# --- TASK-111: the trace is persisted alongside the quote, and never load-bearing ---


def test_the_trace_is_written_to_oss_and_stored_on_the_quote() -> None:
    store = FakeStore()
    artifacts = FakeArtifacts()
    service = _service(store, artifacts=artifacts)
    record, _ = service.submit(text="Cần 2 laptop Dell", on_date=_ON)
    final = asyncio.run(service.process(record, "Cần 2 laptop Dell", on_date=_ON))

    assert f"traces/{final.quote_id}.json" in artifacts.traces  # TASK-111 key layout

    document = service.trace(final.quote_id)  # API-05
    assert document["quote_id"] == final.quote_id
    assert [step["seq"] for step in document["steps"]] == [1, 2]
    assert document["steps"][0]["model"] == MODEL_PARSER_TEXT
    assert document["total_tokens_in"] == 1200
    assert Decimal(document["total_cost_usd"]) > 0  # TASK-112: real tokens, priced
    assert document["contents"] == []  # TRACE_CONTENT is off, so no prompt bodies


def test_a_trace_write_failure_does_not_fail_the_quote() -> None:
    store = FakeStore()
    service = _service(store, artifacts=FakeArtifacts(trace_fails=True))
    record, _ = service.submit(text="Cần 2 laptop Dell", on_date=_ON)
    final = asyncio.run(service.process(record, "Cần 2 laptop Dell", on_date=_ON))

    # Observability is never load-bearing: the quote still reaches the human.
    assert final.status == Status.PENDING_APPROVAL
    names = [event.event for event in store.list_audit(final.quote_id)]
    assert "trace.persist_failed" in names  # but the failure is on the record, not swallowed
