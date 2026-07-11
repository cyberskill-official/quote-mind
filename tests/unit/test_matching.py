"""FR-042 reciprocal-rank fusion and confidence banding into MatchResult (DM-09)."""

from __future__ import annotations

from quotemind.models import MatchStatus
from quotemind.tools import (
    build_match_result,
    fuse_candidates,
    reciprocal_rank_fusion,
    top_candidate,
)


def test_rrf_fuses_both_rankings() -> None:
    fused = fuse_candidates(["A", "B", "C"], ["B", "A", "D"])
    assert set(fused[:2]) == {"A", "B"}  # ranked high in both lists
    assert set(fused) == {"A", "B", "C", "D"}


def test_rrf_scores_and_deterministic_tiebreak() -> None:
    scored = reciprocal_rank_fusion([["A", "B"], ["A", "C"]])
    assert scored[0][0] == "A"  # rank 0 in both -> highest
    assert [sku for sku, _ in scored] == ["A", "B", "C"]  # B, C tie -> break by SKU


def test_matched_high_confidence_has_no_alternatives() -> None:
    result = build_match_result(1, ["DL-1", "DL-2"], "DL-1", 0.92)
    assert result.status == MatchStatus.MATCHED
    assert result.sku == "DL-1"
    assert result.alternatives == []
    assert result.reason is None


def test_needs_confirmation_low_confidence_carries_alternatives() -> None:
    result = build_match_result(2, ["DL-1", "DL-2", "DL-3", "DL-4"], "DL-1", 0.60)
    assert result.status == MatchStatus.NEEDS_CONFIRMATION
    # chosen excluded, capped at 3
    assert [alt.sku for alt in result.alternatives] == ["DL-2", "DL-3", "DL-4"]
    assert result.reason is not None and "confidence" in result.reason.en.lower()


def test_needs_confirmation_on_spec_conflict_even_when_confident() -> None:
    result = build_match_result(3, ["DL-1", "DL-2"], "DL-1", 0.95, specs_conflict=True)
    assert result.status == MatchStatus.NEEDS_CONFIRMATION
    assert result.reason is not None and "spec" in result.reason.en.lower()


def test_no_match_when_nothing_selected() -> None:
    result = build_match_result(4, ["DL-9", "DL-8"], None, 0.0)
    assert result.status == MatchStatus.NO_MATCH
    assert result.sku is None
    assert [alt.sku for alt in result.alternatives] == ["DL-9", "DL-8"]  # near-misses surfaced
    assert top_candidate([]) is None
    assert top_candidate(["X", "Y"]) == "X"
