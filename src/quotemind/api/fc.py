"""Function Compute entry points (FR-003).

How FC 3.0 actually invokes an HTTP function - established by logging the arguments in production
rather than by reading documentation, after three wrong guesses cost three deploys:

    handler(event: bytes, context: FCContext)

    event = {"version": "v1", "rawPath": "/health", "headers": {...}, "queryParameters": {...},
             "body": "<str, base64 when isBase64Encoded>", "isBase64Encoded": true,
             "requestContext": {"requestId": ..., "http": {"method": "GET", ...}}}

That is an *event envelope*, not a WSGI environ. FC's runtime does have a WSGI path
(`bootstrap.wsgi_wrapper`), but it only fires when `request.http_params` is populated, and the
`fcapp.run` endpoint does not populate it - it hands the request over as the envelope above and
expects an envelope back:

    {"statusCode": int, "headers": {...}, "isBase64Encoded": bool, "body": str}

So the adapter's job is envelope -> WSGI environ -> app -> envelope. FastAPI is ASGI, so
`a2wsgi.ASGIMiddleware` bridges ASGI to WSGI once, at import, and this module supplies the environ
on each request. Bodies cross the boundary base64-encoded in both directions, because a quote PDF is
bytes and a Vietnamese quote is UTF-8 - neither survives being treated as a latin-1 string.

The WSGI branch is kept: if FC ever *does* hand us `(environ, start_response)`, that shape is
recognised by the second argument being callable, and passed straight through.

`initialize` is the FC initializer: it runs once per cold start, before any request is served, and
performs the FR-012 model-availability probe.
"""

from __future__ import annotations

import base64
import json
from io import BytesIO
from typing import Any, cast
from urllib.parse import urlencode

from a2wsgi import ASGIMiddleware

from ..obs.log import configure_logging
from .app import app
from .app import initialize as _initialize

# FC collects stdout, so JSON lines to stdout is the whole logging story (FR-008).
configure_logging()

# a2wsgi types its argument against the raw ASGI protocol; FastAPI satisfies it structurally but
# not nominally, which is a typing artefact rather than a real mismatch.
_wsgi_app = ASGIMiddleware(app)  # type: ignore[arg-type]

# Headers that describe the body itself are passed to WSGI without the HTTP_ prefix. Getting this
# wrong means a POST body arrives with no content type and FastAPI rejects it as unparseable.
_UNPREFIXED = {"content-type": "CONTENT_TYPE", "content-length": "CONTENT_LENGTH"}


def _event_body(event: dict[str, Any]) -> bytes:
    """The request body as bytes, decoding base64 when FC says it is encoded."""
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        return base64.b64decode(raw)
    return raw.encode()


def _environ(event: dict[str, Any]) -> dict[str, Any]:
    """Translate FC's HTTP event envelope into a WSGI environ."""
    http = event.get("requestContext", {}).get("http", {})
    body = _event_body(event)
    headers: dict[str, str] = event.get("headers") or {}

    # FC sends Host as a comma-joined duplicate ("host,host"). Passed through verbatim it produces
    # an invalid Host header, which Starlette's TrustedHost handling and any URL the app builds from
    # it would both get wrong.
    host = headers.get("Host", headers.get("host", "")).split(",")[0]

    environ: dict[str, Any] = {
        "REQUEST_METHOD": http.get("method", "GET"),
        "SCRIPT_NAME": "",
        "PATH_INFO": event.get("rawPath", http.get("path", "/")),
        "QUERY_STRING": urlencode(event.get("queryParameters") or {}, doseq=True),
        "SERVER_NAME": host or "fc",
        "SERVER_PORT": "443",
        "SERVER_PROTOCOL": http.get("protocol", "HTTP/1.1"),
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": headers.get("X-Forwarded-Proto", "https"),
        "wsgi.input": BytesIO(body),
        "wsgi.errors": BytesIO(),
        "wsgi.multithread": False,
        "wsgi.multiprocess": False,
        "wsgi.run_once": False,
    }
    for name, value in headers.items():
        key = name.lower()
        if key in _UNPREFIXED:
            environ[_UNPREFIXED[key]] = value
        else:
            environ["HTTP_" + key.replace("-", "_").upper()] = value
    return environ


def _invoke(event: dict[str, Any]) -> dict[str, Any]:
    """Run the app against one FC HTTP event and build the response envelope FC expects."""
    captured: dict[str, Any] = {}

    def start_response(status: str, headers: list[tuple[str, str]], exc_info: Any = None) -> Any:
        captured["status"] = status
        captured["headers"] = headers
        return lambda _: None

    # a2wsgi's Environ is a precise TypedDict; the environ we build satisfies it structurally
    # but is assembled dynamically from FC's headers, so it cannot be typed as one.
    chunks = _wsgi_app(cast(Any, _environ(event)), start_response)
    body = b"".join(chunks)

    # Always base64: the body may be a PDF (bytes) or Vietnamese JSON (UTF-8). Declaring it encoded
    # unconditionally means neither case depends on FC guessing the charset right.
    return {
        "statusCode": int(captured["status"].split(" ", 1)[0]),
        "headers": dict(captured["headers"]),
        "isBase64Encoded": True,
        "body": base64.b64encode(body).decode("ascii"),
    }


def handler(first: Any, second: Any) -> Any:
    """The entry point FC invokes.

    Two shapes are possible and they are told apart by what actually arrives, not by an assumption:
    a WSGI call passes a callable second argument (`start_response`); FC's HTTP-event call passes an
    `FCContext`, which is not callable.
    """
    if callable(second):
        return _wsgi_app(first, second)

    event = first if isinstance(first, dict) else json.loads(first)
    return _invoke(event)


def initialize(context: Any = None) -> None:
    """FC initializer. Probes the frozen model ids and activates any documented fallback."""
    _initialize(context)


__all__ = ["handler", "initialize"]
