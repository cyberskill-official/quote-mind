"""Deterministic customer resolution (FR-043).

Resolve a buyer against candidate profiles from the ``customers`` tenant by email domain, then fuzzy
name, then a free-text hint. Unresolved falls back to the ``end_customer`` tier with the
``unknown_customer`` flag set. The live lookup runs upstream; this picks the best of the candidates.
"""

from __future__ import annotations

import unicodedata
from difflib import SequenceMatcher

from pydantic import BaseModel

from ..models import CustomerProfile, Tier

NAME_MATCH_THRESHOLD = 0.8


class CustomerResolution(BaseModel):
    """Result of FR-043: the matched profile (if any), the effective tier, and the unknown flag."""

    profile: CustomerProfile | None = None
    tier: Tier
    unknown_customer: bool


def _fold(text: str) -> str:
    """Lowercase, drop Vietnamese diacritics, and collapse whitespace for fuzzy comparison."""
    decomposed = unicodedata.normalize("NFKD", text.lower().replace("đ", "d"))
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(stripped.split())


def _domain(email: str | None) -> str | None:
    return email.split("@", 1)[1].lower() if email and "@" in email else None


def _resolved(profile: CustomerProfile) -> CustomerResolution:
    return CustomerResolution(profile=profile, tier=profile.tier, unknown_customer=False)


def resolve_customer(
    candidates: list[CustomerProfile],
    *,
    email: str | None = None,
    name: str | None = None,
    hint: str | None = None,
    name_threshold: float = NAME_MATCH_THRESHOLD,
) -> CustomerResolution:
    """FR-043: resolve by email domain, then fuzzy name, then hint; else end_customer + unknown."""
    domain = _domain(email)
    if domain:
        for candidate in candidates:
            domains = {value.lower() for value in candidate.domains}
            if domain in domains or any(e.lower().endswith("@" + domain) for e in candidate.emails):
                return _resolved(candidate)

    if name:
        folded = _fold(name)
        best: CustomerProfile | None = None
        best_ratio = 0.0
        for candidate in candidates:
            ratio = SequenceMatcher(None, folded, _fold(candidate.name)).ratio()
            if ratio > best_ratio:
                best, best_ratio = candidate, ratio
        if best is not None and best_ratio >= name_threshold:
            return _resolved(best)

    if hint:
        folded_hint = _fold(hint)
        for candidate in candidates:
            if folded_hint and (
                folded_hint in _fold(candidate.name)
                or any(folded_hint in value.lower() for value in candidate.domains)
            ):
                return _resolved(candidate)

    return CustomerResolution(profile=None, tier=Tier.END_CUSTOMER, unknown_customer=True)
