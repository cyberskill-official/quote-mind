"""Deterministic quote assembly (TASK-060).

Turns resolved, matched lines plus the pricing engine into a complete Quote (DM-10). Every number
is produced by the engine here - the drafter LLM only supplies natural-language fields (line
description/unit phrasing, notes, terms), which arrive as inputs. The critic (TASK-070) later
recomputes these same numbers, so assembly and critic must agree by construction.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from ..models import (
    BilingualText,
    CatalogProduct,
    LineSource,
    MarginInfo,
    Quote,
    QuoteLine,
    QuoteTerms,
    StockStatus,
    Tier,
    UsdReference,
)
from ..pricing import (
    amount_in_words_vi,
    blended_margin,
    is_excluded_category,
    line_total,
    margin,
    quote_totals,
    to_usd,
    unit_price,
    vat_amount,
    vat_rate_for,
)

DEFAULT_PROJECT_DISCOUNT_PCT = 3.0
VAT_EXCLUDED_CATEGORY = "VAT_EXCLUDED_CATEGORY"
LEAD_TIME = "LEAD_TIME"


class AssemblyLine(BaseModel):
    """One resolved RFQ line ready to price: a catalog product, quantity, tier, and NL overrides."""

    product: CatalogProduct
    qty: Decimal
    tier: Tier
    discount_pct: float = 0.0
    description: BilingualText | None = None  # drafter override; defaults to the catalog name
    unit: BilingualText | None = None  # drafter override; defaults to the catalog unit
    note: BilingualText | None = None
    source: LineSource = LineSource.MATCHED


def lead_time_lines(lines: list[AssemblyLine]) -> list[int]:
    """TASK-056: the 1-based indexes of lines whose product is not on the shelf.

    The critic never sees the catalog - it only sees the assembled Quote - so the caller that *did*
    resolve the products has to say which lines carry a lead time. Returning indexes rather than a
    boolean means the flag can point at a line instead of at the whole quote.
    """
    return [
        index
        for index, item in enumerate(lines, start=1)
        if item.product.stock_status is StockStatus.OUT_OF_STOCK
    ]


def _line_note(item: AssemblyLine) -> BilingualText | None:
    """TASK-056: an out-of-stock line says so, on the line, in both languages.

    A quote whose delivery terms promise seven working days while one of its lines is a made-to-
    order server is a quote that makes a promise the business cannot keep. The lead time belongs
    next to the item it applies to, not buried in the footer - so it is appended to whatever note
    the line already carries (a substitution note, typically), rather than replacing it.
    """
    product = item.product
    if product.stock_status is not StockStatus.OUT_OF_STOCK:
        return item.note

    days = product.lead_time_days
    lead = BilingualText(
        vi=f"Hiện hết hàng, thời gian giao dự kiến {days} ngày.",
        en=f"Currently out of stock; estimated delivery {days} days.",
    )

    if item.note is None:
        return lead
    return BilingualText(vi=f"{item.note.vi} {lead.vi}", en=f"{item.note.en} {lead.en}")


def assemble_quote(
    *,
    quote_id: str,
    quote_number: str,
    seller_block: dict[str, Any],
    customer_block: dict[str, Any],
    date: str,
    validity_days: int,
    lines: list[AssemblyLine],
    terms: QuoteTerms,
    notes: BilingualText,
    on_date: date,
    fx_usd_vnd: int | None = None,
    project_discount_pct: float = DEFAULT_PROJECT_DISCOUNT_PCT,
) -> Quote:
    """TASK-060: build a fully-priced Quote. All money comes from the pricing engine (D-03)."""
    quote_lines: list[QuoteLine] = []
    margin_pairs: list[tuple[Decimal | int, Decimal | int]] = []
    per_line_margin: list[float] = []

    for index, item in enumerate(lines, start=1):
        product = item.product
        item = item.model_copy(update={"note": _line_note(item)})  # TASK-056  # noqa: PLW2901
        price = unit_price(product, item.tier, project_discount_pct)
        rate = vat_rate_for(product, on_date)
        amount = line_total(item.qty, price, item.discount_pct)
        vat = vat_amount(amount, rate)
        cost = item.qty * Decimal(product.cost_price_vnd)

        quote_lines.append(
            QuoteLine(
                idx=index,
                sku=product.sku,
                description=item.description or product.name,
                unit=item.unit or BilingualText(vi=product.unit, en=product.unit),
                qty=item.qty,
                unit_price_vnd=int(price),
                discount_pct=item.discount_pct,
                line_total_vnd=int(amount),
                vat_rate=rate,
                vat_amount_vnd=int(vat),
                note=item.note,
                source=item.source,
            )
        )
        margin_pairs.append((amount, cost))
        per_line_margin.append(float(margin(amount, cost)))

    totals = quote_totals(quote_lines)

    usd_reference = None
    if fx_usd_vnd is not None:
        usd_reference = UsdReference(
            rate=fx_usd_vnd,
            subtotal=to_usd(totals.subtotal_vnd, fx_usd_vnd),
            total=to_usd(totals.total_vnd, fx_usd_vnd),
            as_of=date,
        )

    flags: list[str] = []
    if any(is_excluded_category(item.product) for item in lines):
        flags.append(VAT_EXCLUDED_CATEGORY)
    if any(item.product.stock_status == StockStatus.OUT_OF_STOCK for item in lines):
        flags.append(LEAD_TIME)

    return Quote(
        quote_id=quote_id,
        quote_number=quote_number,
        seller_block=seller_block,
        customer_block=customer_block,
        date=date,
        validity_days=validity_days,
        lines=quote_lines,
        subtotal_vnd=totals.subtotal_vnd,
        vat_breakdown=totals.vat_breakdown,
        total_vnd=totals.total_vnd,
        total_in_words_vi=amount_in_words_vi(totals.total_vnd),
        usd_reference=usd_reference,
        terms=terms,
        notes=notes,
        flags=flags,
        margin=MarginInfo(
            blended_pct=float(blended_margin(margin_pairs)), per_line=per_line_margin
        ),
    )


__all__ = [
    "AssemblyLine",
    "assemble_quote",
    "DEFAULT_PROJECT_DISCOUNT_PCT",
    "LEAD_TIME",
    "VAT_EXCLUDED_CATEGORY",
]
