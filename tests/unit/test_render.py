"""TASK-090 bilingual HTML render (Appendix C). Deterministic; asserts byte-exact Vietnamese."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from quotemind.models import (
    BilingualText,
    LineSource,
    MarginInfo,
    Quote,
    QuoteLine,
    QuoteTerms,
    UsdReference,
    VatBreakdownEntry,
)
from quotemind.pricing import vat_policy_note
from quotemind.quote.render import render_html

_VAT_NOTE = vat_policy_note(date(2026, 7, 11))


def _quote() -> Quote:
    return Quote(
        quote_id="01J8ZQEXAMPLE0000000000000",
        quote_number="QM-2026-0042",
        seller_block={
            "name": "CyberSkill JSC",
            "address": "207A Nguyễn Văn Thủ, Tân Định, TP.HCM",
            "mst": "0312345678",
            "phone": "(+84)906 878 091",
            "email": "info@cyberskill.world",
            "bank": {
                "bank": "ACB",
                "beneficiary": "CTY CP TV VA PT GIAI PHAP PHAN MEM CYBERSKILL",
                "account": "878196868",
                "swift": "ASCBVNVX",
            },
        },
        customer_block={"name": "Công ty ABC", "address": "Hà Nội", "mst": "0100000000"},
        date="2026-07-11",
        validity_days=14,
        lines=[
            QuoteLine(
                idx=1,
                sku="DL-5450",
                description=BilingualText(vi="Laptop Dell Latitude 5450", en="Dell Latitude 5450"),
                unit=BilingualText(vi="cái", en="unit"),
                qty=Decimal(10),
                unit_price_vnd=1_000_000,
                line_total_vnd=10_000_000,
                vat_rate=8,
                vat_amount_vnd=800_000,
                note=BilingualText(vi="Giao trong 2 tuần", en="Delivery in 2 weeks"),
                source=LineSource.MATCHED,
            ),
            QuoteLine(
                idx=2,
                sku=None,
                description=BilingualText(vi="Dịch vụ lắp đặt R&D", en="R&D installation service"),
                unit=BilingualText(vi="gói", en="package"),
                qty=Decimal(1),
                unit_price_vnd=1_000_000,
                line_total_vnd=1_000_000,
                vat_rate=10,
                vat_amount_vnd=100_000,
                source=LineSource.MATCHED,
            ),
        ],
        subtotal_vnd=11_000_000,
        vat_breakdown=[
            VatBreakdownEntry(rate=8, base=10_000_000, amount=800_000),
            VatBreakdownEntry(rate=10, base=1_000_000, amount=100_000),
        ],
        total_vnd=11_900_000,
        total_in_words_vi="Mười một triệu chín trăm nghìn đồng",
        usd_reference=UsdReference(
            rate=25_400, subtotal=Decimal("433.07"), total=Decimal("468.50"), as_of="2026-07-11"
        ),
        terms=QuoteTerms(
            payment=BilingualText(vi="Thanh toán trong 30 ngày", en="Payment within 30 days"),
            delivery=BilingualText(vi="Giao hàng trong 7 ngày", en="Delivery within 7 days"),
            warranty=BilingualText(vi="Bảo hành 12 tháng", en="12 months warranty"),
        ),
        notes=BilingualText(vi="Cảm ơn quý khách", en="Thank you"),
        margin=MarginInfo(blended_pct=18.0, per_line=[20.0, 15.0]),
    )


def test_render_html_is_bilingual_and_byte_exact() -> None:
    html = render_html(_quote(), vat_policy_note=_VAT_NOTE, fx_note="FX @ 25.400 (2026-07-11)")

    # Vietnamese primary strings, byte-exact.
    for vi in ["BÁO GIÁ", "Mô tả hàng hóa, dịch vụ", "Đơn giá (VNĐ)", "Bằng chữ", "Hiệu lực"]:
        assert vi in html
    assert "Mười một triệu chín trăm nghìn đồng" in html
    assert "Bằng chữ".encode() in html.encode()  # explicit byte-level check

    # English secondary strings.
    for en in ["QUOTATION", "Description", "In words", "Unit price"]:
        assert en in html


def test_render_html_numbers_and_vat_breakdown() -> None:
    html = render_html(_quote(), vat_policy_note=_VAT_NOTE)
    assert "11.000.000 đ" in html  # subtotal, dot thousands (TASK-055)
    assert "11.900.000 đ" in html  # grand total
    assert "Thuế GTGT 8% / VAT 8%" in html
    assert "Thuế GTGT 10% / VAT 10%" in html
    assert "$468.50" in html  # USD reference line


def test_render_html_bank_block_and_brand_and_escaping() -> None:
    html = render_html(_quote(), vat_policy_note=_VAT_NOTE)
    # Bank block (Appendix C section 7).
    assert "ASCBVNVX" in html
    assert "878196868" in html
    # CyberSkill brand palette.
    assert "#45210E" in html and "#F4BA17" in html
    # Autoescape turns the "&" in the R&D line into a safe entity.
    assert "R&amp;D" in html
    assert "R&D installation" not in html  # the raw ampersand must not survive
