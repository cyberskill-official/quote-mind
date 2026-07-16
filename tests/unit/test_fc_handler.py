"""TASK-003: the Function Compute adapter.

These tests exist because this adapter was wrong three times in production and each failure looked
identical from outside: a 502 with no stack trace. The event envelope below is not invented - it is
the one FC actually sent, captured from the function's own logs. Testing against a guessed envelope
would have reproduced the bug rather than caught it.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from quotemind.api.fc import handler

# The exact shape FC hands the handler, as logged from a live invocation of /health.
FC_EVENT: dict[str, Any] = {
    "version": "v1",
    "rawPath": "/health",
    "headers": {
        "Accept": "*/*",
        "User-Agent": "curl/8.7.1",
        "X-Forwarded-Proto": "https",
        # FC really does send the host twice, comma-joined.
        "Host": "quotemind-api-x.ap-southeast-1.fcapp.run,quotemind-api-x.ap-southeast-1.fcapp.run",
    },
    "queryParameters": {},
    "body": "",
    "isBase64Encoded": True,
    "requestContext": {
        "requestId": "1-abc",
        "http": {"method": "GET", "path": "/health", "protocol": "HTTP/1.1"},
    },
}


def _body(response: dict[str, Any]) -> bytes:
    assert response["isBase64Encoded"] is True
    return base64.b64decode(response["body"])


def test_the_real_fc_event_envelope_reaches_the_app() -> None:
    response = handler(FC_EVENT, object())  # a context, which is not callable
    assert response["statusCode"] == 200
    assert json.loads(_body(response))["status"] == "ok"


def test_the_envelope_is_accepted_as_bytes_too() -> None:
    # FC delivered it as bytes, not as a parsed dict. Both must work.
    response = handler(json.dumps(FC_EVENT).encode(), object())
    assert response["statusCode"] == 200


def test_a_post_body_survives_the_crossing() -> None:
    # A body that is base64 on the way in must arrive at the app intact - including diacritics,
    # which is the whole reason the boundary is base64 in both directions.
    payload = json.dumps({"text": "Báo giá 10 máy trạm"}).encode()
    event = dict(
        FC_EVENT,
        rawPath="/api/rfq",
        body=base64.b64encode(payload).decode(),
        isBase64Encoded=True,
        headers=dict(FC_EVENT["headers"], **{"Content-Type": "application/json"}),
        requestContext={"http": {"method": "POST", "path": "/api/rfq"}},
    )
    response = handler(event, object())
    # No bearer token, so the app rejects it - but it rejects it as *the app*, having parsed the
    # request. A 502 or a 422 here would mean the body never made it across intact.
    assert response["statusCode"] == 401


def test_an_unknown_path_is_the_app_s_404_not_a_crash() -> None:
    event = dict(FC_EVENT, rawPath="/nope", requestContext={"http": {"method": "GET"}})
    assert handler(event, object())["statusCode"] == 404


def test_query_parameters_are_passed_through() -> None:
    event = dict(FC_EVENT, rawPath="/health", queryParameters={"verbose": "1"})
    assert handler(event, object())["statusCode"] == 200


def test_the_wsgi_shape_is_still_honoured_if_fc_ever_sends_it() -> None:
    # The other branch: a callable second argument means FC unwrapped the request for us.
    seen: dict[str, Any] = {}

    def start_response(status: str, headers: list[Any], exc_info: Any = None) -> Any:
        seen["status"] = status
        return lambda _: None

    from io import BytesIO

    environ = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": "/health",
        "QUERY_STRING": "",
        "SERVER_NAME": "fc",
        "SERVER_PORT": "443",
        "SERVER_PROTOCOL": "HTTP/1.1",
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": "https",
        "wsgi.input": BytesIO(b""),
        "wsgi.errors": BytesIO(),
        "wsgi.multithread": False,
        "wsgi.multiprocess": False,
        "wsgi.run_once": False,
    }
    body = b"".join(handler(environ, start_response))
    assert seen["status"].startswith("200")
    assert json.loads(body)["status"] == "ok"
