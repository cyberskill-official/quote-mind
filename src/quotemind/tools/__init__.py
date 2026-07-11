"""Toolkit functions the agents call. Currently the deterministic matcher + customer resolution."""

from __future__ import annotations

from .customer import NAME_MATCH_THRESHOLD, CustomerResolution, resolve_customer
from .matching import (
    CONFIDENCE_THRESHOLD,
    build_match_result,
    fuse_candidates,
    reciprocal_rank_fusion,
    top_candidate,
)

__all__ = [
    "CONFIDENCE_THRESHOLD",
    "NAME_MATCH_THRESHOLD",
    "CustomerResolution",
    "build_match_result",
    "fuse_candidates",
    "reciprocal_rank_fusion",
    "resolve_customer",
    "top_candidate",
]
