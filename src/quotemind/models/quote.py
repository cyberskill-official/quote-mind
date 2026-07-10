"""DM-10 Quote, QuoteLine, and totals."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from .common import BilingualText, LineSource


class QuoteLine(BaseModel):
    idx: int
    sku: str | None = None
    description: BilingualText
    unit: BilingualText
    qty: Decimal
    unit_price_vnd: int
    discount_pct: float = 0.0
    line_total_vnd: int
    vat_rate: int
    vat_amount_vnd: int
    note: BilingualText | None = None
    source: LineSource


class VatBreakdownEntry(BaseModel):
    rate: int
    base: int
    amount: int


class UsdReference(BaseModel):
    rate: int
    subtotal: Decimal
    total: Decimal
    as_of: str


class QuoteTerms(BaseModel):
    payment: BilingualText
    delivery: BilingualText
    warranty: BilingualText


class MarginInfo(BaseModel):
    blended_pct: float
    per_line: list[float] = Field(default_factory=list)  # internal-only


class Quote(BaseModel):
    """DM-10: the assembled bilingual quote object rendered to PDF."""

    quote_id: str
    quote_number: str
    seller_block: dict[str, Any] = Field(default_factory=dict)
    customer_block: dict[str, Any] = Field(default_factory=dict)
    date: str
    validity_days: int
    lines: list[QuoteLine] = Field(default_factory=list)
    subtotal_vnd: int
    vat_breakdown: list[VatBreakdownEntry] = Field(default_factory=list)
    total_vnd: int
    total_in_words_vi: str
    usd_reference: UsdReference | None = None
    terms: QuoteTerms
    notes: BilingualText
    flags: list[str] = Field(default_factory=list)
    margin: MarginInfo
    revision: int = 0
