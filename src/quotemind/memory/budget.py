"""Context budget guard (FR-049): cap injected memory tokens, dropping lowest-score items."""

from __future__ import annotations

from typing import TypeVar

CONTEXT_TOKEN_BUDGET = 2500
EPISODIC_TOKEN_BUDGET = 1200
_CHARS_PER_TOKEN = 4

_T = TypeVar("_T")


def estimate_tokens(text: str) -> int:
    """Approximate token count (~4 chars per token). Deterministic; not a model tokenizer."""
    return max(1, (len(text) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN)


def budget_trim(
    items: list[tuple[_T, int, float]], max_tokens: int = CONTEXT_TOKEN_BUDGET
) -> tuple[list[_T], bool]:
    """Keep the highest-effective-score items that fit within max_tokens.

    Each item is (value, token_count, effective_score). Items are taken in descending score;
    once one does not fit, it and the remaining lower-score items are dropped. Returns
    (kept_values, truncated), where truncated is True when anything was dropped (FR-049
    memory_truncated).
    """
    ordered = sorted(items, key=lambda triple: triple[2], reverse=True)
    kept: list[_T] = []
    used = 0
    for value, tokens, _score in ordered:
        if used + tokens <= max_tokens:
            kept.append(value)
            used += tokens
        else:
            return kept, True
    return kept, False
