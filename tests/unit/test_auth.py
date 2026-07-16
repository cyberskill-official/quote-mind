"""TASK-010: /api/* requires a valid bearer token; errors use the frozen error shape."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from quotemind.api.app import app, get_service

from .test_service import FakeStore, _service

client = TestClient(app)

_VALID = "Bearer test-token-abcdef0123456789"  # matches conftest DEMO_API_TOKEN


@pytest.fixture
def _fake_backend() -> Iterator[None]:
    """The queue route now reads a real store; give it an empty in-memory one."""
    app.dependency_overrides[get_service] = lambda: _service(FakeStore())
    yield
    app.dependency_overrides.clear()


def test_quotes_requires_bearer() -> None:
    response = client.get("/api/quotes")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_quotes_rejects_wrong_token() -> None:
    response = client.get("/api/quotes", headers={"Authorization": "Bearer nope"})
    assert response.status_code == 401


@pytest.mark.usefixtures("_fake_backend")
def test_quotes_accepts_valid_token() -> None:
    response = client.get("/api/quotes", headers={"Authorization": _VALID})
    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None}
