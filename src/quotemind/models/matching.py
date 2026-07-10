"""DM-09 MatchResult."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .common import BilingualText, MatchStatus


class MatchAlternative(BaseModel):
    sku: str
    reason: BilingualText


class MatchResult(BaseModel):
    """DM-09: per-line catalog resolution with up to three alternatives."""

    line_ref: int
    status: MatchStatus
    sku: str | None = None
    match_confidence: float
    alternatives: list[MatchAlternative] = Field(default_factory=list, max_length=3)
    reason: BilingualText | None = None
