"""QuoteMind HTTP API (API-01..13).

PR-1 implements /health (API-11) and the bearer guard on /api/* (FR-009, FR-010). The
remaining routes arrive with their epics; /api/quotes is a guarded empty page for now.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .. import __version__
from ..config import models as model_constants
from .auth import require_bearer

app = FastAPI(title="QuoteMind API", version=__version__)


@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(_request: Any, exc: StarletteHTTPException) -> JSONResponse:
    """Render errors in the frozen shape {"error": {code, message, details?}} (section 8)."""
    detail = exc.detail
    if isinstance(detail, dict) and "error" in detail:
        return JSONResponse(status_code=exc.status_code, content=detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": str(exc.status_code), "message": str(detail)}},
    )


@app.get("/health")
def health() -> dict[str, Any]:
    """API-11 / FR-009: liveness, version, git SHA, and frozen model constants. No auth."""
    return {
        "status": "ok",
        "version": __version__,
        "git_sha": os.getenv("GIT_SHA", "dev"),
        "models": model_constants.MODEL_CONSTANTS,
    }


@app.get("/api/quotes", dependencies=[Depends(require_bearer)])
def list_quotes(
    status: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> dict[str, Any]:
    """API-02 queue. PR-1 returns an empty page; real listing lands with EP-08/EP-10."""
    return {"items": [], "next_cursor": None}
