"""FR-050..054: deterministic pricing functions."""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from quotemind.models import (
    BilingualText,
    CatalogProduct,
    Category,
    LineSource,
    QuoteLine,
    StockStatus,
    Tier,
)
from quotemind.pricing import (
    blended_margin,
    format_usd,
    format_vnd,
    line_total,
    margin,
    quote_totals,
    to_usd,
    unit_price,
    vat_amount,
)

_BT = BilingualText(vi="x", en="x")


def _product(
    list_price: int = 32_000_000,
    dealer_price: int = 30_000_000,
    cost: int = 28_000_000,
    vat_rate: int = 8,
    category: Category = Category.LAPTOP,
) -> CatalogProduct:
    return CatalogProduct(
        sku="SKU",
        brand="Dell",
        category=category,
        name=_BT,
        unit="chiếc",
        list_price_vnd=list_price,
        dealer_price_vnd=dealer_price,
        cost_price_vnd=cost,
        vat_rate=vat_rate,
        stock_status=StockStatus.IN_STOCK,
        lead_time_days=7,
        warranty_months=36,
    )


def _line(line_total_vnd: int, vat_rate: int, vat_amount_vnd: int) -> QuoteLine:
    return QuoteLine(
        idx=1,
        description=_BT,
        unit=_BT,
        qty=Decimal(1),
        unit_price_vnd=line_total_vnd,
        line_total_vnd=line_total_vnd,
        vat_rate=vat_rate,
        vat_amount_vnd=vat_amount_vnd,
        source=LineSource.MATCHED,
    )


def test_unit_price_by_tier() -> None:
    product = _product()
    assert unit_price(product, Tier.END_CUSTOMER) == Decimal(32_000_000)
    assert unit_price(product, Tier.DEALER) == Decimal(30_000_000)
    assert unit_price(product, Tier.PROJECT, project_discount_pct=Decimal(5)) == Decimal(28_500_000)


def test_unit_price_default_project_discount() -> None:
    assert unit_price(_product(), Tier.PROJECT) == Decimal(29_100_000)  # 30M * (1 - 3/100)


def test_unit_price_missing_dealer_falls_back_to_list() -> None:
    product = _product(dealer_price=0)
    assert unit_price(product, Tier.DEALER) == Decimal(32_000_000)
    assert unit_price(product, Tier.PROJECT, project_discount_pct=Decimal(0)) == Decimal(32_000_000)


def test_line_total_with_and_without_discount() -> None:
    assert line_total(Decimal(20), Decimal(30_000_000)) == Decimal(600_000_000)
    assert line_total(Decimal(20), Decimal(30_000_000), Decimal(10)) == Decimal(540_000_000)


def test_vat_amount() -> None:
    assert vat_amount(Decimal(600_000_000), 8) == Decimal(48_000_000)
    assert vat_amount(Decimal(600_000_000), 0) == Decimal(0)


def test_margin_and_blended() -> None:
    assert margin(Decimal(100), Decimal(80)) == Decimal(20)
    assert margin(Decimal(0), Decimal(80)) == Decimal(0)
    assert blended_margin([(Decimal(100), Decimal(80)), (Decimal(100), Decimal(90))]) == Decimal(15)
    assert blended_margin([(Decimal(0), Decimal(0))]) == Decimal(0)


def test_quote_totals_groups_by_rate() -> None:
    lines = [
        _line(600_000_000, 8, 48_000_000),
        _line(100_000_000, 10, 10_000_000),
        _line(200_000_000, 8, 16_000_000),
    ]
    totals = quote_totals(lines)
    assert totals.subtotal_vnd == 900_000_000
    assert totals.total_vnd == 974_000_000
    rates = {entry.rate: (entry.base, entry.amount) for entry in totals.vat_breakdown}
    assert rates[8] == (800_000_000, 64_000_000)
    assert rates[10] == (100_000_000, 10_000_000)


def test_to_usd_and_formatting() -> None:
    assert to_usd(Decimal(648_000_000), 25_400) == Decimal("25511.81")
    assert format_vnd(Decimal(1_234_567)) == "1.234.567 đ"
    assert format_usd(Decimal("25511.81")) == "$25,511.81"


@given(
    rows=st.lists(
        st.tuples(
            st.integers(min_value=0, max_value=10_000_000_000),
            st.sampled_from([0, 5, 8, 10]),
        ),
        min_size=1,
        max_size=12,
    )
)
def test_quote_totals_equals_sum_of_parts(rows: list[tuple[int, int]]) -> None:
    lines = [_line(amount, rate, int(vat_amount(amount, rate))) for amount, rate in rows]
    totals = quote_totals(lines)
    expected_subtotal = sum(amount for amount, _ in rows)
    expected_vat = sum(int(vat_amount(amount, rate)) for amount, rate in rows)
    assert totals.subtotal_vnd == expected_subtotal
    assert totals.total_vnd == expected_subtotal + expected_vat
    assert isinstance(totals.subtotal_vnd, int)
    assert isinstance(totals.total_vnd, int)
