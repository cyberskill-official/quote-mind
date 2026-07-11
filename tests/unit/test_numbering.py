"""FR-062 frozen quote numbering QM-YYYY-NNNN."""

from __future__ import annotations

import pytest

from quotemind.quote import format_quote_number, is_valid_quote_number, parse_quote_number


def test_format_and_parse_roundtrip() -> None:
    assert format_quote_number(2026, 1) == "QM-2026-0001"
    assert format_quote_number(2026, 4231) == "QM-2026-4231"
    assert parse_quote_number("QM-2026-0007") == (2026, 7)


def test_sequence_beyond_9999_widens() -> None:
    assert format_quote_number(2026, 12345) == "QM-2026-12345"
    assert parse_quote_number("QM-2026-12345") == (2026, 12345)


def test_validation() -> None:
    assert is_valid_quote_number("QM-2026-0001") is True
    for bad in ["QM-26-0001", "QM-2026-1", "qm-2026-0001", "2026-0001", "QM-2026-0001x"]:
        assert is_valid_quote_number(bad) is False


def test_invalid_inputs_raise() -> None:
    with pytest.raises(ValueError):
        format_quote_number(2026, 0)
    with pytest.raises(ValueError):
        format_quote_number(10000, 1)
    with pytest.raises(ValueError):
        parse_quote_number("nope")
