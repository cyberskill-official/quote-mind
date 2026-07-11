"""FR-033 deterministic Excel extraction and FR-034 validation gate."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from io import BytesIO

import openpyxl
import pytest

from quotemind.models import Language
from quotemind.parsing import (
    HeaderNotFoundError,
    needs_clarification,
    parse_excel,
    validation_reasons,
)


def _xlsx(rows: Sequence[Sequence[object]]) -> bytes:
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    for row in rows:
        worksheet.append(list(row))
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_vietnamese_headers_below_a_title_row() -> None:
    data = _xlsx(
        [
            ["BÁO GIÁ THIẾT BỊ"],  # title row above the header
            ["STT", "Tên hàng", "Số lượng", "ĐVT"],
            [1, "Laptop Dell Latitude 5450", 20, "cái"],
            [2, "Màn hình Dell 27 inch", 20, "cái"],
        ]
    )
    extraction = parse_excel(data)
    assert len(extraction.lines) == 2
    assert extraction.lines[0].description_normalized == "Laptop Dell Latitude 5450"
    assert extraction.lines[0].unit == "cái"
    assert extraction.lines[0].unit_original == "cái"
    assert extraction.lines[0].confidence == 1.0
    # Per-line language is a deterministic diacritic check (FR-035): the ASCII brand/model line
    # reads EN, the line carrying Vietnamese diacritics reads VI. The drafter refines later.
    assert extraction.language_per_line == [Language.EN, Language.VI]


def test_quantities_match_labels_exactly() -> None:
    # FR-033 AC: quantity fields match labels 100%.
    data = _xlsx(
        [
            ["Mô tả", "Số lượng"],
            ["Switch Cisco Catalyst 9200", 4],
            ["Cáp mạng Cat6 (cuộn 305m)", 12.5],
            ["Ổ cứng SSD Samsung 1TB", 3.0],  # float integer normalizes to Decimal("3")
        ]
    )
    extraction = parse_excel(data)
    assert [line.quantity for line in extraction.lines] == [
        Decimal("4"),
        Decimal("12.5"),
        Decimal("3"),
    ]


def test_english_headers_and_blank_rows_skipped() -> None:
    data = _xlsx(
        [
            ["No", "Description", "Qty", "Unit"],
            [1, "Dell Latitude 5450 laptop", 15, "unit"],
            [None, None, None, None],  # fully blank -> skipped
            [2, "Logitech wireless mouse", 15, "unit"],
        ]
    )
    extraction = parse_excel(data)
    assert len(extraction.lines) == 2
    assert extraction.lines[0].quantity == Decimal("15")
    assert extraction.language_per_line == [Language.EN, Language.EN]


def test_missing_header_row_raises() -> None:
    with pytest.raises(HeaderNotFoundError):
        parse_excel(_xlsx([["foo", "bar"], ["a", "b"]]))


def test_gate_flags_empty_extraction() -> None:
    header_only = parse_excel(_xlsx([["Mô tả", "Số lượng"]]))
    assert header_only.lines == []
    assert validation_reasons(header_only) == ["NO_LINE_ITEMS"]
    assert needs_clarification(header_only) is True


def test_gate_flags_missing_quantity_but_passes_complete_lines() -> None:
    flagged = parse_excel(_xlsx([["Mô tả", "Số lượng"], ["Mặt hàng thiếu số lượng", None]]))
    assert validation_reasons(flagged) == ["MISSING_QUANTITY"]

    complete = parse_excel(_xlsx([["Mô tả", "Số lượng"], ["Bàn phím cơ", 5]]))
    assert validation_reasons(complete) == []
    assert needs_clarification(complete) is False
