"""DM-05 CatalogProduct and DM-06 CustomerProfile."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .common import BilingualText, Category, Currency, Language, StockStatus, Tier


class CatalogProduct(BaseModel):
    """DM-05: KnowledgeStore tenant catalog, document_id = sku."""

    sku: str
    brand: str
    category: Category
    name: BilingualText
    specs: dict[str, Any] = Field(default_factory=dict)
    unit: str
    list_price_vnd: int
    dealer_price_vnd: int
    cost_price_vnd: int
    vat_rate: int
    stock_status: StockStatus
    lead_time_days: int
    warranty_months: int
    text: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CustomerProfile(BaseModel):
    """DM-06: KnowledgeStore tenant customers."""

    customer_id: str
    name: str
    mst: str | None = None
    emails: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    tier: Tier
    project_discount_pct: float = 0.0
    preferred_currency: Currency = Currency.VND
    preferred_language: Language = Language.VI
    address: str | None = None
    contact: str | None = None
