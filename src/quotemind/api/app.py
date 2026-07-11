"""QuoteMind HTTP API (API-01..13).

The routes are a thin shell: every state change goes through QuoteService, which owns the state
machine and the audit chain. Processing is asynchronous (FR-020) - POST /api/rfq returns 202
immediately and the pipeline runs in the background, ending durably at the approval gate.
"""

from __future__ import annotations

import os
from typing import Annotated, Any

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from .. import __version__
from ..config import models as model_constants
from ..config.settings import get_settings
from ..intake import MAX_UPLOAD_BYTES, UnsupportedPayloadError, doc_type_for
from ..memory.quotes import QuoteStore
from ..memory.store import MemoryFacade
from ..models import Channel, EmailMeta, Status
from ..service import ApprovalBlockedError, QuoteNotFoundError, QuoteService
from .auth import require_bearer

app = FastAPI(title="QuoteMind API", version=__version__)

# The demo seller identity; real deployments read this from tenant config.
SELLER_BLOCK: dict[str, Any] = {
    "name": "CyberSkill JSC",
    "address": "1st Floor, 207A Nguyen Van Thu, Tan Dinh Ward, Ho Chi Minh City",
    "mst": "0312345678",
    "phone": "(+84)906 878 091",
    "email": "info@cyberskill.world",
    "bank": {
        "bank": "Asia Commercial Joint Stock Bank (ACB)",
        "beneficiary": "CTY CP TV VA PT GIAI PHAP PHAN MEM CYBERSKILL",
        "account": "878196868",
        "swift": "ASCBVNVX",
    },
}


def get_service() -> QuoteService:
    """Build the service from settings. Tests override this via dependency_overrides."""
    settings = get_settings()
    return QuoteService(
        store=QuoteStore.from_settings(settings),
        facade=MemoryFacade.from_settings(settings),
        settings=settings,
        seller_block=SELLER_BLOCK,
    )


ServiceDep = Annotated[QuoteService, Depends(get_service)]


class RfqJson(BaseModel):
    text: str
    customer_hint: str | None = None
    channel: Channel = Channel.PASTE
    email_meta: EmailMeta | None = None


class ApproveBody(BaseModel):
    comment: str | None = None
    waive_flags: list[str] | None = None
    reason: str | None = None


class RejectBody(BaseModel):
    comment: str | None = None


class ReviseBody(BaseModel):
    instruction: str


def _error(status_code: int, code: str, message: str, **details: Any) -> HTTPException:
    body: dict[str, Any] = {"code": code, "message": message}
    if details:
        body["details"] = details
    return HTTPException(status_code=status_code, detail={"error": body})


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


async def _run_pipeline(
    service: QuoteService,
    quote_id: str,
    text: str,
    customer_hint: str | None,
    email: str | None,
) -> None:
    stored = service.store.get_quote(quote_id)
    if stored is None:
        return
    await service.process(
        stored["record"], text, customer_hint=customer_hint, customer_email=email
    )


@app.post("/api/rfq", status_code=202, dependencies=[Depends(require_bearer)])
async def submit_rfq(
    service: ServiceDep, background: BackgroundTasks, request: Request
) -> dict[str, Any]:
    """API-01 / FR-020: JSON text or a multipart file in, 202 out, pipeline runs in background.

    FastAPI cannot mix a JSON body model with File/Form parameters on one route, and FR-020 requires
    both on this path, so the content type is dispatched by hand.
    """
    content_type = request.headers.get("content-type", "")
    filename: str | None = None
    email_meta: EmailMeta | None = None

    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise _error(422, "empty_payload", "multipart request without a file part")
        raw = await upload.read()
        try:  # FR-025
            doc_type_for(upload.filename)
            if len(raw) > MAX_UPLOAD_BYTES:
                raise UnsupportedPayloadError(f"file exceeds the {MAX_UPLOAD_BYTES} byte limit")
        except UnsupportedPayloadError as exc:
            raise _error(422, "unsupported_payload", exc.reason) from exc
        # Only text-bearing uploads run today; PDF and image parsing land with FR-031/032.
        text = raw.decode("utf-8", errors="replace")
        channel: Channel = Channel.UPLOAD
        filename = upload.filename
        hint = form.get("customer_hint")
        hint = hint if isinstance(hint, str) else None
        email: str | None = None
    else:
        try:
            body = RfqJson.model_validate(await request.json())
        except (ValidationError, ValueError) as exc:
            raise _error(422, "empty_payload", "provide either a JSON body or a file") from exc
        text = body.text
        channel = body.channel
        hint = body.customer_hint
        email_meta = body.email_meta
        email = email_meta.from_addr if email_meta else None

    record, created = service.submit(
        text=text, channel=channel, filename=filename, customer_hint=hint, email_meta=email_meta
    )
    if created:
        background.add_task(_run_pipeline, service, record.quote_id, text, hint, email)
    return {
        "quote_id": record.quote_id,
        "quote_number": record.quote_number,
        "status": record.status.value,
        "duplicate": not created,  # FR-024: a re-post returns the original
    }


@app.get("/api/quotes", dependencies=[Depends(require_bearer)])
def list_quotes(
    service: ServiceDep, status: Status | None = None, limit: int = 50
) -> dict[str, Any]:
    """API-02 queue."""
    records = service.queue(status=status, limit=limit)
    return {
        "items": [
            {
                "quote_id": record.quote_id,
                "quote_number": record.quote_number,
                "status": record.status.value,
                "customer_id": record.customer_id,
                "flags": record.flags,
                "totals": record.totals_json,
                "updated_at": record.updated_at.isoformat(),
            }
            for record in records
        ],
        "next_cursor": None,
    }


@app.get("/api/quotes/{quote_id}", dependencies=[Depends(require_bearer)])
def get_quote(service: ServiceDep, quote_id: str) -> dict[str, Any]:
    """API-03 / FR-082: the full review payload."""
    try:
        return service.review(quote_id)
    except QuoteNotFoundError as exc:
        raise _error(404, "not_found", f"no quote {quote_id}") from exc


@app.get("/api/quotes/{quote_id}/audit", dependencies=[Depends(require_bearer)])
def get_audit(service: ServiceDep, quote_id: str) -> dict[str, Any]:
    """API-04 / FR-094: the hash-chained audit trail."""
    events = service.store.list_audit(quote_id)
    return {"events": [event.model_dump(mode="json") for event in events]}


@app.post("/api/quotes/{quote_id}/approve", dependencies=[Depends(require_bearer)])
def approve(service: ServiceDep, quote_id: str, body: ApproveBody | None = None) -> dict[str, Any]:
    """API-06 / FR-083. Blocking flags need an explicit, audited waiver, else 409."""
    payload = body or ApproveBody()
    try:
        record = service.approve(
            quote_id,
            comment=payload.comment,
            waive_flags=payload.waive_flags,
            reason=payload.reason,
        )
    except QuoteNotFoundError as exc:
        raise _error(404, "not_found", f"no quote {quote_id}") from exc
    except ApprovalBlockedError as exc:
        raise _error(409, "blocking_flags", str(exc), flags=exc.flags) from exc
    return {"quote_id": quote_id, "status": record.status.value}


@app.post("/api/quotes/{quote_id}/reject", dependencies=[Depends(require_bearer)])
def reject(service: ServiceDep, quote_id: str, body: RejectBody | None = None) -> dict[str, Any]:
    """API-07."""
    try:
        record = service.reject(quote_id, comment=(body or RejectBody()).comment)
    except QuoteNotFoundError as exc:
        raise _error(404, "not_found", f"no quote {quote_id}") from exc
    return {"quote_id": quote_id, "status": record.status.value}


@app.post("/api/quotes/{quote_id}/revise", status_code=202, dependencies=[Depends(require_bearer)])
async def revise(service: ServiceDep, quote_id: str, body: ReviseBody) -> dict[str, Any]:
    """API-08 / FR-084: re-run the pipeline honouring the instruction."""
    try:
        record = await service.revise(quote_id, instruction=body.instruction)
    except QuoteNotFoundError as exc:
        raise _error(404, "not_found", f"no quote {quote_id}") from exc
    return {"quote_id": quote_id, "status": record.status.value, "revision": record.revision}
