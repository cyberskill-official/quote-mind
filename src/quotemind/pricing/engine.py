"""Deterministic pricing (FR-050..054).

Pure Decimal math quantized to whole đồng. No network, no LLM, no wall clock: any
date-dependent input is injected by the caller. The critic recomputes with these same
functions (D-03), so they are the single source of numeric truth.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel

from ..models import CatalogProduct, QuoteLine, Tier, VatBreakdownEntry

ZERO = Decimal(0)
_WHOLE = Decimal(1)
_CENTS = Decimal("0.01")
DEFAULT_PROJECT_DISCOUNT_PCT = Decimal(3)


def to_vnd(value: Decimal | int | str) -> Decimal:
    """Quantize to whole đồng (0 dp, round half up)."""
    return Decimal(value).quantize(_WHOLE, rounding=ROUND_HALF_UP)


class Totals(BaseModel):
    """Aggregate output of quote_totals: subtotal, per-rate VAT, and grand total (VND)."""

    subtotal_vnd: int
    vat_breakdown: list[VatBreakdownEntry]
    total_vnd: int


def unit_price(
    product: CatalogProduct,
    tier: Tier,
    project_discount_pct: Decimal | int | float = DEFAULT_PROJECT_DISCOUNT_PCT,
) -> Decimal:
    """FR-051 tiered unit price. A missing dealer price falls back to the list price."""
    list_price = Decimal(product.list_price_vnd)
    dealer_price = Decimal(product.dealer_price_vnd)
    if tier == Tier.END_CUSTOMER:
        return to_vnd(list_price)
    base = dealer_price if dealer_price > ZERO else list_price
    if tier == Tier.DEALER:
        return to_vnd(base)
    pct = Decimal(str(project_discount_pct))
    return to_vnd(base * (Decimal(100) - pct) / Decimal(100))


def line_total(
    qty: Decimal | int,
    price: Decimal | int,
    discount_pct: Decimal | int | float = 0,
) -> Decimal:
    """FR-050 line subtotal after discount, whole đồng."""
    net = Decimal(str(qty)) * Decimal(str(price)) * (Decimal(100) - Decimal(str(discount_pct)))
    return to_vnd(net / Decimal(100))


def vat_amount(base: Decimal | int, vat_rate: int) -> Decimal:
    """FR-050 VAT on a base amount, whole đồng."""
    return to_vnd(Decimal(str(base)) * Decimal(vat_rate) / Decimal(100))


def margin(sell: Decimal | int, cost: Decimal | int) -> Decimal:
    """FR-053 margin percent = (sell - cost) / sell * 100. Non-positive sell yields 0."""
    sell_d = Decimal(str(sell))
    if sell_d <= ZERO:
        return ZERO
    return (sell_d - Decimal(str(cost))) / sell_d * Decimal(100)


def blended_margin(pairs: list[tuple[Decimal | int, Decimal | int]]) -> Decimal:
    """FR-053 revenue-weighted blended margin over (sell, cost) pairs. Zero revenue yields 0."""
    total_sell = ZERO
    total_cost = ZERO
    for sell, cost in pairs:
        total_sell += Decimal(str(sell))
        total_cost += Decimal(str(cost))
    if total_sell <= ZERO:
        return ZERO
    return (total_sell - total_cost) / total_sell * Decimal(100)


def quote_totals(lines: list[QuoteLine]) -> Totals:
    """FR-050 aggregate subtotal, per-rate VAT breakdown, and grand total."""
    subtotal = ZERO
    base_by_rate: dict[int, Decimal] = {}
    vat_by_rate: dict[int, Decimal] = {}
    for line in lines:
        line_amount = Decimal(line.line_total_vnd)
        subtotal += line_amount
        base_by_rate[line.vat_rate] = base_by_rate.get(line.vat_rate, ZERO) + line_amount
        vat_by_rate[line.vat_rate] = vat_by_rate.get(line.vat_rate, ZERO) + Decimal(
            line.vat_amount_vnd
        )
    breakdown = [
        VatBreakdownEntry(
            rate=rate,
            base=int(to_vnd(base_by_rate[rate])),
            amount=int(to_vnd(vat_by_rate[rate])),
        )
        for rate in sorted(base_by_rate)
    ]
    total_vat = ZERO
    for amount in vat_by_rate.values():
        total_vat += amount
    return Totals(
        subtotal_vnd=int(to_vnd(subtotal)),
        vat_breakdown=breakdown,
        total_vnd=int(to_vnd(subtotal + total_vat)),
    )


def to_usd(vnd: Decimal | int, fx_usd_vnd: int) -> Decimal:
    """FR-054 USD reference = VND / FX rate, 2 dp. Reference only; the invoice is in VND."""
    return (Decimal(str(vnd)) / Decimal(fx_usd_vnd)).quantize(_CENTS, rounding=ROUND_HALF_UP)


def format_vnd(amount: Decimal | int) -> str:
    """FR-055 VND display: '1.234.567 đ' (dot thousands)."""
    return f"{int(to_vnd(amount)):,}".replace(",", ".") + " đ"


def format_usd(amount: Decimal | int) -> str:
    """FR-055 USD display: '$1,234.56'."""
    value = Decimal(str(amount)).quantize(_CENTS, rounding=ROUND_HALF_UP)
    return f"${value:,.2f}"
