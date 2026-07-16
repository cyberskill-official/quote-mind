"""Quote numbering (TASK-062).

Frozen format ``QM-YYYY-NNNN`` (section 12). These helpers are pure: the per-year sequence itself
comes from a Tablestore atomic counter row (qm_counters) at runtime; here we only format, parse, and
validate, so the format stays testable offline and in one place.
"""

from __future__ import annotations

import re

PREFIX = "QM"
_PATTERN = re.compile(r"^QM-(?P<year>\d{4})-(?P<seq>\d{4,})$")


def format_quote_number(year: int, seq: int) -> str:
    """Render ``QM-YYYY-NNNN``; the sequence is zero-padded to 4 digits (wider only past 9999)."""
    if not 0 <= year <= 9999:
        raise ValueError(f"year out of range for QM-YYYY-NNNN: {year}")
    if seq < 1:
        raise ValueError(f"sequence must be >= 1: {seq}")
    return f"{PREFIX}-{year:04d}-{seq:04d}"


def parse_quote_number(value: str) -> tuple[int, int]:
    """Return ``(year, seq)`` for a valid quote number, else raise ValueError."""
    match = _PATTERN.match(value)
    if match is None:
        raise ValueError(f"not a QM-YYYY-NNNN quote number: {value!r}")
    return int(match.group("year")), int(match.group("seq"))


def is_valid_quote_number(value: str) -> bool:
    """True when ``value`` matches the frozen QM-YYYY-NNNN format."""
    return _PATTERN.match(value) is not None
