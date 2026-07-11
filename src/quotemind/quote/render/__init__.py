"""FR-090 bilingual quote rendering.

``render_html`` is deterministic (Jinja2 only, no I/O beyond the bundled template), so the layout is
fully offline-testable. ``render_pdf`` is a thin WeasyPrint wrapper that needs the ``pdf`` extra
(weasyprint==68) and the bundled Be Vietnam Pro fonts; it is the live path and is not part of the
offline gate.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ...models import BilingualText, Quote, QuoteLine
from ...pricing import format_usd, format_vnd

_TEMPLATE_DIR = Path(__file__).parent
_TEMPLATE_NAME = "quote.html.j2"
# FR-124: the branded face, bundled. `quote.html.j2` resolves the @font-face URLs relative to the
# template, so WeasyPrint finds them without a base_url and without a Dockerfile step.
FONT_DIR = _TEMPLATE_DIR / "fonts"
_ENV = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(enabled_extensions=("html", "j2"), default_for_string=True),
    trim_blocks=True,
    lstrip_blocks=True,
)


def _format_qty(qty: Decimal) -> str:
    normalized = qty.normalize()
    if normalized == normalized.to_integral_value():
        return str(int(normalized))
    return format(normalized, "f")


def _line_context(line: QuoteLine) -> dict[str, Any]:
    note = line.note
    return {
        "idx": line.idx,
        "sku": line.sku,
        "desc_vi": line.description.vi,
        "desc_en": line.description.en,
        "unit_vi": line.unit.vi,
        "unit_en": line.unit.en,
        "qty": _format_qty(line.qty),
        "unit_price": format_vnd(line.unit_price_vnd),
        "amount": format_vnd(line.line_total_vnd),
        "has_note": note is not None,
        "note_vi": note.vi if note is not None else "",
        "note_en": note.en if note is not None else "",
    }


def build_context(
    quote: Quote,
    *,
    vat_policy_note: BilingualText,
    fx_note: str = "",
    prepared_by: str = "QuoteMind",
    reviewer: str = "",
) -> dict[str, Any]:
    """Assemble the template context. Every money value is formatted by the pricing engine."""
    seller = dict(quote.seller_block)
    usd = None
    if quote.usd_reference is not None:
        ref = quote.usd_reference
        usd = {
            "rate": f"{ref.rate:,}",
            "subtotal": format_usd(ref.subtotal),
            "total": format_usd(ref.total),
            "as_of": ref.as_of,
        }
    return {
        "q": quote,
        "seller": seller,
        "customer": dict(quote.customer_block),
        "bank": dict(seller.get("bank", {})),
        "lines": [_line_context(line) for line in quote.lines],
        "subtotal": format_vnd(quote.subtotal_vnd),
        "vat_lines": [
            {"rate": entry.rate, "base": format_vnd(entry.base), "amount": format_vnd(entry.amount)}
            for entry in quote.vat_breakdown
        ],
        "total": format_vnd(quote.total_vnd),
        "usd": usd,
        "terms": {
            "payment_vi": quote.terms.payment.vi,
            "payment_en": quote.terms.payment.en,
            "delivery_vi": quote.terms.delivery.vi,
            "delivery_en": quote.terms.delivery.en,
            "warranty_vi": quote.terms.warranty.vi,
            "warranty_en": quote.terms.warranty.en,
        },
        "notes_vi": quote.notes.vi,
        "notes_en": quote.notes.en,
        "vat_note_vi": vat_policy_note.vi,
        "vat_note_en": vat_policy_note.en,
        "fx_note": fx_note,
        "prepared_by": prepared_by,
        "reviewer": reviewer,
    }


def render_html(
    quote: Quote,
    *,
    vat_policy_note: BilingualText,
    fx_note: str = "",
    prepared_by: str = "QuoteMind",
    reviewer: str = "",
) -> str:
    """FR-090: deterministic bilingual HTML (Appendix C) for the quote."""
    context = build_context(
        quote,
        vat_policy_note=vat_policy_note,
        fx_note=fx_note,
        prepared_by=prepared_by,
        reviewer=reviewer,
    )
    return _ENV.get_template(_TEMPLATE_NAME).render(**context)


def render_pdf(
    quote: Quote,
    *,
    vat_policy_note: BilingualText,
    fx_note: str = "",
    prepared_by: str = "QuoteMind",
    reviewer: str = "",
) -> bytes:
    """FR-090 PDF via WeasyPrint. Requires the 'pdf' extra and bundled fonts (live path)."""
    try:
        from weasyprint import HTML
    except ImportError as exc:  # pragma: no cover - only without the pdf extra
        raise RuntimeError(
            "render_pdf needs the 'pdf' extra (weasyprint==68) and bundled Be Vietnam Pro fonts"
        ) from exc
    html = render_html(
        quote,
        vat_policy_note=vat_policy_note,
        fx_note=fx_note,
        prepared_by=prepared_by,
        reviewer=reviewer,
    )
    return HTML(string=html, base_url=str(_TEMPLATE_DIR)).write_pdf()  # pragma: no cover


__all__ = ["build_context", "render_html", "render_pdf"]
