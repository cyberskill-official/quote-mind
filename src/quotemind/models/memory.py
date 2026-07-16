"""DM-07 EpisodicQuoteMemory and DM-08 SOPSnippet."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from .common import BilingualText, Category, Outcome, SopTopic


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
    # TASK-048. Which goods this term is *allowed* to apply to. Empty means universal.
    #
    # This is a rule, not a similarity, and it exists because similarity got it wrong: asked for the
    # payment terms on a Dell PowerEdge server, the vector search returned "software licences and
    # implementation services: 100% before activation" (0.657) above the generic 30-day term
    # (0.617). Both mention money and both say "100%", so they sit close together in the embedding -
    # and the wrong one would have gone onto a quotation as an obligation nobody agreed to.
    #
    # Whether a payment term applies to software or to hardware is not a fuzzy question: the
    # business knows exactly. So retrieval *proposes* - it ranks within what is allowed - and this
    # field *disposes*, exactly as deterministic banding disposes of the matcher's SKU proposal.
    applies_to: list[Category] = Field(default_factory=list)


class EpisodicRecall(BaseModel):
    """TASK-045: one retrieved memory, and every term that decided where it ranked.

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
