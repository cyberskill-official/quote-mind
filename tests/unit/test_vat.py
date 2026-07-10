"""FR-052: Vietnam 2026 VAT rules and the policy note."""

from __future__ import annotations

from datetime import date

import pytest

from quotemind.models import BilingualText, CatalogProduct, Category, StockStatus
from quotemind.pricing import (
    is_excluded_category,
    is_reduction_active,
    vat_policy_note,
    vat_rate_for,
)

_BT = BilingualText(vi="x", en="x")
_IN_WINDOW = date(2026, 7, 11)
_AFTER_WINDOW = date(2027, 1, 1)


def _product(vat_rate: int = 8, category: Category = Category.LAPTOP) -> CatalogProduct:
    return CatalogProduct(
        sku="SKU",
        brand="B",
        category=category,
        name=_BT,
        unit="u",
        list_price_vnd=1,
        dealer_price_vnd=1,
        cost_price_vnd=1,
        vat_rate=vat_rate,
        stock_status=StockStatus.IN_STOCK,
        lead_time_days=0,
        warranty_months=0,
    )


def test_reduction_window() -> None:
    assert is_reduction_active(_IN_WINDOW)
    assert not is_reduction_active(_AFTER_WINDOW)
    assert not is_reduction_active(date(2025, 1, 1))


def test_it_goods_8_percent_in_window() -> None:
    assert vat_rate_for(_product(vat_rate=8), _IN_WINDOW) == 8


def test_it_goods_revert_to_10_after_window() -> None:
    assert vat_rate_for(_product(vat_rate=8), _AFTER_WINDOW) == 10
    assert vat_rate_for(_product(vat_rate=8), _AFTER_WINDOW, default_override=8) == 8


def test_telecom_forced_to_10_and_flagged() -> None:
    product = _product(vat_rate=8, category=Category.TELECOM_SERVICE)
    assert vat_rate_for(product, _IN_WINDOW) == 10
    assert is_excluded_category(product)
    assert not is_excluded_category(_product())


def test_non_reduced_rate_unchanged() -> None:
    assert vat_rate_for(_product(vat_rate=5), _AFTER_WINDOW) == 5
    assert vat_rate_for(_product(vat_rate=10), _IN_WINDOW) == 10
    assert vat_rate_for(_product(vat_rate=0), _AFTER_WINDOW) == 0


def test_invalid_rate_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported VAT rate"):
        vat_rate_for(_product(vat_rate=7), _IN_WINDOW)


def test_policy_note_switches_with_date() -> None:
    active = vat_policy_note(_IN_WINDOW)
    expired = vat_policy_note(_AFTER_WINDOW)
    assert "8%" in active.vi
    assert "8%" in active.en
    assert "10%" in expired.vi
    assert "10%" in expired.en
