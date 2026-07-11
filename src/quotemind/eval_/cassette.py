"""FR-123: recorded model responses, so CI can run the pipeline without a model.

A cassette is the model half of one case, frozen: the parser's RFQExtraction and, per line, the
matcher's MatchSelection and the SKUs retrieval returned. Replaying it exercises everything the
pipeline does *around* the model - the FR-034 validation gate, RRF fusion, the SKU whitelist,
assembly, VAT, the critic's recompute, the renderer - with no API key, no cost, and no flakiness.

What this does and does not prove is worth being blunt about. It cannot tell you the model got
better or worse; only the live eval (FR-121) does that. What it catches is the regression that would
otherwise ship silently: someone refactors the pricing engine, or the fusion, or the critic, and the
arithmetic quietly changes while every unit test still passes. The cassettes pin the *deterministic*
half of the pipeline to known-good output.

Cassettes are harvested from a live run's own trace (FR-111 with TRACE_CONTENT=1), so they are real
recorded responses rather than hand-written fictions of what the model might say.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ..agents.matcher import MatchSelection
from ..models import RFQExtraction

CASSETTES = Path(__file__).resolve().parents[3] / "eval" / "dataset" / "cassettes"


class LineCassette(BaseModel):
    """One line's recorded retrieval + selection."""

    vector_skus: list[str] = Field(default_factory=list)
    text_skus: list[str] = Field(default_factory=list)
    selection: MatchSelection


class Cassette(BaseModel):
    """Everything the models produced for one case."""

    case_id: str
    extraction: RFQExtraction
    lines: list[LineCassette] = Field(default_factory=list)

    @classmethod
    def load(cls, case_id: str) -> Cassette:
        return cls.model_validate_json((CASSETTES / f"{case_id}.json").read_text(encoding="utf-8"))

    def save(self) -> Path:
        CASSETTES.mkdir(parents=True, exist_ok=True)
        path = CASSETTES / f"{self.case_id}.json"
        payload: dict[str, Any] = self.model_dump(mode="json")
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )  # ensure_ascii=False: Vietnamese stays readable in the recorded fixture
        return path


def available() -> list[str]:
    """Case ids with a cassette on disk."""
    if not CASSETTES.exists():
        return []
    return sorted(path.stem for path in CASSETTES.glob("*.json"))
