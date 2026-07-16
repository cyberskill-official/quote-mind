"""Episodic memory scoring: importance, recency decay, and effective score (TASK-044..046).

Pure functions. The write and retrieve paths that use these live on MemoryFacade; the actual
Tablestore reads and writes are exercised live, not by unit tests.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TypeVar

from ..models import Outcome

HALF_LIFE_DAYS = 90.0
PRUNE_FLOOR = 0.05
COMPACTION_LIMIT = 50

_OUTCOME_BASE = {Outcome.APPROVED: 0.7, Outcome.EDITED: 0.8, Outcome.REJECTED: 0.9}
_HIGH_VALUE_VND = 100_000_000

_T = TypeVar("_T")


def initial_importance(outcome: Outcome, total_vnd: int) -> float:
    """TASK-046 initial importance in [0,1]: outcome base plus a high-value bonus, capped at 1.0."""
    score = _OUTCOME_BASE[outcome]
    if total_vnd > _HIGH_VALUE_VND:
        score += 0.1
    return min(score, 1.0)


def recency_decay(age_days: float, half_life: float = HALF_LIFE_DAYS) -> float:
    """TASK-046 recency decay = 0.5 ** (age_days / half_life)."""
    return 0.5 ** (age_days / half_life)


def age_in_days(created_at: datetime, now: datetime | None = None) -> float:
    """Whole-and-fractional days since created_at, never negative."""
    reference = now or datetime.now(timezone.utc)
    return max((reference - created_at).total_seconds() / 86400.0, 0.0)


def effective_score(
    similarity: float, importance: float, age_days: float, half_life: float = HALF_LIFE_DAYS
) -> float:
    """TASK-046 effective retrieval score = similarity * recency_decay * importance."""
    return similarity * recency_decay(age_days, half_life) * importance


def effective_ceiling(
    importance: float, age_days: float, half_life: float = HALF_LIFE_DAYS
) -> float:
    """Best-case effective score (similarity = 1.0); the gc pruning basis."""
    return recency_decay(age_days, half_life) * importance


def should_prune(importance: float, age_days: float, floor: float = PRUNE_FLOOR) -> bool:
    """TASK-046: prune when the effective ceiling falls below the floor."""
    return effective_ceiling(importance, age_days) < floor


def rank_by_effective_score(
    items: list[tuple[_T, float, float, float]],
) -> list[tuple[_T, float]]:
    """Sort (item, similarity, importance, age_days) tuples by descending effective score."""
    scored = [(item, effective_score(sim, imp, age)) for item, sim, imp, age in items]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored
