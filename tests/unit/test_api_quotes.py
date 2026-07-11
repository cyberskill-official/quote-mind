"""API-01..08: the HTTP surface over QuoteService (auth, 202, idempotency, 409, 404, 422)."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from quotemind.api.app import app, get_service
from quotemind.models import Status

from .test_service import FakeStore, _service

_AUTH = {"Authorization": "Bearer test-token-abcdef0123456789"}
_RFQ = {"text": "Cần báo giá 2 laptop Dell Latitude 5450"}


def _client(store: FakeStore, *, thin_margin: bool = False) -> TestClient:
    service = _service(store, thin_margin=thin_margin)
    app.dependency_overrides[get_service] = lambda: service
    return TestClient(app)


def _teardown() -> None:
    app.dependency_overrides.clear()


def test_submit_runs_the_pipeline_and_review_shows_pending_approval() -> None:
    store = FakeStore()
    client = _client(store)
    try:
        response = client.post("/api/rfq", json=_RFQ, headers=_AUTH)
        assert response.status_code == 202  # FR-020
        body: dict[str, Any] = response.json()
        assert body["duplicate"] is False
        quote_id = body["quote_id"]

        # TestClient runs the background task before returning, so the pipeline has completed.
        review = client.get(f"/api/quotes/{quote_id}", headers=_AUTH).json()
        assert review["status"] == Status.PENDING_APPROVAL.value
        assert review["quote"]["quote_number"] == body["quote_number"]
        assert review["totals"]["total_vnd"] > 0
        assert review["audit"][0]["event"] == "intake.received"

        queue = client.get("/api/quotes", params={"status": "pending_approval"}, headers=_AUTH)
        assert [item["quote_id"] for item in queue.json()["items"]] == [quote_id]
    finally:
        _teardown()


def test_reposting_the_same_rfq_returns_the_original() -> None:
    store = FakeStore()
    client = _client(store)
    try:
        first = client.post("/api/rfq", json=_RFQ, headers=_AUTH).json()
        second = client.post("/api/rfq", json=_RFQ, headers=_AUTH).json()
        assert second["quote_id"] == first["quote_id"]  # FR-024
        assert second["duplicate"] is True
    finally:
        _teardown()


def test_approve_conflicts_on_blocking_flags_then_succeeds_with_a_waiver() -> None:
    store = FakeStore()
    client = _client(store, thin_margin=True)
    try:
        quote_id = client.post("/api/rfq", json=_RFQ, headers=_AUTH).json()["quote_id"]

        blocked = client.post(f"/api/quotes/{quote_id}/approve", json={}, headers=_AUTH)
        assert blocked.status_code == 409  # FR-083 AC
        assert blocked.json()["error"]["details"]["flags"] == ["MARGIN_BELOW_FLOOR"]

        waived = client.post(
            f"/api/quotes/{quote_id}/approve",
            json={"waive_flags": ["MARGIN_BELOW_FLOOR"], "reason": "strategic"},
            headers=_AUTH,
        )
        assert waived.status_code == 200
        assert waived.json()["status"] == Status.APPROVED.value
    finally:
        _teardown()


def test_revise_returns_202_and_bumps_the_revision() -> None:
    store = FakeStore()
    client = _client(store)
    try:
        quote_id = client.post("/api/rfq", json=_RFQ, headers=_AUTH).json()["quote_id"]
        response = client.post(
            f"/api/quotes/{quote_id}/revise", json={"instruction": "Giảm 5%"}, headers=_AUTH
        )
        assert response.status_code == 202
        assert response.json()["revision"] == 1
    finally:
        _teardown()


def test_unsupported_upload_is_rejected() -> None:
    store = FakeStore()
    client = _client(store)
    try:
        response = client.post(
            "/api/rfq", files={"file": ("virus.exe", b"nope", "application/octet-stream")},
            headers=_AUTH,
        )
        assert response.status_code == 422  # FR-025
        assert response.json()["error"]["code"] == "unsupported_payload"
    finally:
        _teardown()


def test_auth_and_not_found() -> None:
    store = FakeStore()
    client = _client(store)
    try:
        assert client.post("/api/rfq", json=_RFQ).status_code == 401  # FR-010
        missing = client.get("/api/quotes/does-not-exist", headers=_AUTH)
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "not_found"
    finally:
        _teardown()
