"""Quote assembly and validation layer. Currently the deterministic critic core (EP-07)."""

from __future__ import annotations

from .assemble import AssemblyLine, assemble_quote
from .critic import (
    BILINGUAL_NUMBER_MISMATCH,
    MARGIN_BELOW_FLOOR,
    MISSING_MANDATORY_FIELDS,
    MOJIBAKE,
    NEEDS_CONFIRMATION,
    RECOMPUTE_MISMATCH,
    UNKNOWN_CUSTOMER,
    VALIDITY_OUT_OF_BOUNDS,
    bilingual_number_mismatches,
    mojibake_fields,
    policy_flags,
    recompute_diffs,
    run_critic,
)
from .numbering import format_quote_number, is_valid_quote_number, parse_quote_number

__all__ = [
    "BILINGUAL_NUMBER_MISMATCH",
    "AssemblyLine",
    "MARGIN_BELOW_FLOOR",
    "MISSING_MANDATORY_FIELDS",
    "MOJIBAKE",
    "NEEDS_CONFIRMATION",
    "RECOMPUTE_MISMATCH",
    "UNKNOWN_CUSTOMER",
    "VALIDITY_OUT_OF_BOUNDS",
    "assemble_quote",
    "bilingual_number_mismatches",
    "format_quote_number",
    "is_valid_quote_number",
    "mojibake_fields",
    "parse_quote_number",
    "policy_flags",
    "recompute_diffs",
    "run_critic",
]
