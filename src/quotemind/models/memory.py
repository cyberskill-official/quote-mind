"""DM-07 EpisodicQuoteMemory and DM-08 SOPSnippet."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from .common import BilingualText, Outcome, SopTopic


class ItemBrief(BaseModel):
    sku: str
    qty: Decimal
    unit_price: int


class EpisodicQuoteMemory(BaseModel):
    """DM-07: KnowledgeStore tenant episodic:{customer_id}."""

    memory_id: str
    quote_number: str
    summary: BilingualText
    items_brief: list[ItemBrief] = Field(default_factory=list)
    outcome: Outcome
    human_edits: str | None = None
    importance: float
    created_at: datetime
    embedding: list[float] | None = None


class SOPSnippet(BaseModel):
    """DM-08: KnowledgeStore tenant sop."""

    topic: SopTopic
    text: BilingualText
    embedding: list[float] | None = None


class EpisodicRecall(BaseModel):
    """FR-045: one retrieved memory, and every term that decided where it ranked.

    The components are carried separately rather than collapsed into a single number, because a
    reviewer looking at the trace should be able to see *why* a memory surfaced - a strong match on
    an old, low-importance episode is a different claim from a weak match on last week's rejection.
    """

    memory_id: str
    quote_number: str
    summary: BilingualText
    outcome: Outcome
    similarity: float
    importance: float
    recency_decay: float
    age_days: float
    effective_score: float
