"""Quote assembly and validation layer. Currently the deterministic critic core (EP-07)."""

from __future__ import annotations

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

__all__ = [
    "BILINGUAL_NUMBER_MISMATCH",
    "MARGIN_BELOW_FLOOR",
    "MISSING_MANDATORY_FIELDS",
    "MOJIBAKE",
    "NEEDS_CONFIRMATION",
    "RECOMPUTE_MISMATCH",
    "UNKNOWN_CUSTOMER",
    "VALIDITY_OUT_OF_BOUNDS",
    "bilingual_number_mismatches",
    "mojibake_fields",
    "policy_flags",
    "recompute_diffs",
    "run_critic",
]
