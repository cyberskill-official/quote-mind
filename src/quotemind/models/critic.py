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
    # TASK-073: the model's account of the verdict above - written *after* it, from it, and unable to
    # change it. Optional because it is an aid: if the call fails the quote is unaffected and the
    # gate still shows the flags and the diffs, which are the parts that carry authority.
    narrative: BilingualText | None = None
