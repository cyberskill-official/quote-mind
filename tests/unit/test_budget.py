"""FR-049: the context budget guard."""

from __future__ import annotations

from quotemind.memory import budget_trim, estimate_tokens


def test_estimate_tokens() -> None:
    assert estimate_tokens("") == 1
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcde") == 2  # 5 chars -> 2 tokens


def test_budget_trim_keeps_top_scores_within_budget() -> None:
    items = [("a", 1000, 0.9), ("b", 1000, 0.5), ("c", 1000, 0.8)]
    kept, truncated = budget_trim(items, max_tokens=2000)
    assert kept == ["a", "c"]  # the two highest scores fit; the lowest is dropped
    assert truncated is True


def test_budget_trim_all_fit() -> None:
    kept, truncated = budget_trim([("a", 100, 0.9), ("b", 100, 0.5)], max_tokens=2500)
    assert set(kept) == {"a", "b"}
    assert truncated is False
