"""FR-106: the dashboard is served by the API, and it must actually be in the bundle."""

from __future__ import annotations

from fastapi.testclient import TestClient

from quotemind.api.app import app
from quotemind.web import dashboard_html


def test_the_dashboard_ships_inside_the_package() -> None:
    # The failure this guards is invisible locally: the file exists on disk during development and
    # is stripped from the deployed bundle, so `GET /` 500s in production only.
    html = dashboard_html()
    assert "<!doctype html>" in html.lower()
    assert "__API_BASE__" in html and "__API_TOKEN__" in html  # placeholders, filled at serve time


def test_the_root_route_serves_the_dashboard() -> None:
    response = TestClient(app).get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "QuoteMind" in response.text


def test_the_served_page_is_wired_to_this_api_and_carries_the_token() -> None:
    body = TestClient(app).get("/").text

    # No placeholder may survive: an unsubstituted __API_BASE__ falls back to localhost, and the
    # deployed dashboard would silently call a machine that is not there.
    assert "__API_BASE__" not in body
    assert "__API_TOKEN__" not in body

    # Same-origin: the page calls the API that served it, so no absolute host is baked in.
    assert 'const API_BASE = ""' in body
    assert 'const API_TOKEN = "test-token-abcdef0123456789"' in body  # from the test settings
