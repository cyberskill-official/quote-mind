"""Deterministic .xlsx RFQ extraction (TASK-033).

openpyxl only, no LLM reads numeric cells. Header-row detection fuzzy-matches the Vietnamese
and English column names; quantities are read straight from the cells. LLM normalization of
genuinely ambiguous headers is an enhancement handled later in the agent path.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

import openpyxl

from ..models import Buyer, Language, RFQExtraction, RFQLine

_DESCRIPTION_HEADERS = {
    "tên hàng",
    "tên hàng hóa",
    "tên hàng hoá",
    "tên sản phẩm",
    "mô tả",
    "mô tả hàng hóa",
    "mặt hàng",
    "sản phẩm",
    "hàng hóa",
    "hàng hoá",
    "description",
    "item",
}
_QUANTITY_HEADERS = {"số lượng", "so luong", "sl", "qty", "quantity"}
_UNIT_HEADERS = {"đvt", "dvt", "đơn vị", "đơn vị tính", "unit", "uom"}
_MAX_HEADER_SCAN = 15
_VN_CHARS = set("ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ")


class HeaderNotFoundError(ValueError):
    """Raised when a header row with both a description and a quantity column is not found."""


def _norm(value: object) -> str:
    return " ".join(str(value).strip().lower().split()) if value is not None else ""


def _match(header: str, aliases: set[str]) -> bool:
    return header in aliases or any(alias in header for alias in aliases)


def _language_of(text: str) -> Language:
    return Language.VI if any(char in _VN_CHARS for char in text.lower()) else Language.EN


def _cell(row: tuple[Any, ...], index: int | None) -> Any:
    if index is None or index >= len(row):
        return None
    return row[index]


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(int(value))) if value.is_integer() else Decimal(str(value))
    text = str(value).strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _find_header(rows: list[tuple[Any, ...]]) -> tuple[int, dict[str, int]]:
    for index, row in enumerate(rows[:_MAX_HEADER_SCAN]):
        columns: dict[str, int] = {}
        for col, cell in enumerate(row):
            header = _norm(cell)
            if not header:
                continue
            if "description" not in columns and _match(header, _DESCRIPTION_HEADERS):
                columns["description"] = col
            elif "quantity" not in columns and _match(header, _QUANTITY_HEADERS):
                columns["quantity"] = col
            elif "unit" not in columns and _match(header, _UNIT_HEADERS):
                columns["unit"] = col
        if "description" in columns and "quantity" in columns:
            return index, columns
    raise HeaderNotFoundError("no header row with description and quantity columns")


def parse_excel(data: bytes) -> RFQExtraction:
    """Parse an .xlsx RFQ into an RFQExtraction (DM-03). Quantities come straight from cells."""
    workbook = openpyxl.load_workbook(BytesIO(data), data_only=True, read_only=True)
    rows: list[tuple[Any, ...]] = list(workbook.active.iter_rows(values_only=True))
    header_index, columns = _find_header(rows)

    lines: list[RFQLine] = []
    languages: list[Language] = []
    for row in rows[header_index + 1 :]:
        description = str(_cell(row, columns["description"]) or "").strip()
        quantity = _to_decimal(_cell(row, columns["quantity"]))
        unit = str(_cell(row, columns.get("unit")) or "").strip()
        if not description and quantity is None:
            continue
        raw_text = " | ".join("" if cell is None else str(cell) for cell in row).strip()
        lines.append(
            RFQLine(
                raw_text=raw_text,
                description_normalized=description,
                quantity=quantity,
                unit=unit,
                unit_original=unit,
                confidence=1.0,
            )
        )
        languages.append(_language_of(description))

    return RFQExtraction(buyer=Buyer(), lines=lines, language_per_line=languages)
