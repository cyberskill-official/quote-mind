"""DM-12 AuditEvent and the tamper-evident sha256 hash chain (table qm_audit)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

GENESIS_HASH = "0" * 64


class Actor(BaseModel):
    kind: Literal["agent", "human", "system"]
    name: str | None = None  # agent name when kind == "agent"


class AuditEvent(BaseModel):
    """DM-12: immutable audit row (pk quote_id + seq) linked by a sha256 chain."""

    quote_id: str
    seq: int
    ts: datetime
    actor: Actor
    event: str
    payload_json: dict[str, Any] = Field(default_factory=dict)
    prev_hash: str
    hash: str


def compute_event_hash(
    *,
    quote_id: str,
    seq: int,
    ts: datetime,
    actor: Actor,
    event: str,
    payload_json: dict[str, Any],
    prev_hash: str,
) -> str:
    """Deterministic sha256 over the canonical event body, excluding `hash` itself."""
    canonical = json.dumps(
        {
            "quote_id": quote_id,
            "seq": seq,
            "ts": ts.isoformat(),
            "actor": actor.model_dump(mode="json"),
            "event": event,
            "payload_json": payload_json,
            "prev_hash": prev_hash,
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def make_event(
    *,
    quote_id: str,
    seq: int,
    actor: Actor,
    event: str,
    prev_hash: str,
    payload_json: dict[str, Any] | None = None,
    ts: datetime | None = None,
) -> AuditEvent:
    """Build an AuditEvent with its chained hash computed from prev_hash."""
    resolved_ts = ts or datetime.now(timezone.utc)
    resolved_payload = payload_json if payload_json is not None else {}
    event_hash = compute_event_hash(
        quote_id=quote_id,
        seq=seq,
        ts=resolved_ts,
        actor=actor,
        event=event,
        payload_json=resolved_payload,
        prev_hash=prev_hash,
    )
    return AuditEvent(
        quote_id=quote_id,
        seq=seq,
        ts=resolved_ts,
        actor=actor,
        event=event,
        payload_json=resolved_payload,
        prev_hash=prev_hash,
        hash=event_hash,
    )


def verify_chain(events: list[AuditEvent]) -> bool:
    """True when events form an unbroken chain from GENESIS_HASH by ascending seq."""
    prev = GENESIS_HASH
    for event in sorted(events, key=lambda item: item.seq):
        expected = compute_event_hash(
            quote_id=event.quote_id,
            seq=event.seq,
            ts=event.ts,
            actor=event.actor,
            event=event.event,
            payload_json=event.payload_json,
            prev_hash=event.prev_hash,
        )
        if event.prev_hash != prev or event.hash != expected:
            return False
        prev = event.hash
    return True
