"""Bearer authentication for /api/* routes (TASK-010, NFR-006)."""

from __future__ import annotations

from fastapi import Header, HTTPException

from ..config.settings import get_settings


def require_bearer(authorization: str | None = Header(default=None)) -> None:
    """Require `Authorization: Bearer $DEMO_API_TOKEN`; raise 401 otherwise."""
    expected = get_settings().demo_api_token
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "unauthorized", "message": "Missing bearer token"}},
        )
    token = authorization.split(" ", 1)[1].strip()
    if token != expected:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "unauthorized", "message": "Invalid bearer token"}},
        )
