"""Deterministic critic core (FR-070, FR-071, FR-072).

Pure re-checks over an assembled Quote (DM-10), producing a CriticReport (DM-11). Every money
field is recomputed with the same pricing-engine functions (D-03), so the engine stays the single
source of numeric truth and the LLM can never do arithmetic that ships. The LLM critic narrative
(FR-073) is layered on top by AGT-07; this module is the code-enforced guardrail.
"""

from __future__ import annotations

import re

from ..models import (
    BilingualText,
    CriticReport,
    LineSource,
    Quote,
    QuoteLine,
    RecomputeDiff,
)
from ..pricing import line_total, quote_totals, vat_amount

# FR-053/060 defaults mirror config (settings.margin_floor_pct=5). The agent injects live values;
# validity bounds come from SOP memory, so they are optional and only checked when supplied.
DEFAULT_MARGIN_FLOOR_PCT = 5.0

# Blocking flag codes.
RECOMPUTE_MISMATCH = "RECOMPUTE_MISMATCH"
MARGIN_BELOW_FLOOR = "MARGIN_BELOW_FLOOR"
MISSING_MANDATORY_FIELDS = "MISSING_MANDATORY_FIELDS"
BILINGUAL_NUMBER_MISMATCH = "BILINGUAL_NUMBER_MISMATCH"
MOJIBAKE = "MOJIBAKE"
# Non-blocking flag codes.
UNKNOWN_CUSTOMER = "UNKNOWN_CUSTOMER"
NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
VALIDITY_OUT_OF_BOUNDS = "VALIDITY_OUT_OF_BOUNDS"

_NEEDS_CONFIRMATION_SOURCES = frozenset({LineSource.SUBSTITUTED, LineSource.NO_MATCH})
_DIGIT_RE = re.compile(r"\d+")
# Mojibake signature (FR-072): U+FFFD, a "â€" smart-punctuation artifact, or a Latin-1 high letter
# (U+00C0-U+00FF) immediately followed by a U+0080-U+00BF continuation byte. None of these occur in
# correct NFC Vietnamese, where diacritic vowels are single precomposed code points.
_MOJIBAKE_RE = re.compile("\ufffd|\u00e2\u20ac|[\u00c0-\u00ff][\u0080-\u00bf]")


def recompute_diffs(quote: Quote) -> list[RecomputeDiff]:
    """FR-070: recompute every money field from raw inputs; any != claimed is a diff (> 0 VND)."""
    diffs: list[RecomputeDiff] = []
    recomputed: list[QuoteLine] = []
    for line in quote.lines:
        expected_line_total = int(line_total(line.qty, line.unit_price_vnd, line.discount_pct))
        expected_vat = int(vat_amount(expected_line_total, line.vat_rate))
        if expected_line_total != line.line_total_vnd:
            diffs.append(
                RecomputeDiff(
                    field="line_total_vnd",
                    expected=str(expected_line_total),
                    actual=str(line.line_total_vnd),
                    line_idx=line.idx,
                )
            )
        if expected_vat != line.vat_amount_vnd:
            diffs.append(
                RecomputeDiff(
                    field="vat_amount_vnd",
                    expected=str(expected_vat),
                    actual=str(line.vat_amount_vnd),
                    line_idx=line.idx,
                )
            )
        recomputed.append(
            line.model_copy(
                update={"line_total_vnd": expected_line_total, "vat_amount_vnd": expected_vat}
            )
        )

    totals = quote_totals(recomputed)
    if totals.subtotal_vnd != quote.subtotal_vnd:
        diffs.append(
            RecomputeDiff(
                field="subtotal_vnd",
                expected=str(totals.subtotal_vnd),
                actual=str(quote.subtotal_vnd),
            )
        )
    if totals.total_vnd != quote.total_vnd:
        diffs.append(
            RecomputeDiff(
                field="total_vnd", expected=str(totals.total_vnd), actual=str(quote.total_vnd)
            )
        )

    claimed = {entry.rate: entry for entry in quote.vat_breakdown}
    expected = {entry.rate: entry for entry in totals.vat_breakdown}
    for rate in sorted(set(claimed) | set(expected)):
        exp = expected.get(rate)
        cla = claimed.get(rate)
        if exp is None or cla is None or exp.base != cla.base:
            diffs.append(
                RecomputeDiff(
                    field=f"vat_breakdown[{rate}].base",
                    expected=str(exp.base if exp else 0),
                    actual=str(cla.base if cla else 0),
                )
            )
        if exp is None or cla is None or exp.amount != cla.amount:
            diffs.append(
                RecomputeDiff(
                    field=f"vat_breakdown[{rate}].amount",
                    expected=str(exp.amount if exp else 0),
                    actual=str(cla.amount if cla else 0),
                )
            )
    return diffs


def _missing_mandatory(quote: Quote) -> bool:
    return (
        not quote.quote_number
        or not quote.date
        or not quote.lines
        or not quote.seller_block
        or not quote.customer_block
        or not quote.total_in_words_vi.strip()
    )


def policy_flags(
    quote: Quote,
    *,
    margin_floor_pct: float = DEFAULT_MARGIN_FLOOR_PCT,
    customer_known: bool = True,
    validity_min_days: int | None = None,
    validity_max_days: int | None = None,
) -> tuple[list[str], list[str]]:
    """FR-071 policy flags: (blocking, non_blocking). Validity checked only if SOP bounds given."""
    blocking: list[str] = []
    non_blocking: list[str] = []

    below_floor = quote.margin.blended_pct < margin_floor_pct or any(
        pct < margin_floor_pct for pct in quote.margin.per_line
    )
    if below_floor:
        blocking.append(MARGIN_BELOW_FLOOR)
    if _missing_mandatory(quote):
        blocking.append(MISSING_MANDATORY_FIELDS)

    if not customer_known:
        non_blocking.append(UNKNOWN_CUSTOMER)
    if any(line.source in _NEEDS_CONFIRMATION_SOURCES for line in quote.lines):
        non_blocking.append(NEEDS_CONFIRMATION)
    if validity_min_days is not None and validity_max_days is not None:
        if not validity_min_days <= quote.validity_days <= validity_max_days:
            non_blocking.append(VALIDITY_OUT_OF_BOUNDS)

    return blocking, non_blocking


def _bilingual_pairs(quote: Quote) -> list[tuple[str, BilingualText]]:
    pairs: list[tuple[str, BilingualText]] = [
        ("notes", quote.notes),
        ("terms.payment", quote.terms.payment),
        ("terms.delivery", quote.terms.delivery),
        ("terms.warranty", quote.terms.warranty),
    ]
    for line in quote.lines:
        pairs.append((f"line[{line.idx}].description", line.description))
        pairs.append((f"line[{line.idx}].unit", line.unit))
        if line.note is not None:
            pairs.append((f"line[{line.idx}].note", line.note))
    return pairs


def _numeric_tokens(text: str) -> list[str]:
    # Strip thousands separators so a money figure reads the same regardless of vi/en grouping.
    return sorted(_DIGIT_RE.findall(text.replace(".", "").replace(",", "")))


def bilingual_number_mismatches(quote: Quote) -> list[str]:
    """FR-072: field names whose vi and en numeric tokens disagree (regex diff, never the LLM)."""
    return [
        name
        for name, text in _bilingual_pairs(quote)
        if _numeric_tokens(text.vi) != _numeric_tokens(text.en)
    ]


def mojibake_fields(quote: Quote) -> list[str]:
    """FR-072: field names whose text shows an encoding artifact in either language."""
    bad = [
        name
        for name, text in _bilingual_pairs(quote)
        if _MOJIBAKE_RE.search(text.vi) or _MOJIBAKE_RE.search(text.en)
    ]
    if _MOJIBAKE_RE.search(quote.total_in_words_vi):
        bad.append("total_in_words_vi")
    return bad


def _summary_note(passed: bool, blocking: list[str], non_blocking: list[str]) -> BilingualText:
    if passed:
        note = (
            "Đã kiểm tra: số học, chính sách và song ngữ đều khớp.",
            "Checked: arithmetic, policy, and bilingual fields all agree.",
        )
    else:
        note = (
            "Không đạt: " + ", ".join(blocking) + ".",
            "Failed: " + ", ".join(blocking) + ".",
        )
    return BilingualText(vi=note[0], en=note[1])


def run_critic(
    quote: Quote,
    *,
    margin_floor_pct: float = DEFAULT_MARGIN_FLOOR_PCT,
    customer_known: bool = True,
    validity_min_days: int | None = None,
    validity_max_days: int | None = None,
) -> CriticReport:
    """FR-070/071/072: assemble the deterministic CriticReport. passed only when nothing blocks."""
    diffs = recompute_diffs(quote)
    blocking, non_blocking = policy_flags(
        quote,
        margin_floor_pct=margin_floor_pct,
        customer_known=customer_known,
        validity_min_days=validity_min_days,
        validity_max_days=validity_max_days,
    )
    if diffs:
        blocking = [RECOMPUTE_MISMATCH, *blocking]
    if bilingual_number_mismatches(quote):
        blocking.append(BILINGUAL_NUMBER_MISMATCH)
    if mojibake_fields(quote):
        blocking.append(MOJIBAKE)

    passed = not blocking
    return CriticReport(
        passed=passed,
        blocking=blocking,
        non_blocking=non_blocking,
        recompute_diffs=diffs,
        note=_summary_note(passed, blocking, non_blocking),
    )
