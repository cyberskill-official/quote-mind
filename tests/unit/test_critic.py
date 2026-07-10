"""FR-070 independent recomputation, FR-071 policy flags, FR-072 bilingual/mojibake checks."""

from __future__ import annotations

from decimal import Decimal

from quotemind.models import (
    BilingualText,
    LineSource,
    MarginInfo,
    Quote,
    QuoteLine,
    QuoteTerms,
    VatBreakdownEntry,
)
from quotemind.quote import (
    bilingual_number_mismatches,
    mojibake_fields,
    recompute_diffs,
    run_critic,
)


def _line(
    idx: int,
    qty: int,
    price: int,
    line_total_vnd: int,
    vat_amount_vnd: int,
    *,
    vat_rate: int = 8,
    discount_pct: float = 0.0,
    source: LineSource = LineSource.MATCHED,
) -> QuoteLine:
    return QuoteLine(
        idx=idx,
        sku=f"SKU-{idx}",
        description=BilingualText(vi="Thiết bị mạng", en="Network device"),
        unit=BilingualText(vi="cái", en="unit"),
        qty=Decimal(qty),
        unit_price_vnd=price,
        discount_pct=discount_pct,
        line_total_vnd=line_total_vnd,
        vat_rate=vat_rate,
        vat_amount_vnd=vat_amount_vnd,
        source=source,
    )


def _quote(**over: object) -> Quote:
    # Self-consistent: 10 x 1,000,000 + 2 x 500,000 = 11,000,000 subtotal; 8% VAT = 880,000.
    base: dict[str, object] = {
        "quote_id": "Q1",
        "quote_number": "QM-2026-0001",
        "seller_block": {"name": "CyberSkill"},
        "customer_block": {"name": "ACME"},
        "date": "2026-07-11",
        "validity_days": 14,
        "lines": [
            _line(1, 10, 1_000_000, 10_000_000, 800_000),
            _line(2, 2, 500_000, 1_000_000, 80_000),
        ],
        "subtotal_vnd": 11_000_000,
        "vat_breakdown": [VatBreakdownEntry(rate=8, base=11_000_000, amount=880_000)],
        "total_vnd": 11_880_000,
        "total_in_words_vi": "Mười một triệu tám trăm tám mươi nghìn đồng",
        "terms": QuoteTerms(
            payment=BilingualText(vi="Thanh toán trong 30 ngày", en="Payment within 30 days"),
            delivery=BilingualText(vi="Giao hàng trong 7 ngày", en="Delivery within 7 days"),
            warranty=BilingualText(vi="Bảo hành 12 tháng", en="12 months warranty"),
        ),
        "notes": BilingualText(vi="Cảm ơn quý khách", en="Thank you for your business"),
        "margin": MarginInfo(blended_pct=18.0, per_line=[20.0, 15.0]),
    }
    base.update(over)
    return Quote(**base)  # type: ignore[arg-type]


def test_clean_quote_passes() -> None:
    report = run_critic(_quote())
    assert report.passed is True
    assert report.blocking == []
    assert report.recompute_diffs == []


def test_tampered_line_total_is_caught() -> None:
    # FR-070 AC: one wrong line total -> critic_failed with the offending line id.
    bad = _quote(
        lines=[
            _line(1, 10, 1_000_000, 9_999_999, 800_000),  # claimed total is wrong
            _line(2, 2, 500_000, 1_000_000, 80_000),
        ]
    )
    report = run_critic(bad)
    assert report.passed is False
    assert "RECOMPUTE_MISMATCH" in report.blocking
    assert ("line_total_vnd", 1) in {(d.field, d.line_idx) for d in report.recompute_diffs}


def test_tampered_subtotal_and_total_caught() -> None:
    report = run_critic(_quote(subtotal_vnd=1, total_vnd=2))
    fields = {d.field for d in report.recompute_diffs}
    assert {"subtotal_vnd", "total_vnd"} <= fields
    assert "RECOMPUTE_MISMATCH" in report.blocking


def test_tampered_vat_breakdown_caught() -> None:
    report = run_critic(
        _quote(vat_breakdown=[VatBreakdownEntry(rate=8, base=11_000_000, amount=880_001)])
    )
    assert any(d.field == "vat_breakdown[8].amount" for d in report.recompute_diffs)


def test_margin_below_floor_blocks() -> None:
    report = run_critic(_quote(margin=MarginInfo(blended_pct=3.0, per_line=[3.0, 3.0])))
    assert "MARGIN_BELOW_FLOOR" in report.blocking
    assert report.passed is False


def test_nonblocking_flags_do_not_fail_the_quote() -> None:
    quote = _quote(
        lines=[
            _line(1, 10, 1_000_000, 10_000_000, 800_000, source=LineSource.SUBSTITUTED),
            _line(2, 2, 500_000, 1_000_000, 80_000),
        ]
    )
    report = run_critic(quote, customer_known=False, validity_min_days=7, validity_max_days=10)
    assert set(report.non_blocking) == {
        "UNKNOWN_CUSTOMER",
        "NEEDS_CONFIRMATION",
        "VALIDITY_OUT_OF_BOUNDS",  # validity_days 14 > 10
    }
    assert report.blocking == []
    assert report.passed is True


def test_bilingual_number_mismatch_blocks() -> None:
    quote = _quote(
        terms=QuoteTerms(
            payment=BilingualText(vi="Thanh toán trong 30 ngày", en="Payment within 45 days"),
            delivery=BilingualText(vi="Giao hàng trong 7 ngày", en="Delivery within 7 days"),
            warranty=BilingualText(vi="Bảo hành 12 tháng", en="12 months warranty"),
        )
    )
    report = run_critic(quote)
    assert "BILINGUAL_NUMBER_MISMATCH" in report.blocking
    assert "terms.payment" in bilingual_number_mismatches(quote)


def test_mojibake_blocks() -> None:
    quote = _quote(notes=BilingualText(vi="Cáº£m Æ¡n quÃ½ khÃ¡ch", en="Thanks"))
    report = run_critic(quote)
    assert "MOJIBAKE" in report.blocking
    assert "notes" in mojibake_fields(quote)


def test_missing_mandatory_field_blocks() -> None:
    report = run_critic(_quote(quote_number=""))
    assert "MISSING_MANDATORY_FIELDS" in report.blocking
    assert report.passed is False


def test_recompute_diffs_helper_clean() -> None:
    assert recompute_diffs(_quote()) == []
