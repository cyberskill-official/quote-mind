"""DM-01 QuoteRecord and the approval state machine (TASK-080; frozen, parent 12.9)."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from .common import Channel, Language


class Status(str, Enum):
    RECEIVED = "received"
    PARSING = "parsing"
    MATCHING = "matching"
    PRICING = "pricing"
    DRAFTING = "drafting"
    VALIDATING = "validating"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    DISPATCHING = "dispatching"
    SENT = "sent"
    REJECTED = "rejected"
    REVISING = "revising"
    NEEDS_CLARIFICATION = "needs_clarification"
    NEEDS_MANUAL = "needs_manual"
    FAILED_INTAKE = "failed_intake"
    FAILED_PARSE = "failed_parse"
    FAILED_PRICE = "failed_price"
    FAILED_DRAFT = "failed_draft"
    CRITIC_FAILED = "critic_failed"
    FAILED_DISPATCH = "failed_dispatch"


# Frozen transition table (parent 5.2 / 12.9). A source status maps to the set of
# statuses it may legally move to. Statuses absent as keys are terminal.
LEGAL_TRANSITIONS: dict[Status, set[Status]] = {
    Status.RECEIVED: {Status.PARSING, Status.FAILED_INTAKE},
    Status.PARSING: {Status.MATCHING, Status.NEEDS_CLARIFICATION, Status.FAILED_PARSE},
    Status.MATCHING: {Status.PRICING},
    Status.PRICING: {Status.DRAFTING, Status.FAILED_PRICE},
    Status.DRAFTING: {Status.VALIDATING, Status.FAILED_DRAFT, Status.NEEDS_MANUAL},
    Status.VALIDATING: {Status.PENDING_APPROVAL, Status.CRITIC_FAILED},
    Status.PENDING_APPROVAL: {Status.APPROVED, Status.REJECTED, Status.REVISING},
    Status.REVISING: {Status.DRAFTING, Status.NEEDS_MANUAL},
    Status.APPROVED: {Status.DISPATCHING},
    Status.DISPATCHING: {Status.SENT, Status.FAILED_DISPATCH},
}

TERMINAL_STATES: frozenset[Status] = frozenset(
    status for status in Status if not LEGAL_TRANSITIONS.get(status)
)


class IllegalTransitionError(ValueError):
    """Raised when a status transition is not permitted by LEGAL_TRANSITIONS."""

    def __init__(self, current: Status, target: Status) -> None:
        super().__init__(f"Illegal quote status transition: {current.value} -> {target.value}")
        self.current = current
        self.target = target


def can_transition(current: Status, target: Status) -> bool:
    return target in LEGAL_TRANSITIONS.get(current, set())


def assert_transition(current: Status, target: Status) -> Status:
    """Return target if the transition is legal, else raise IllegalTransitionError."""
    if not can_transition(current, target):
        raise IllegalTransitionError(current, target)
    return target


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QuoteRecord(BaseModel):
    """DM-01: durable quote row (Tablestore qm_quotes, pk quote_id)."""

    quote_id: str
    quote_number: str
    status: Status
    channel: Channel
    source_uri: str | None = None
    customer_id: str | None = None
    language: Language
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    revision: int = 0
    flags: list[str] = Field(default_factory=list)
    totals_json: dict[str, Any] | None = None
    batch_id: str | None = None
    sha256_payload: str | None = None
    actor_last: str | None = None
