"""DM-12: the audit hash chain builds, verifies, and detects tampering."""

from __future__ import annotations

from quotemind.models import GENESIS_HASH, Actor, AuditEvent, make_event, verify_chain


def _chain() -> list[AuditEvent]:
    events: list[AuditEvent] = []
    prev = GENESIS_HASH
    steps = [
        ("system", None, "received"),
        ("agent", "IntakeClassifier", "classified"),
        ("human", None, "approved"),
    ]
    for seq, (kind, name, event) in enumerate(steps, start=1):
        built = make_event(
            quote_id="q1",
            seq=seq,
            actor=Actor(kind=kind, name=name),
            event=event,
            prev_hash=prev,
            payload_json={"seq": seq},
        )
        events.append(built)
        prev = built.hash
    return events


def test_valid_chain_verifies() -> None:
    assert verify_chain(_chain()) is True


def test_first_event_links_to_genesis() -> None:
    assert _chain()[0].prev_hash == GENESIS_HASH


def test_tampered_payload_breaks_chain() -> None:
    events = _chain()
    events[1] = events[1].model_copy(update={"payload_json": {"seq": 999}})
    assert verify_chain(events) is False


def test_broken_prev_hash_fails() -> None:
    events = _chain()
    events[2] = events[2].model_copy(update={"prev_hash": GENESIS_HASH})
    assert verify_chain(events) is False
