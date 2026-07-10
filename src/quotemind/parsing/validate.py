"""Extraction validation gate (FR-034).

Deterministic reason codes for an RFQExtraction that must not proceed to matching. The pipeline
maps a non-empty result to quote status ``needs_clarification`` (DM-14 status enum, section 12.7).
"""

from __future__ import annotations

from ..models import RFQExtraction

NO_LINE_ITEMS = "NO_LINE_ITEMS"
MISSING_DESCRIPTION = "MISSING_DESCRIPTION"
MISSING_QUANTITY = "MISSING_QUANTITY"


def validation_reasons(extraction: RFQExtraction) -> list[str]:
    """Reason codes forcing needs_clarification (FR-034). Empty list means the extraction passes."""
    if not extraction.lines:
        return [NO_LINE_ITEMS]
    reasons: list[str] = []
    for line in extraction.lines:
        if not line.description_normalized.strip() and MISSING_DESCRIPTION not in reasons:
            reasons.append(MISSING_DESCRIPTION)
        if line.quantity is None and MISSING_QUANTITY not in reasons:
            reasons.append(MISSING_QUANTITY)
    return reasons


def needs_clarification(extraction: RFQExtraction) -> bool:
    """True when the extraction fails the FR-034 gate and must not proceed to matching."""
    return bool(validation_reasons(extraction))
