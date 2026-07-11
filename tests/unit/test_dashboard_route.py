"""FR-106: the dashboard, and the design system it is bound to.

Two classes of failure are guarded here.

The first is invisible locally and fatal in production: the page, or the CSS it needs, being absent
from the deployed bundle. It exists on the developer's disk, so every test passes, and `GET /` 500s
for the customer.

The second is slower and worse: the design system quietly drifting. `vendor/` holds byte-for-byte
copies of github.com/cyberskill-official/design-system, and the whole point of vendoring is undone
the moment someone "just tweaks" a colour in the copy. The design system calls Umber and Ochre
*anchor immutables*; these tests make an edit to them fail loudly rather than ship silently.
"""

from __future__ import annotations

import hashlib
import re

from fastapi.testclient import TestClient

from quotemind.api.app import app
from quotemind.web import dashboard_html, design_system_css, logo_mark, manifest

UMBER = "#45210E"
OCHRE = "#F4BA17"


# --- the vendored design system is a copy, not a fork ---
def test_every_vendored_file_still_matches_the_hash_it_was_vendored_at() -> None:
    from importlib.resources import files  # noqa: PLC0415 - only this test needs the loader

    for name, expected in manifest()["sha256"].items():
        raw = (files("quotemind.web.vendor") / name).read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        assert actual == expected, (
            f"{name} no longer matches the design system it was vendored from. "
            "Do not edit vendored files - re-copy from upstream and refresh MANIFEST.json."
        )


def test_the_manifest_records_where_the_design_system_came_from() -> None:
    # A vendored dependency with no provenance is a fork nobody admitted to.
    recorded = manifest()
    assert "cyberskill-official/design-system" in str(recorded["source"])
    assert re.fullmatch(r"[0-9a-f]{40}", str(recorded["commit"]))
    assert recorded["design_system_version"]


def test_the_brand_anchors_are_the_immutable_ones() -> None:
    css = design_system_css()
    assert f"--cs-color-brand-umber: {UMBER}" in css
    assert f"--cs-color-brand-ochre: {OCHRE}" in css


def test_the_logo_is_the_master_file_not_a_recreation() -> None:
    # DESIGN.md 1.2.x: the official mark must be "reproduced from the master file, never recreated,
    # retraced, retyped, recoloured". Redrawing it in CSS would have been quicker, and wrong. This
    # asserts we ship the real vector, in the real anchor colours.
    svg = logo_mark()
    assert svg.lstrip().startswith("<svg")
    assert UMBER in svg and OCHRE in svg


def test_the_design_system_loads_in_the_order_it_documents() -> None:
    # tokens -> styles -> glass. Glass composes from the token scalars, so a glass rule that lands
    # before its tokens silently falls back to its hardcoded defaults and the theme stops working.
    css = design_system_css()
    tokens = css.index("--cs-color-brand-umber")
    styles = css.index(".cs-button")
    glass = css.index(".cs-surface-heavy")
    assert tokens < styles < glass


# --- the page reaches the runtime, with its CSS ---
def test_the_dashboard_ships_inside_the_package() -> None:
    html = dashboard_html()
    assert "<!doctype html>" in html.lower()
    assert "__API_BASE__" in html and "__API_TOKEN__" in html  # filled at serve time


def test_the_design_system_is_inlined_and_no_placeholder_survives() -> None:
    html = dashboard_html()
    assert "__CS_DESIGN_SYSTEM__" not in html
    assert "__CS_LOGO_MARK__" not in html
    assert "--cs-color-brand-umber" in html  # the tokens really are in the page
    assert "<svg" in html  # so is the mark


def test_the_root_route_serves_the_dashboard() -> None:
    response = TestClient(app).get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "QuoteMind" in response.text


def test_the_served_page_is_wired_to_this_api_and_carries_the_token() -> None:
    body = TestClient(app).get("/").text

    # An unsubstituted __API_BASE__ falls back to localhost, so the deployed dashboard would
    # silently call a machine that is not there.
    assert "__API_BASE__" not in body
    assert "__API_TOKEN__" not in body
    assert 'const API_BASE = ""' in body  # same-origin
    assert 'const API_TOKEN = "test-token-abcdef0123456789"' in body


# --- what the page claims about AI, which had better be true ---
def test_the_page_discloses_ai_use_precisely_and_not_in_a_blanket() -> None:
    # The design system requires disclosure on every AI-generated region. A blanket "AI-generated"
    # would be false in the direction that matters: it would imply a model priced the quote, which
    # is the one thing this system is built never to do.
    body = TestClient(app).get("/").text
    assert 'property="ai:generated" content="partial"' in body
    assert "sku-matching" in body  # what IS the model's work
    assert "grand-total" in body  # what is NOT
    assert 'property="ai:deterministic-regions"' in body
    assert 'property="ai:human-review" content="required-before-send"' in body


def test_the_human_gate_is_rendered_as_the_design_system_s_own_component() -> None:
    # Part 3h rule 4: financial output goes through a HumanReviewGate. QuoteMind has one; the page
    # must show it as one rather than as three unlabelled buttons.
    body = TestClient(app).get("/").text
    assert "cs-review-gate" in body
    assert "cs-ai-disclosure__badge" in body


def test_the_page_never_promotes_a_model_s_self_reported_confidence_to_a_number() -> None:
    # Part 3h rule 2: confidence is calibrated before it is numeric. The matcher emits a
    # self-reported 0.99 on every line; rendering that as a confidence would be false precision
    # dressed up as rigour. If a future change starts printing it, this fails.
    body = TestClient(app).get("/").text
    assert "l.confidence" not in body
    assert "match.confidence" not in body
