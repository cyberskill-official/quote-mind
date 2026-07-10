"""Document parsing (EP-03). Deterministic Excel extraction plus the FR-034 validation gate.

Text/vision/PDF parsers (FR-030/031/032) call models and land with the agent path; they are not
re-exported here so the light offline install stays import-clean.
"""

from __future__ import annotations

from .excel import HeaderNotFoundError, parse_excel
from .validate import (
    MISSING_DESCRIPTION,
    MISSING_QUANTITY,
    NO_LINE_ITEMS,
    needs_clarification,
    validation_reasons,
)

__all__ = [
    "MISSING_DESCRIPTION",
    "MISSING_QUANTITY",
    "NO_LINE_ITEMS",
    "HeaderNotFoundError",
    "needs_clarification",
    "parse_excel",
    "validation_reasons",
]
