"""Regressions from the live audit of 2026-07-11.

Every bug here passed the whole test suite and failed the moment it met production. That is the
common thread, and it is worth naming: each one lived in a seam that the tests mocked away.

  * The plan and the recalled memories were written to Tablestore and never read back, because
    `put_quote` and `get_quote` keep *separate* column allowlists and only one of them was updated.
    The unit tests used a FakeStore with `**payloads`, which has no allowlist at all - so the fake
    was more permissive than the real thing, and the bug was invisible by construction.
  * Approving a quote that arrived as a file drop sent it to `failed_dispatch`, because a dropped
    file has no sender and dispatch treated "nobody to send to" as an error.
  * Approving an already-decided quote returned 500 instead of 409.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from quotemind.api.app import app, get_service
from quotemind.memory.quotes import PAYLOAD_COLUMNS, QuoteStore
from quotemind.models import Status

from .test_service import FakeStore, _service

_AUTH = {"Authorization": "Bearer test-token-abcdef0123456789"}


def _client(service: Any) -> TestClient:
    app.dependency_overrides[get_service] = lambda: service
    return TestClient(app)


# --- the allowlists that drifted ---
def test_every_column_put_quote_writes_is_a_column_get_quote_reads() -> None:
    """The bug, made structurally impossible.

    `put_quote` gained `plan_json` and `episodic_json`; `get_quote` did not. The plan and the
    memories were persisted on every single quote and read back by nobody, and the two dashboard
    panels built on them were empty in production while every test passed.

    Relying on a human to remember two lists is not a control. This is.
    """
    import inspect  # noqa: PLC0415 - only this test needs to introspect the signature

    written = {
        name
        for name, param in inspect.signature(QuoteStore.put_quote).parameters.items()
        if param.kind is inspect.Parameter.KEYWORD_ONLY
    }
    assert written == set(PAYLOAD_COLUMNS), (
        "put_quote writes a payload column that get_quote will never read back "
        f"(or vice versa). written={sorted(written)} read={sorted(PAYLOAD_COLUMNS)}"
    )


# --- a quote nobody asked us to send is not a failed dispatch ---
def test_a_quote_with_no_recipient_is_approved_and_simply_not_sent() -> None:
    import json  # noqa: PLC0415

    store = FakeStore()
    service = _service(store)
    client = _client(service)
    try:
        body = client.post("/api/rfq", json={"text": "Cần 2 laptop"}, headers=_AUTH).json()
        qid = body["quote_id"]

        # Strip the email off the quote: this is what an OSS file drop looks like. A file has no
        # sender, so there is nobody to send the finished quote back to.
        row = store.rows[qid]
        quote = json.loads(row["quote_json"])
        quote["customer_block"].pop("email", None)
        row["quote_json"] = json.dumps(quote)

        result = client.post(f"/api/quotes/{qid}/approve", json={}, headers=_AUTH)
        assert result.status_code == 200
        assert result.json()["dispatching_to"] is None  # approved, deliberately not sent

        review = client.get(f"/api/quotes/{qid}", headers=_AUTH).json()
        assert review["status"] == Status.APPROVED.value
        assert review["status"] != Status.FAILED_DISPATCH.value  # the bug

        events = [e["event"] for e in review["audit"]]
        assert "dispatch.skipped" in events  # and it says why, on the audit trail
    finally:
        app.dependency_overrides.clear()


def test_a_recipient_supplied_at_the_gate_is_dispatched_to() -> None:
    store = FakeStore()
    service = _service(store)
    client = _client(service)
    try:
        posted = client.post("/api/rfq", json={"text": "Cần 2 laptop"}, headers=_AUTH)
        qid = posted.json()["quote_id"]
        result = client.post(
            f"/api/quotes/{qid}/approve",
            json={"recipient": "chi.lan@thanhcong.vn"},
            headers=_AUTH,
        )
        assert result.status_code == 200
        assert result.json()["dispatching_to"] == "chi.lan@thanhcong.vn"
    finally:
        app.dependency_overrides.clear()


# --- an already-decided quote is a conflict, not a crash ---
def test_approving_twice_is_a_409_not_a_500() -> None:
    store = FakeStore()
    client = _client(_service(store))
    try:
        posted = client.post("/api/rfq", json={"text": "Cần 2 laptop"}, headers=_AUTH)
        qid = posted.json()["quote_id"]
        assert client.post(f"/api/quotes/{qid}/approve", json={}, headers=_AUTH).status_code == 200

        second = client.post(f"/api/quotes/{qid}/approve", json={}, headers=_AUTH)
        assert second.status_code == 409  # was 500: "the system broke" when the caller had
        assert second.json()["error"]["code"] == "illegal_transition"
    finally:
        app.dependency_overrides.clear()


# --- the PDF route cannot 302 on Function Compute ---
def test_the_pdf_route_returns_a_signed_url_rather_than_redirecting_to_it() -> None:
    """FC's default domain rejects a cross-domain 302 (`ExternalRedirectForbidden`), and a plain
    `<a href>` cannot carry the bearer token this route requires. The redirect could never have
    worked from the dashboard; returning the signed URL does, and the object stays private."""
    store = FakeStore()
    service = _service(store)
    service.pdf_url = lambda _id: "https://oss.example/quote.pdf?sig=abc"  # type: ignore[method-assign]
    client = _client(service)
    try:
        posted = client.post("/api/rfq", json={"text": "Cần 2 laptop"}, headers=_AUTH)
        qid = posted.json()["quote_id"]
        response = client.get(f"/api/quotes/{qid}/pdf", headers=_AUTH, follow_redirects=False)

        assert response.status_code == 200  # not 302
        body = response.json()
        assert body["url"].startswith("https://")
        assert body["expires_in"] == 600  # FR-091: short-lived
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("path", ["/api/quotes/nope/pdf", "/api/quotes/nope"])
def test_an_unknown_quote_is_still_a_404(path: str) -> None:
    client = _client(_service(FakeStore()))
    try:
        assert client.get(path, headers=_AUTH).status_code == 404
    finally:
        app.dependency_overrides.clear()
