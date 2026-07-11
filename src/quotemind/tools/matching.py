"""Deterministic catalog-matching helpers (FR-042).

The CatalogMatcher agent (AGT-04) runs vector_search + full_text_search against the live catalog,
then an LLM selects the best SKU with a confidence. The code-enforced parts - fusing the two
candidate rankings and banding a selection into a MatchResult (DM-09) - live here so they are
testable offline. The LLM select is injected: this module never calls a model.
"""

from __future__ import annotations

from ..models import BilingualText, MatchAlternative, MatchResult, MatchStatus

CONFIDENCE_THRESHOLD = 0.75  # FR-042: below this (or on a spec conflict) -> needs_confirmation
_RRF_K = 60  # standard reciprocal-rank-fusion damping constant
_MAX_ALTERNATIVES = 3

_LOWCONF_REASON = BilingualText(
    vi="Độ tin cậy khớp thấp, cần xác nhận.", en="Low match confidence; confirmation needed."
)
_SPECS_REASON = BilingualText(
    vi="Thông số kỹ thuật chưa khớp hoàn toàn, cần xác nhận.",
    en="Specs do not fully match; confirmation needed.",
)
_NO_MATCH_REASON = BilingualText(
    vi="Không tìm thấy sản phẩm phù hợp trong danh mục.", en="No matching catalog product found."
)
_ALT_REASON = BilingualText(vi="Ứng viên thay thế", en="Alternative candidate")


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = _RRF_K) -> list[tuple[str, float]]:
    """Fuse ranked SKU lists by reciprocal rank: score = sum 1/(k + rank). Ties break by SKU."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, sku in enumerate(ranking):
            scores[sku] = scores.get(sku, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def fuse_candidates(vector_skus: list[str], text_skus: list[str], k: int = _RRF_K) -> list[str]:
    """RRF-fuse the vector and full-text SKU rankings into a single ranked SKU list."""
    return [sku for sku, _ in reciprocal_rank_fusion([vector_skus, text_skus], k)]


def top_candidate(fused_skus: list[str]) -> str | None:
    """The best fused SKU, or None when there are no candidates (no-LLM default selection)."""
    return fused_skus[0] if fused_skus else None


def _alternatives(fused_skus: list[str], exclude: str | None) -> list[MatchAlternative]:
    return [MatchAlternative(sku=sku, reason=_ALT_REASON) for sku in fused_skus if sku != exclude][
        :_MAX_ALTERNATIVES
    ]


def build_match_result(
    line_ref: int,
    fused_skus: list[str],
    chosen_sku: str | None,
    confidence: float,
    *,
    specs_conflict: bool = False,
) -> MatchResult:
    """FR-042 banding: MATCHED, or NEEDS_CONFIRMATION (< 0.75 or spec conflict, with <=3 alts), or
    NO_MATCH when nothing was selected (near-misses surfaced as alternatives)."""
    if chosen_sku is None:
        return MatchResult(
            line_ref=line_ref,
            status=MatchStatus.NO_MATCH,
            sku=None,
            match_confidence=0.0,
            alternatives=_alternatives(fused_skus, None),
            reason=_NO_MATCH_REASON,
        )
    if confidence < CONFIDENCE_THRESHOLD or specs_conflict:
        return MatchResult(
            line_ref=line_ref,
            status=MatchStatus.NEEDS_CONFIRMATION,
            sku=chosen_sku,
            match_confidence=confidence,
            alternatives=_alternatives(fused_skus, chosen_sku),
            reason=_SPECS_REASON if specs_conflict else _LOWCONF_REASON,
        )
    return MatchResult(
        line_ref=line_ref,
        status=MatchStatus.MATCHED,
        sku=chosen_sku,
        match_confidence=confidence,
    )
