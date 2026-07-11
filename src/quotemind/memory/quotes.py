"""Durable quote persistence: qm_quotes, qm_audit, qm_counters (frozen table names, section 12.5).

This is the state that makes FR-081 (durable pause and resume) real: the pipeline ends at the
approval gate and writes everything down, so a later approval call can be served by a completely
different process. Nothing waits in memory.

Two implementation notes, both deliberate and demo-scoped:
- The Python Tablestore SDK cannot read back an atomically incremented value (ReturnType has no
  RT_AFTER_MODIFY), so the per-year quote counter (FR-062) uses a bounded compare-and-set loop on
  qm_counters instead. It is still atomic: a losing writer retries against the new value.
- Idempotency (FR-024) and the status queue (API-02) would each want a secondary index. Rather than
  add tables outside the frozen list, idempotency is a pointer row inside qm_quotes ("idem:{sha}")
  and the queue is a bounded range scan. Both are documented demo-scale choices.
"""

from __future__ import annotations

import json
from typing import Any

from tablestore import (
    CapacityUnit,
    ComparatorType,
    Condition,
    Direction,
    OTSClient,
    OTSServiceError,
    ReservedThroughput,
    Row,
    RowExistenceExpectation,
    SingleColumnCondition,
    TableMeta,
    TableOptions,
)

from ..config.settings import Settings
from ..models import Actor, AuditEvent, QuoteRecord, Status
from ..models.audit import GENESIS_HASH, make_event

TABLE_QUOTES = "qm_quotes"
TABLE_AUDIT = "qm_audit"
TABLE_COUNTERS = "qm_counters"

_IDEM_PREFIX = "idem:"
_ALREADY_EXISTS = "OTSObjectAlreadyExist"
_CONDITION_FAILED = "OTSConditionCheckFail"
_MAX_CAS_RETRIES = 8


class CounterContentionError(RuntimeError):
    """The quote counter could not be advanced within the retry budget."""


# Every payload column on a quote row. `put_quote` writes these and `get_quote` reads them; the
# two must not drift apart, and a test asserts they do not. A column written but not listed here
# is a column that exists in Tablestore and reaches nobody.
PAYLOAD_COLUMNS = (
    "source_text",
    "extraction_json",  # FR-064: what a revision re-drafts from
    "matches_json",  # FR-042: what the matcher decided, and why - including when it refused
    "quote_json",
    "critic_json",
    "trace_json",
    "html",
    "plan_json",  # FR-131
    "episodic_json",  # FR-045
)


def _columns(row: Any) -> dict[str, Any]:
    return {name: value for name, value, *_ in (row.attribute_columns or [])}


class QuoteStore:
    """Wide-column store for QuoteRecord, the audit chain, and the quote-number counter."""

    def __init__(self, client: OTSClient) -> None:
        self.client = client

    @classmethod
    def from_settings(cls, settings: Settings) -> QuoteStore:
        return cls(
            OTSClient(
                settings.tablestore_endpoint,
                settings.alibaba_cloud_access_key_id,
                settings.alibaba_cloud_access_key_secret,
                settings.tablestore_instance,
            )
        )

    # --- schema ---
    def init_tables(self) -> list[str]:
        """Idempotently create the three tables. Returns the ones actually created."""
        specs = [
            (TABLE_QUOTES, [("quote_id", "STRING")]),
            (TABLE_AUDIT, [("quote_id", "STRING"), ("seq", "INTEGER")]),
            (TABLE_COUNTERS, [("counter_id", "STRING")]),
        ]
        created: list[str] = []
        for name, schema in specs:
            try:
                self.client.create_table(
                    TableMeta(name, schema),
                    TableOptions(),
                    ReservedThroughput(CapacityUnit(0, 0)),
                )
                created.append(name)
            except OTSServiceError as exc:
                if exc.get_error_code() != _ALREADY_EXISTS:
                    raise
        return created

    # --- quote numbering (FR-062) ---
    def next_sequence(self, year: int) -> int:
        """Atomically advance and return the per-year quote sequence (compare-and-set)."""
        counter_id = f"quote:{year}"
        for _ in range(_MAX_CAS_RETRIES):
            _, row, _ = self.client.get_row(
                TABLE_COUNTERS, [("counter_id", counter_id)], columns_to_get=["value"]
            )
            if row is None:
                try:
                    self.client.put_row(
                        TABLE_COUNTERS,
                        Row([("counter_id", counter_id)], [("value", 1)]),
                        Condition(RowExistenceExpectation.EXPECT_NOT_EXIST),
                    )
                    return 1
                except OTSServiceError as exc:
                    if exc.get_error_code() != _CONDITION_FAILED:
                        raise
                    continue  # someone else created it first; re-read and try again

            current = int(_columns(row)["value"])
            try:
                self.client.update_row(
                    TABLE_COUNTERS,
                    Row([("counter_id", counter_id)], {"PUT": [("value", current + 1)]}),
                    Condition(
                        RowExistenceExpectation.EXPECT_EXIST,
                        SingleColumnCondition("value", current, ComparatorType.EQUAL),
                    ),
                )
                return current + 1
            except OTSServiceError as exc:
                if exc.get_error_code() != _CONDITION_FAILED:
                    raise
                # lost the race: loop and retry against the new value
        raise CounterContentionError(f"could not advance counter {counter_id}")

    # --- quotes (DM-01) ---
    def put_quote(self, record: QuoteRecord, **payloads: str | None) -> None:
        """Merge-write the row. update_row (not put_row) so a status change cannot wipe payloads.

        There is exactly ONE list of payload columns - PAYLOAD_COLUMNS - and this reads from it.

        There used to be three: a keyword-only signature here, an inline tuple in the body that
        actually did the writing, and PAYLOAD_COLUMNS on the read side. `plan_json` and
        `episodic_json` were added to two of the three, and so were written to Tablestore and read
        back by nobody. The fix added the missing name to the signature and to PAYLOAD_COLUMNS, plus
        a test asserting *those two* agreed - and the very next column, `extraction_json`, was
        dropped by the third list the test did not know about. Live, twice, from the same shape.

        A typed signature did not prevent that, so it is gone. An unknown column now RAISES rather
        than being silently dropped, which is the failure mode that kept getting through: a write
        that vanishes leaves a green test suite and an empty panel in production.
        """
        unknown = set(payloads) - set(PAYLOAD_COLUMNS)
        if unknown:
            raise ValueError(
                f"{sorted(unknown)} is not a persisted quote column. Add it to PAYLOAD_COLUMNS - "
                "there is one list, and this is it."
            )

        columns: list[tuple[str, Any]] = [
            ("record_json", record.model_dump_json()),
            ("status", record.status.value),
        ]
        if record.sha256_payload:
            columns.append(("sha256", record.sha256_payload))
        for name in PAYLOAD_COLUMNS:
            value = payloads.get(name)
            if value is not None:
                columns.append((name, value))
        self.client.update_row(
            TABLE_QUOTES,
            Row([("quote_id", record.quote_id)], {"PUT": columns}),
            Condition(RowExistenceExpectation.IGNORE),
        )

    def get_quote(self, quote_id: str) -> dict[str, Any] | None:
        """The stored row: record (QuoteRecord) plus any quote/critic/html payloads."""
        _, row, _ = self.client.get_row(TABLE_QUOTES, [("quote_id", quote_id)])
        if row is None:
            return None
        columns = _columns(row)
        raw_record = columns.get("record_json")
        if not isinstance(raw_record, str):
            return None
        stored: dict[str, Any] = {"record": QuoteRecord.model_validate_json(raw_record)}
        for key in PAYLOAD_COLUMNS:
            if key in columns:
                stored[key] = columns[key]
        return stored

    def list_quotes(self, status: Status | None = None, limit: int = 50) -> list[QuoteRecord]:
        """API-02 queue. Bounded range scan, newest-first by updated_at (demo scale)."""
        records: list[QuoteRecord] = []
        start: list[tuple[str, Any]] | None = [("quote_id", "")]
        while start is not None and len(records) < limit * 4:
            consumed, next_start, rows, _ = self.client.get_range(
                TABLE_QUOTES,
                Direction.FORWARD,
                start,
                [("quote_id", "￿")],
                columns_to_get=["record_json", "status"],
                limit=100,
            )
            for row in rows or []:
                key = dict(row.primary_key).get("quote_id", "")
                if isinstance(key, str) and key.startswith(_IDEM_PREFIX):
                    continue  # pointer rows are not quotes
                raw = _columns(row).get("record_json")
                if not isinstance(raw, str):
                    continue
                record = QuoteRecord.model_validate_json(raw)
                if status is None or record.status == status:
                    records.append(record)
            start = next_start
        records.sort(key=lambda item: item.updated_at, reverse=True)
        return records[:limit]

    # --- idempotency (FR-024) ---
    def put_idempotency(self, sha256_payload: str, quote_id: str) -> None:
        self.client.put_row(
            TABLE_QUOTES,
            Row(
                [("quote_id", f"{_IDEM_PREFIX}{sha256_payload}")],
                [("target_quote_id", quote_id)],
            ),
            Condition(RowExistenceExpectation.IGNORE),
        )

    def get_idempotency(self, sha256_payload: str) -> str | None:
        _, row, _ = self.client.get_row(
            TABLE_QUOTES,
            [("quote_id", f"{_IDEM_PREFIX}{sha256_payload}")],
            columns_to_get=["target_quote_id"],
        )
        if row is None:
            return None
        target = _columns(row).get("target_quote_id")
        return target if isinstance(target, str) else None

    # --- audit chain (FR-094 / DM-12) ---
    def append_audit(
        self,
        quote_id: str,
        *,
        actor: Actor,
        event: str,
        payload_json: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Append the next hash-chained event. Reads the tail to chain onto it."""
        existing = self.list_audit(quote_id)
        seq = existing[-1].seq + 1 if existing else 1
        prev_hash = existing[-1].hash if existing else GENESIS_HASH
        entry = make_event(
            quote_id=quote_id,
            seq=seq,
            actor=actor,
            event=event,
            prev_hash=prev_hash,
            payload_json=payload_json,
        )
        self.client.put_row(
            TABLE_AUDIT,
            Row(
                [("quote_id", quote_id), ("seq", seq)],
                [("event_json", entry.model_dump_json())],
            ),
            Condition(RowExistenceExpectation.EXPECT_NOT_EXIST),
        )
        return entry

    def list_audit(self, quote_id: str) -> list[AuditEvent]:
        """API-04: the quote's audit events in seq order."""
        events: list[AuditEvent] = []
        _, _, rows, _ = self.client.get_range(
            TABLE_AUDIT,
            Direction.FORWARD,
            [("quote_id", quote_id), ("seq", 0)],
            [("quote_id", quote_id), ("seq", 2**62)],
            columns_to_get=["event_json"],
            limit=500,
        )
        for row in rows or []:
            raw = _columns(row).get("event_json")
            if isinstance(raw, str):
                events.append(AuditEvent.model_validate_json(raw))
        events.sort(key=lambda item: item.seq)
        return events


def totals_of(quote_json: str | None) -> dict[str, Any] | None:
    """The totals block stored on QuoteRecord.totals_json, pulled from a serialized Quote."""
    if not quote_json:
        return None
    data = json.loads(quote_json)
    return {
        "subtotal_vnd": data.get("subtotal_vnd"),
        "total_vnd": data.get("total_vnd"),
        "vat_breakdown": data.get("vat_breakdown"),
    }
