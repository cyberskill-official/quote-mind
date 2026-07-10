"""DM-11 CriticReport."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .common import BilingualText


class RecomputeDiff(BaseModel):
    field: str
    expected: str
    actual: str
    line_idx: int | None = None


class CriticReport(BaseModel):
    """DM-11: independent recomputation result plus policy flags."""

    passed: bool
    blocking: list[str] = Field(default_factory=list)
    non_blocking: list[str] = Field(default_factory=list)
    recompute_diffs: list[RecomputeDiff] = Field(default_factory=list)
    note: BilingualText
