"""QuoteMind HTTP API (API-01..13).

The routes are a thin shell: every state change goes through QuoteService, which owns the state
machine and the audit chain. Processing is asynchronous (TASK-020) - POST /api/rfq returns 202
immediately and the pipeline runs in the background, ending durably at the approval gate.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from typing import Annotated, Any

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, ValidationError
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from .. import __version__
from ..cloud.oss import PRESIGNED_TTL_SECONDS
from ..config.bootstrap import ModelStatus, check_models, health_models
from ..config.models import MODEL_CONSTANTS
from ..config.seller import SELLER_BLOCK
from ..config.settings import get_settings
from ..eval_.report import render_report_html
from ..intake import MAX_UPLOAD_BYTES, UnsupportedPayloadError, doc_type_for
from ..memory.quotes import QuoteStore
from ..memory.store import MemoryFacade
from ..models import Channel, DocType, EmailMeta, IllegalTransitionError, Status
from ..obs.log import log_event
from ..service import ApprovalBlockedError, QuoteNotFoundError, QuoteService
from ..web import dashboard_html
from .auth import require_bearer

# ACME tokens are base64url. Anything else is not a challenge, it is someone probing.
_ACME_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{16,128}")

app = FastAPI(title="QuoteMind API", version=__version__)

# TASK-106: the dashboard is a static page on OSS, so it calls this API cross-origin. Every route is
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
    # An RFQ dropped as a file carries no sender, so there is nobody to send the quote back to. The
    # reviewer can supply an address at the gate; without one the quote is approved and simply not
    # sent, which is a state, not a failure.
    recipient: str | None = None


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


# TASK-012. Filled by the probe, which runs once per process - the first time anything needs to know
# what the models are.
#
# It deliberately does NOT depend on Function Compute's initializer. It used to, and the initializer
# silently never ran: `initializer:` / `initializationTimeout:` is the FC *2.0* spelling, Serverless
# Devs accepted the keys, dropped them, and deployed a function with no initializer at all. The only
# visible symptom was /health reporting every model as unverified - which is precisely what that
# field is for, and it was telling the truth.
#
# Correcting the YAML is necessary but not sufficient. A probe that only runs from a platform hook
# is one config typo away from silently not running again, and TASK-012's whole purpose is to know,
# before quoting, whether a frozen model id has been retired. So the probe runs on first need, and
# the initializer merely gets it out of the way before the first request arrives: a warm-up, not a
# correctness dependency.
_MODEL_STATUS: list[ModelStatus] = []
_PROBE_ATTEMPTED = False
_PROBE_LOCK = threading.Lock()


def model_status() -> list[ModelStatus]:
    """The TASK-012 probe result, running the probe once per process if it has not run yet.

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
    """FC initializer (TASK-003). Warms the TASK-012 probe before the first request arrives."""
    model_status()


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard() -> HTMLResponse:
    """TASK-106: the operator dashboard, served by the API that backs it.

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
    approval gate (TASK-070), the token is one rotatable value, and a production tenant would put this
    behind the identity provider section 3.2 also calls for.
    """
    page = dashboard_html()
    page = page.replace("__API_BASE__", "").replace("__API_TOKEN__", get_settings().demo_api_token)
    return HTMLResponse(page)


@app.get("/.well-known/acme-challenge/{token}", include_in_schema=False)
def acme_challenge(token: str) -> PlainTextResponse:
    """Let's Encrypt's HTTP-01 challenge, so the site can have a certificate.

    The custom domain is bound over HTTP - which is what removed Function Compute's forced
    `Content-Disposition: attachment` and made the dashboard a page instead of a download. HTTPS
    needs a certificate, a certificate needs domain validation, and the cheapest honest validation
    is: prove you control what the domain serves. This route is how.

    The answer is read from OSS rather than from an environment variable, and that is the point of
    doing it this way: an env var means a redeploy per challenge, and a redeploy inside an ACME
    validation window is a race nobody should have to run. Renewal is a `put_object` and a `curl`.

    It serves exactly one shape of thing - an ACME key authorization, under a token ACME chose - and
    it can leak nothing else: the key is prefixed, the value is a string Let's Encrypt itself gave
    us, and there is no path traversal to be had from a token that has to match a base64url charset.
    """
    if not _ACME_TOKEN_RE.fullmatch(token):
        raise _error(404, "not_found", "no such challenge")
    try:
        answer = get_service().artifacts.get_acme_challenge(token)
    except Exception as exc:  # noqa: BLE001 - an unissued challenge is a 404, not a 500
        raise _error(404, "not_found", "no such challenge") from exc
    return PlainTextResponse(answer)


@app.get("/eval", response_class=HTMLResponse, include_in_schema=False)
def eval_report() -> HTMLResponse:
    """TASK-104: the measured claim, on the deployed site, without a credential.

    Public on purpose, for the same reason /health is: the headline of this whole project is a
    comparison - 93% against 40% - and a benchmark a judge has to take our word for is not a
    benchmark. The page carries no customer data; it is aggregate metrics over a labelled synthetic
    dataset that ships in the repo, plus one square per case.
    """
    return HTMLResponse(render_report_html())


@app.get("/health")
def health() -> dict[str, Any]:
    """API-11 / TASK-009 + TASK-012: liveness, version, git SHA, and the models actually in use."""
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
    """API-01 / TASK-020: JSON text or a multipart file in, 202 out, pipeline runs in background.

    FastAPI cannot mix a JSON body model with File/Form parameters on one route, and TASK-020 requires
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
        try:  # TASK-025
            doc_type = doc_type_for(upload.filename)
            if len(raw) > MAX_UPLOAD_BYTES:
                raise UnsupportedPayloadError(f"file exceeds the {MAX_UPLOAD_BYTES} byte limit")
        except UnsupportedPayloadError as exc:
            raise _error(422, "unsupported_payload", exc.reason) from exc

        # TASK-021/022/031/032/033: the parser is chosen by document type, and the bytes are handed to
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
        background.add_task(_run_pipeline, service, record.quote_id, payload, doc_type, hint, email)
    return {
        "quote_id": record.quote_id,
        "quote_number": record.quote_number,
        "status": record.status.value,
        "duplicate": not created,  # TASK-024: a re-post returns the original
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
                "stale": service.is_stale(record),  # TASK-085
            }
            for record in records
        ],
        "next_cursor": None,
    }


@app.get("/api/quotes/{quote_id}", dependencies=[Depends(require_bearer)])
def get_quote(service: ServiceDep, quote_id: str) -> dict[str, Any]:
    """API-03 / TASK-082: the full review payload."""
    try:
        return service.review(quote_id)
    except QuoteNotFoundError as exc:
        raise _error(404, "not_found", f"no quote {quote_id}") from exc


@app.get("/api/quotes/{quote_id}/audit", dependencies=[Depends(require_bearer)])
def get_audit(service: ServiceDep, quote_id: str) -> dict[str, Any]:
    """API-04 / TASK-094: the hash-chained audit trail."""
    events = service.store.list_audit(quote_id)
    return {"events": [event.model_dump(mode="json") for event in events]}


@app.get("/api/quotes/{quote_id}/trace", dependencies=[Depends(require_bearer)])
def get_trace(service: ServiceDep, quote_id: str) -> dict[str, Any]:
    """API-05 / TASK-111: the persisted reasoning trace (steps, tokens, cost, durations)."""
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
    """API-06 / TASK-083. Blocking flags need an explicit, audited waiver, else 409."""
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
    except IllegalTransitionError as exc:
        # Approving an already-decided quote is a conflict, not a server error. It used to be a 500,
        # which told the caller the system was broken when in fact the caller was.
        raise _error(409, "illegal_transition", str(exc)) from exc

    # TASK-083: approval triggers dispatch. Always - even with no recipient, because `dispatch` is
    # what writes `dispatch.skipped` to the audit trail, and a quote that is approved but not sent
    # must say why. Guarding this call here would leave the reviewer looking at an approved quote
    # with no explanation for its silence, and would put the decision in two places.
    recipient = payload.recipient or service.recipient_of(quote_id)
    background.add_task(service.dispatch, quote_id, recipient=recipient)
    return {
        "quote_id": quote_id,
        "status": record.status.value,
        "dispatching_to": recipient,  # null means: approved, and deliberately not sent
    }


@app.get("/api/quotes/{quote_id}/pdf", dependencies=[Depends(require_bearer)])
def quote_pdf(service: ServiceDep, quote_id: str) -> dict[str, Any]:
    """API-09 / TASK-091: a fresh, short-lived presigned GET on the private object.

    TASK-091 says *302 to* that URL. This returns it instead, and the reason is not a preference.

    Two independent things made the redirect unusable, and only one of them was about the platform:

      1. Function Compute's default `fcapp.run` domain refuses to emit a cross-domain 302 -
         `ExternalRedirectForbidden: The external redirect is forbidden, please use custom domain
         endpoint`. The route worked under uvicorn and returned 400 the moment it was deployed.
         **This one is gone.** The custom domain is bound (quotemind.cyberskill.world), which is
         exactly the endpoint that error was asking for.
      2. This route is bearer-guarded, and a 302 is only useful to a client that can *follow a
         link*. A plain `<a href>` carries no Authorization header, so it would 401 - which is
         why the PDF button had never worked once, on any domain. A custom domain changes
         nothing about that.

    So the note that used to sit here - "restore the 302 the day a custom domain is bound" - was
    wrong, and it is worth saying why rather than quietly deleting it. It treated the platform
    objection as the whole reason, when the *client* objection is the one that decides. The redirect
    is now merely possible; it was never the better shape.

    What TASK-091 exists to guarantee - the PDF stays a private object, reached by a short-lived
    signed URL rather than a public one - is fully preserved, and preserved more usably: the
    client fetches this with its token and opens the URL it gets back.
    """
    try:
        return {"url": service.pdf_url(quote_id), "expires_in": PRESIGNED_TTL_SECONDS}
    except QuoteNotFoundError as exc:
        raise _error(404, "not_found", f"no quote {quote_id}") from exc


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
    """API-08 / TASK-084: re-run the pipeline honouring the instruction."""
    try:
        record = await service.revise(quote_id, instruction=body.instruction)
    except QuoteNotFoundError as exc:
        raise _error(404, "not_found", f"no quote {quote_id}") from exc
    return {"quote_id": quote_id, "status": record.status.value, "revision": record.revision}


@app.post("/api/quotes/{quote_id}/cancel", dependencies=[Depends(require_bearer)])
def cancel(service: ServiceDep, quote_id: str, body: RejectBody | None = None) -> dict[str, Any]:
    """TASK-134: cancel a quote, with the HITL gate's own semantics.

    TASK-134 asks for an interrupt hook that can cancel an *in-flight* run. This implements the half
    of it that can be implemented honestly, and refuses the other half rather than faking it.

    A quote waiting at the gate is cancelled by ending it - which is what `rejected` already means,
    so cancel is a reject carrying its reason. The audit trail says `human.cancel`, so "the operator
    stopped this" and "the reviewer turned it down" stay distinguishable forever, which is the part
    that matters.

    A quote still *running* is a different question, and the answer is 409. Two reasons, both real:

      * The pipeline runs inside a FastAPI BackgroundTask, in the same Function Compute invocation
        that accepted the RFQ. There is no second process holding a handle to it. Cancelling would
        mean adding a flag in Tablestore and polling it between stages - which is a real design, and
        a bigger one than this task is worth.
      * The status enum is frozen (section 12.5) and has no `cancelled`. Landing an interrupted run
        in `failed_parse` would put a lie on a hash-chained audit trail: nothing failed. Landing it
        in `needs_manual` is not reachable from `parsing` or `matching` under LEGAL_TRANSITIONS, and
        widening that table to make one task fit is exactly the change section 12 says to stop and ask
        about.

    So: cancellable at the gate, 409 while running, and the reason is on the record rather than in
    someone's head.
    """
    try:
        record = service.cancel(quote_id, comment=(body or RejectBody()).comment)
    except QuoteNotFoundError as exc:
        raise _error(404, "not_found", f"no quote {quote_id}") from exc
    except IllegalTransitionError as exc:
        raise _error(
            409,
            "illegal_transition",
            f"a quote in {exc.current.value} cannot be cancelled: the run is already under way "
            "and Function Compute cannot interrupt it. Wait for the approval gate.",
        ) from exc
    return {"quote_id": quote_id, "status": record.status.value, "cancelled": True}
