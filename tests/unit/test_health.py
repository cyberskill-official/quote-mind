"""TASK-009 / API-11: /health is unauthenticated and returns the frozen model constants."""

from __future__ import annotations

from fastapi.testclient import TestClient

from quotemind.api.app import app
from quotemind.config import models as model_constants

client = TestClient(app)


def test_health_ok_and_unauthenticated() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "git_sha" in body
    assert body["models"] == model_constants.MODEL_CONSTANTS
    assert body["models"]["embed"] == "text-embedding-v4"
