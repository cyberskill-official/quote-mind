"""DM-13 EvalCase."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class EvalLabelLine(BaseModel):
    description_canon: str
    sku: str
    qty: Decimal


class EvalLabels(BaseModel):
    lines: list[EvalLabelLine] = Field(default_factory=list)
    customer_id: str | None = None
    expected_flags: list[str] = Field(default_factory=list)


class EvalInput(BaseModel):
    file: str | None = None
    text: str | None = None


class EvalCase(BaseModel):
    """DM-13: one labeled RFQ case in the evaluation dataset."""

    case_id: str
    input: EvalInput
    labels: EvalLabels
    tags: list[str] = Field(default_factory=list)
