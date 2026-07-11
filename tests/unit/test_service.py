"""FR-080/081/083/084/094: the persisted lifecycle, the approval gate, and the audit chain."""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

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
from quotemind.orchestrator import DEFAULT_NOTES, DEFAULT_TERMS, PipelineResult
from quotemind.quote import AssemblyLine, assemble_quote, format_quote_number, run_critic
from quotemind.service import ApprovalBlockedError, QuoteService

_ON = date(2026, 7, 11)


class _Settings:
    dashscope_api_key = "sk-test"
    dashscope_base_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    quote_validity_days = 14
    margin_floor_pct = 5
    fx_usd_vnd = 25_400


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
        customer_block={"name": "Công ty ABC"},
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


def _service(store: FakeStore, *, thin_margin: bool = False) -> QuoteService:
    async def pipeline(_text: str, *, sequence: int, **_kwargs: Any) -> PipelineResult:
        return _result(sequence, thin_margin=thin_margin)

    return QuoteService(
        store=store,  # type: ignore[arg-type]
        facade=object(),  # type: ignore[arg-type]
        settings=_Settings(),  # type: ignore[arg-type]
        seller_block={"name": "CyberSkill JSC"},
        pipeline=pipeline,
    )


def test_submit_is_idempotent() -> None:
    store = FakeStore()
    service = _service(store)
    first, created_first = service.submit(text="Cần 2 laptop Dell", on_date=_ON)
    second, created_second = service.submit(text="Cần 2 laptop Dell", on_date=_ON)

    assert created_first is True and created_second is False  # FR-024
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
    assert verify_chain(events) is True  # FR-094 tamper-evident chain


def test_approve_requires_a_waiver_for_blocking_flags() -> None:
    store = FakeStore()
    service = _service(store, thin_margin=True)
    record, _ = service.submit(text="Cần 2 laptop Dell", on_date=_ON)
    final = asyncio.run(service.process(record, "Cần 2 laptop Dell", on_date=_ON))

    # A policy flag still reaches the human (FR-071/083) - it is not a hard critic failure.
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
    assert waiver.payload_json["waived_flags"] == ["MARGIN_BELOW_FLOOR"]  # FR-083: audited
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

    # received -> approved is not a legal edge (FR-080)
    with pytest.raises(IllegalTransitionError):
        service.approve(record.quote_id)

    final = asyncio.run(service.process(record, "Cần 2 laptop Dell", on_date=_ON))
    assert service.reject(final.quote_id, comment="giá cao").status == Status.REJECTED


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
