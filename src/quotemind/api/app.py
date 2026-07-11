"""QuoteMind HTTP API (API-01..13).

The routes are a thin shell: every state change goes through QuoteService, which owns the state
machine and the audit chain. Processing is asynchronous (FR-020) - POST /api/rfq returns 202
immediately and the pipeline runs in the background, ending durably at the approval gate.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Annotated, Any

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, ValidationError
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from .. import __version__
from ..config.bootstrap import ModelStatus, check_models, health_models
from ..config.models import MODEL_CONSTANTS
from ..config.seller import SELLER_BLOCK
from ..config.settings import get_settings
from ..intake import MAX_UPLOAD_BYTES, UnsupportedPayloadError, doc_type_for
from ..memory.quotes import QuoteStore
from ..memory.store import MemoryFacade
from ..models import Channel, DocType, EmailMeta, Status
from ..obs.log import log_event
from ..service import ApprovalBlockedError, QuoteNotFoundError, QuoteService
from ..web import dashboard_html
from .auth import require_bearer

app = FastAPI(title="QuoteMind API", version=__version__)

# FR-106: the dashboard is a static page on OSS, so it calls this API cross-origin. Every route is
# bearer-guarded, so the origin is not the security boundary - the token is.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

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


# FR-012. Filled by the probe, which runs once per process - the first time anything needs to know
# what the models are.
#
# It deliberately does NOT depend on Function Compute's initializer. It used to, and the initializer
# silently never ran: `initializer:` / `initializationTimeout:` is the FC *2.0* spelling, Serverless
# Devs accepted the keys, dropped them, and deployed a function with no initializer at all. The only
# visible symptom was /health reporting every model as unverified - which is precisely what that
# field is for, and it was telling the truth.
#
# Correcting the YAML is necessary but not sufficient. A probe that only runs from a platform hook
# is one config typo away from silently not running again, and FR-012's whole purpose is to know,
# before quoting, whether a frozen model id has been retired. So the probe runs on first need, and
# the initializer merely gets it out of the way before the first request arrives: a warm-up, not a
# correctness dependency.
_MODEL_STATUS: list[ModelStatus] = []
_PROBE_ATTEMPTED = False
_PROBE_LOCK = threading.Lock()


def model_status() -> list[ModelStatus]:
    """The FR-012 probe result, running the probe once per process if it has not run yet.

    Never raises. A boot check that can take the API down is a liability, not a safeguard - and a
    failed probe is not retried per-request, because a DashScope outage must not turn every /health
    into a slow call.
    """
    global _MODEL_STATUS, _PROBE_ATTEMPTED
    if _PROBE_ATTEMPTED:
        return _MODEL_STATUS
    with _PROBE_LOCK:
        if _PROBE_ATTEMPTED:  # another thread got here first
            return _MODEL_STATUS
        try:
            _MODEL_STATUS = check_models(get_settings())
            log_event(
                "model_probe_complete",
                probed=len(_MODEL_STATUS),
                unverified=health_models(_MODEL_STATUS)["unverified"],
            )
        except Exception as exc:  # noqa: BLE001 - a failed probe must not stop the function booting
            log_event(
                "model_bootstrap_failed",
                level=logging.WARNING,
                error=f"{type(exc).__name__}: {exc}",
            )
            _MODEL_STATUS = []
        finally:
            _PROBE_ATTEMPTED = True
    return _MODEL_STATUS


def initialize(_context: Any = None) -> None:
    """FC initializer (FR-003). Warms the FR-012 probe before the first request arrives."""
    model_status()


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard() -> HTMLResponse:
    """FR-106: the operator dashboard, served by the API that backs it.

    The original plan was OSS static website hosting. That plan is still in `deploy/upload_site.py`,
    and it does not work on this account: the artifacts bucket has Block Public Access enabled, so
    OSS refuses `Put public object acl`. The right response is not to switch that off. The bucket
    holds customer quote PDFs, which are handed out as 10-minute presigned URLs precisely because
    they must not be world-readable - a bucket configured to host a public dashboard is a bucket
    that would just as happily serve someone else's quote.

    Serving the page from the API instead costs one route, adds no infrastructure, and makes the
    dashboard same-origin with the API it calls, so the CORS allowance above becomes belt-and-braces
    rather than load-bearing.

    The demo token is embedded in the page. That is deliberate, and it is exactly the exposure the
    OSS plan already had: a public page must carry a credential to be usable at all. It is what
    section 3.2 means by demo-grade, and it is bounded - every write path still stops at the human
    approval gate (FR-070), the token is one rotatable value, and a production tenant would put this
    behind the identity provider section 3.2 also calls for.
    """
    page = dashboard_html()
    page = page.replace("__API_BASE__", "").replace("__API_TOKEN__", get_settings().demo_api_token)
    return HTMLResponse(page)


@app.get("/health")
def health() -> dict[str, Any]:
    """API-11 / FR-009 + FR-012: liveness, version, git SHA, and the models actually in use."""
    body: dict[str, Any] = {
        "status": "ok",
        "version": __version__,
        "git_sha": os.getenv("GIT_SHA", "dev"),
    }
    statuses = model_status()
    if statuses:
        body.update(health_models(statuses))  # includes any fallback substitution, visibly
    else:
        # The probe could not run. Report the frozen constants and say they are unchecked, rather
        # than implying a verification that did not happen.
        body["models"] = MODEL_CONSTANTS
        body["unverified"] = sorted(MODEL_CONSTANTS)
    return body


async def _run_pipeline(
    service: QuoteService,
    quote_id: str,
    payload: str | bytes,
    doc_type: DocType,
    customer_hint: str | None,
    email: str | None,
) -> None:
    stored = service.store.get_quote(quote_id)
    if stored is None:
        return
    await service.process(
        stored["record"],
        payload,
        doc_type=doc_type,
        customer_hint=customer_hint,
        customer_email=email,
    )


def _payload_and_text(
    raw: bytes, doc_type: DocType, filename: str | None
) -> tuple[bytes | str, str]:
    """What the pipeline parses, and what a human sees on the record.

    For text they are the same string. For a file they are not: the pipeline needs the bytes, and
    the record needs something a reviewer can read in a queue - not 40 KB of decoded spreadsheet.
    """
    if doc_type is DocType.EMAIL_TEXT:
        text = raw.decode("utf-8", errors="replace")
        return text, text
    return raw, f"[{doc_type.value}] {filename or 'unnamed'}"


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
            doc_type = doc_type_for(upload.filename)
            if len(raw) > MAX_UPLOAD_BYTES:
                raise UnsupportedPayloadError(f"file exceeds the {MAX_UPLOAD_BYTES} byte limit")
        except UnsupportedPayloadError as exc:
            raise _error(422, "unsupported_payload", exc.reason) from exc

        # FR-021/022/031/032/033: the parser is chosen by document type, and the bytes are handed to
        # it intact. This line used to read `raw.decode("utf-8", errors="replace")` for *every*
        # upload, which turned a spreadsheet into mojibake and then quoted the mojibake.
        payload, text = _payload_and_text(raw, doc_type, upload.filename)
        digest_payload: bytes | str = raw
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
        payload = text
        digest_payload = text
        doc_type = DocType.EMAIL_TEXT
        channel = body.channel
        hint = body.customer_hint
        email_meta = body.email_meta
        email = email_meta.from_addr if email_meta else None

    record, created = service.submit(
        text=text,
        digest_payload=digest_payload,
        channel=channel,
        filename=filename,
        customer_hint=hint,
        email_meta=email_meta,
    )
    if created:
        background.add_task(
            _run_pipeline, service, record.quote_id, payload, doc_type, hint, email
        )
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


@app.get("/api/quotes/{quote_id}/trace", dependencies=[Depends(require_bearer)])
def get_trace(service: ServiceDep, quote_id: str) -> dict[str, Any]:
    """API-05 / FR-111: the persisted reasoning trace (steps, tokens, cost, durations)."""
    try:
        return service.trace(quote_id)
    except QuoteNotFoundError as exc:
        raise _error(404, "not_found", f"no quote {quote_id}") from exc


@app.post("/api/quotes/{quote_id}/approve", dependencies=[Depends(require_bearer)])
def approve(
    service: ServiceDep,
    background: BackgroundTasks,
    quote_id: str,
    body: ApproveBody | None = None,
) -> dict[str, Any]:
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

    background.add_task(service.dispatch, quote_id)  # FR-083: approval triggers dispatch
    return {"quote_id": quote_id, "status": record.status.value}


@app.get("/api/quotes/{quote_id}/pdf", dependencies=[Depends(require_bearer)])
def quote_pdf(service: ServiceDep, quote_id: str) -> RedirectResponse:
    """API-09 / FR-091: 302 to a fresh, short-lived presigned GET on the private object."""
    try:
        url = service.pdf_url(quote_id)
    except QuoteNotFoundError as exc:
        raise _error(404, "not_found", f"no quote {quote_id}") from exc
    return RedirectResponse(url=url, status_code=302)


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
