"""DM-03 RFQExtraction and RFQLine."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from .common import Language


class Buyer(BaseModel):
    company: str | None = None
    mst: str | None = None
    contact: str | None = None
    email: str | None = None


class SourceSpan(BaseModel):
    page: int | None = None
    start: int
    end: int


class RFQLine(BaseModel):
    raw_text: str
    description_normalized: str
    quantity: Decimal | None = None
    unit: str
    unit_original: str
    specs: dict[str, Any] = Field(default_factory=dict)
    requested_delivery: str | None = None
    confidence: float
    source_span: SourceSpan | None = None


class RFQExtraction(BaseModel):
    """DM-03: structured RFQ content extracted from any input channel."""

    buyer: Buyer
    lines: list[RFQLine] = Field(default_factory=list)
    language_per_line: list[Language] = Field(default_factory=list)
    notes_raw: str | None = None
