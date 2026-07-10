"""Memory layer: the SDK adapter over tablestore-for-agent-memory (FR-040..043)."""

from __future__ import annotations

from .store import (
    TENANT_CATALOG,
    TENANT_CUSTOMERS,
    TENANT_SOP,
    MemoryFacade,
    episodic_tenant,
)

__all__ = [
    "TENANT_CATALOG",
    "TENANT_CUSTOMERS",
    "TENANT_SOP",
    "MemoryFacade",
    "episodic_tenant",
]
