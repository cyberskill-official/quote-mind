"""AGT-04 CatalogMatcher: the LLM selection step of hybrid matching (FR-042).

Retrieval (vector + full-text) and the fusion/banding around this call are deterministic code in
quotemind.tools. This module only asks the model to pick one of a fixed candidate list, and then
*enforces* that choice against the whitelist: a SKU the model invented is discarded, never trusted.
"""

from __future__ import annotations

from agentscope.message import Msg
from pydantic import BaseModel, Field

from ..config.models import MODEL_PLANNER
from ..config.settings import Settings
from ..models import CatalogProduct
from ..prompts import MATCHER_SYS
from .model import build_agent


class MatchSelection(BaseModel):
    """The model's pick for one RFQ line. Prices are never asked for and never accepted."""

    sku: str | None = Field(default=None, description="A SKU from the candidate list, or null")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    specs_conflict: bool = False
    reason_vi: str = ""
    reason_en: str = ""


def _candidate_block(candidates: list[CatalogProduct]) -> str:
    lines = []
    for product in candidates:
        specs = ", ".join(f"{key}={value}" for key, value in sorted(product.specs.items()))
        lines.append(
            f"- SKU: {product.sku} | {product.name.vi} / {product.name.en} "
            f"| brand: {product.brand} | unit: {product.unit} | specs: {specs or 'n/a'}"
        )
    return "\n".join(lines)


async def select_sku(
    line_description: str, candidates: list[CatalogProduct], settings: Settings
) -> MatchSelection:
    """FR-042 LLM select. Returns sku=None when nothing fits or the model invents a SKU."""
    if not candidates:
        return MatchSelection(sku=None, confidence=0.0)

    agent = build_agent(
        name="matcher", sys_prompt=MATCHER_SYS, model_name=MODEL_PLANNER, settings=settings
    )
    prompt = (
        f"RFQ line:\n{line_description}\n\n"
        f"Candidates (choose exactly one SKU from this list, or null):\n"
        f"{_candidate_block(candidates)}"
    )
    reply = await agent(Msg("user", prompt, "user"), structured_model=MatchSelection)
    selection = MatchSelection.model_validate(reply.metadata)

    # Guardrail: the model may only choose from the whitelist. Anything else is treated as no match.
    allowed = {product.sku for product in candidates}
    if selection.sku is not None and selection.sku not in allowed:
        return MatchSelection(
            sku=None,
            confidence=0.0,
            reason_vi="Mô hình chọn SKU ngoài danh sách ứng viên.",
            reason_en="Model chose a SKU outside the candidate list.",
        )
    return selection
