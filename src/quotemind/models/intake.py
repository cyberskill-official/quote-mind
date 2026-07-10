"""DM-02 IntakeResult."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from .common import DocType, Language, Urgency


class CustomerMatch(BaseModel):
    customer_id: str | None = None
    method: str
    confidence: float


class EmailMeta(BaseModel):
    from_addr: str | None = None
    subject: str | None = None
    received_at: datetime | None = None


class IntakeResult(BaseModel):
    """DM-02: detected language, doc type, urgency, and a customer match hint."""

    language: Language
    doc_type: DocType
    urgency: Urgency
    customer_match: CustomerMatch
    email_meta: EmailMeta | None = None
