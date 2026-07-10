"""DM-14 TraceStep."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class TraceStep(BaseModel):
    """DM-14: one ordered step in a quote's reasoning trace."""

    model_config = ConfigDict(protected_namespaces=())

    seq: int
    agent: str
    action: str
    tool: str | None = None
    model: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: Decimal = Decimal("0")
    duration_ms: int = 0
    summary: str
    memory_ids: list[str] = Field(default_factory=list)
