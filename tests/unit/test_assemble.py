"""FR-060 quote assembly + the pricing -> assembly -> critic -> render chain, offline."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from quotemind.models import (
    BilingualText,
    CatalogProduct,
    Category,
    QuoteTerms,
    StockStatus,
    Tier,
)
from quotemind.pricing import vat_policy_note
from quotemind.quote import AssemblyLine, assemble_quote, run_critic
from quotemind.quote.assemble import LEAD_TIME, VAT_EXCLUDED_CATEGORY
from quotemind.quote.render import render_html

_ON = date(2026, 7, 11)


def _product(
    sku: str,
    category: Category,
    name_vi: str,
    name_en: str,
    list_p: int,
    dealer_p: int,
    cost_p: int,
    *,
    vat: int = 8,
    stock: StockStatus = StockStatus.IN_STOCK,
) -> CatalogProduct:
    return CatalogProduct(
        sku=sku,
        brand="Dell",
        category=category,
        name=BilingualText(vi=name_vi, en=name_en),
        unit="cái",
        list_price_vnd=list_p,
        dealer_price_vnd=dealer_p,
        cost_price_vnd=cost_p,
        vat_rate=vat,
        stock_status=stock,
        lead_time_days=7,
        warranty_months=12,
    )


def _terms() -> QuoteTerms:
    return QuoteTerms(
        payment=BilingualText(vi="Thanh toán trong 30 ngày", en="Payment within 30 days"),
        delivery=BilingualText(vi="Giao hàng trong 7 ngày", en="Delivery within 7 days"),
        warranty=BilingualText(vi="Bảo hành 12 tháng", en="12 months warranty"),
    )


def _assemble(lines: list[AssemblyLine], **over: Any):
    kwargs: dict[str, Any] = {
        "quote_id": "01JQUOTEEXAMPLE00000000000",
        "quote_number": "QM-2026-0100",
        "seller_block": {
            "name": "CyberSkill JSC",
            "mst": "0312345678",
            "bank": {
                "bank": "ACB",
                "beneficiary": "CS",
                "account": "878196868",
                "swift": "ASCBVNVX",
            },
        },
        "customer_block": {"name": "Công ty ABC"},
        "date": "2026-07-11",
        "validity_days": 14,
        "lines": lines,
        "terms": _terms(),
        "notes": BilingualText(vi="Cảm ơn quý khách", en="Thank you"),
        "on_date": _ON,
    }
    kwargs.update(over)
    return assemble_quote(**kwargs)


def test_assemble_then_critic_passes_end_to_end() -> None:
    lines = [
        AssemblyLine(
            product=_product(
                "DL-LAT",
                Category.LAPTOP,
                "Laptop Dell Latitude",
                "Dell Latitude laptop",
                20_000_000,
                18_000_000,
                15_000_000,
            ),
            qty=Decimal(10),
            tier=Tier.DEALER,
        ),
        AssemblyLine(
            product=_product(
                "DL-MON",
                Category.MONITOR,
                "Màn hình Dell 27 inch",
                "Dell 27 inch monitor",
                6_500_000,
                5_800_000,
                4_800_000,
            ),
            qty=Decimal(5),
            tier=Tier.PROJECT,
        ),
    ]
    quote = _assemble(lines, project_discount_pct=5.0, fx_usd_vnd=25_400)

    # Numbers come straight from the pricing engine.
    assert quote.lines[0].unit_price_vnd == 18_000_000  # dealer price
    assert quote.lines[0].line_total_vnd == 180_000_000
    assert quote.lines[0].vat_amount_vnd == 14_400_000  # 8%
    assert quote.lines[1].unit_price_vnd == 5_510_000  # 5,800,000 x 0.95 project discount
    assert quote.subtotal_vnd == 207_550_000
    assert quote.total_vnd == 224_154_000
    assert quote.total_in_words_vi  # bang chu populated
    assert quote.usd_reference is not None and quote.usd_reference.rate == 25_400

    # End to end: assembly and the critic recompute agree by construction.
    report = run_critic(quote)
    assert report.recompute_diffs == []
    assert report.passed is True

    # And it renders with the grand total and quote number.
    html = render_html(quote, vat_policy_note=vat_policy_note(_ON))
    assert "224.154.000 đ" in html
    assert "QM-2026-0100" in html


def test_flags_vat_excluded_and_lead_time() -> None:
    lines = [
        AssemblyLine(
            product=_product(
                "TEL-1",
                Category.TELECOM_SERVICE,
                "Dịch vụ viễn thông",
                "Telecom service",
                1_000_000,
                1_000_000,
                500_000,
            ),
            qty=Decimal(1),
            tier=Tier.END_CUSTOMER,
        ),
        AssemblyLine(
            product=_product(
                "OOS-1",
                Category.LAPTOP,
                "Laptop hết hàng",
                "Out-of-stock laptop",
                10_000_000,
                9_000_000,
                7_000_000,
                stock=StockStatus.OUT_OF_STOCK,
            ),
            qty=Decimal(1),
            tier=Tier.DEALER,
        ),
    ]
    quote = _assemble(lines)
    assert quote.lines[0].vat_rate == 10  # telecom_service forced to the standard rate (FR-052)
    assert VAT_EXCLUDED_CATEGORY in quote.flags
    assert LEAD_TIME in quote.flags


def test_nl_fields_default_to_catalog() -> None:
    product = _product(
        "DL-1", Category.LAPTOP, "Laptop Dell", "Dell laptop", 20_000_000, 18_000_000, 15_000_000
    )
    quote = _assemble([AssemblyLine(product=product, qty=Decimal(1), tier=Tier.DEALER)])
    assert quote.lines[0].description.vi == "Laptop Dell"
    assert quote.lines[0].unit.vi == "cái"
