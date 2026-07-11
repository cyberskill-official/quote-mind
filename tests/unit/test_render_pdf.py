"""FR-090: WeasyPrint renders a real PDF and copy-pasted text keeps its Vietnamese diacritics."""

from __future__ import annotations

from datetime import date

import pypdfium2
import pytest

from quotemind.pricing import vat_policy_note
from quotemind.quote.render import render_pdf

from .test_render import _quote

_ON = date(2026, 7, 11)


def _squash(text: str) -> str:
    """Drop whitespace so table wrapping cannot break a substring check."""
    return "".join(text.split())


def _text_of(pdf: bytes) -> str:
    document = pypdfium2.PdfDocument(pdf)
    try:
        return "\n".join(page.get_textpage().get_text_range() for page in document)
    finally:
        document.close()


@pytest.fixture(scope="module")
def extracted() -> str:
    pdf = render_pdf(_quote(), vat_policy_note=vat_policy_note(_ON))
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 2000
    return _text_of(pdf)


def test_extracted_text_preserves_diacritics_byte_exact(extracted: str) -> None:
    # FR-090 AC: "copy-pasted text preserves diacritics".
    squashed = _squash(extracted)
    for vietnamese in [
        "BÁO GIÁ",
        "Mô tả hàng hóa, dịch vụ",
        "Đơn giá (VNĐ)",
        "Bằng chữ",
        "Mười một triệu chín trăm nghìn đồng",  # the bang chu line
        "Laptop Dell Latitude 5450",
        "Dịch vụ lắp đặt R&D",
        "Thanh toán trong 30 ngày",
        "Cảm ơn quý khách",
    ]:
        assert _squash(vietnamese) in squashed, f"lost in the PDF: {vietnamese!r}"


def test_pdf_carries_the_money_the_vat_lines_and_the_bank_block(extracted: str) -> None:
    squashed = _squash(extracted)
    assert _squash("11.900.000 đ") in squashed  # grand total, dot thousands
    assert _squash("Thuế GTGT 8% / VAT 8%") in squashed
    assert _squash("Thuế GTGT 10% / VAT 10%") in squashed
    assert "ASCBVNVX" in squashed  # bank block (Appendix C section 7)
    assert "QUOTATION" in squashed  # bilingual header
