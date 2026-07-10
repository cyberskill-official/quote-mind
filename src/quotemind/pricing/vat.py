"""Vietnam 2026 VAT rules (FR-052, Appendix B). Pure; the caller injects the quote date."""

from __future__ import annotations

from datetime import date

from ..models import BilingualText, CatalogProduct, Category

ALLOWED_VAT_RATES = frozenset({0, 5, 8, 10})
EXCLUDED_CATEGORIES = frozenset({Category.TELECOM_SERVICE})
REDUCTION_START = date(2025, 7, 1)
REDUCTION_END = date(2026, 12, 31)
REDUCED_RATE = 8
STANDARD_RATE = 10


def is_reduction_active(on_date: date) -> bool:
    """True while the 10->8 VAT reduction (Decree 174/2025) is in force."""
    return REDUCTION_START <= on_date <= REDUCTION_END


def is_excluded_category(product: CatalogProduct) -> bool:
    """True when the line must carry the VAT_EXCLUDED_CATEGORY flag (FR-052)."""
    return product.category in EXCLUDED_CATEGORIES


def vat_rate_for(
    product: CatalogProduct,
    on_date: date,
    default_override: int | None = None,
) -> int:
    """FR-052 line VAT rate. Excluded categories force 10%; the 8% relief expires end-2026."""
    if product.vat_rate not in ALLOWED_VAT_RATES:
        raise ValueError(
            f"Unsupported VAT rate {product.vat_rate}; allowed {sorted(ALLOWED_VAT_RATES)}"
        )
    if is_excluded_category(product):
        return STANDARD_RATE
    if product.vat_rate == REDUCED_RATE and not is_reduction_active(on_date):
        return default_override if default_override is not None else STANDARD_RATE
    return product.vat_rate


def vat_policy_note(on_date: date) -> BilingualText:
    """FR-052 footer legal-basis note, per Appendix B."""
    if is_reduction_active(on_date):
        return BilingualText(
            vi=(
                "Thuế GTGT áp dụng theo Nghị định 174/2025/NĐ-CP "
                "(thuế suất ưu đãi 8% đến 31/12/2026, trừ nhóm loại trừ)."
            ),
            en=(
                "VAT applied per Decree 174/2025/ND-CP "
                "(reduced 8% rate through 31 Dec 2026, excluded groups at 10%)."
            ),
        )
    return BilingualText(
        vi="Thuế GTGT áp dụng thuế suất tiêu chuẩn 10% (ưu đãi 8% hết hiệu lực sau 31/12/2026).",
        en="VAT applied at the standard 10% rate (the reduced 8% rate expired after 31 Dec 2026).",
    )
