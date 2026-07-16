"""TASK-046: episodic importance, recency decay, effective score, and ranking."""

from __future__ import annotations

import pytest

from quotemind.memory import (
    effective_ceiling,
    effective_score,
    initial_importance,
    rank_by_effective_score,
    recency_decay,
    should_prune,
)
from quotemind.models import Outcome


def test_initial_importance() -> None:
    assert initial_importance(Outcome.APPROVED, 50_000_000) == 0.7
    assert initial_importance(Outcome.EDITED, 50_000_000) == 0.8
    assert initial_importance(Outcome.REJECTED, 50_000_000) == 0.9
    assert initial_importance(Outcome.APPROVED, 200_000_000) == pytest.approx(0.8)
    assert initial_importance(Outcome.REJECTED, 200_000_000) == pytest.approx(1.0)  # capped


def test_recency_decay() -> None:
    assert recency_decay(0) == 1.0
    assert recency_decay(90) == pytest.approx(0.5)
    assert recency_decay(180) == pytest.approx(0.25)


def test_effective_score_and_ceiling() -> None:
    assert effective_score(1.0, 1.0, 0) == 1.0
    assert effective_score(0.5, 0.8, 90) == pytest.approx(0.5 * 0.5 * 0.8)
    assert effective_ceiling(0.7, 90) == pytest.approx(0.35)


def test_should_prune() -> None:
    assert should_prune(0.1, 400) is True  # very old, low importance
    assert should_prune(0.9, 5) is False  # fresh, high importance


def test_fresh_ranks_above_old_of_equal_similarity() -> None:
    # TASK-046 AC: fresh memory ranks first over a 200-day-old one of equal similarity.
    ranked = rank_by_effective_score([("old", 0.9, 0.7, 200.0), ("fresh", 0.9, 0.7, 1.0)])
    assert [item for item, _score in ranked] == ["fresh", "old"]
