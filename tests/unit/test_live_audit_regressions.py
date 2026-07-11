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
from quotemind.models import Channel, Language, QuoteRecord, Status

from .test_service import FakeStore, _service

_AUTH = {"Authorization": "Bearer test-token-abcdef0123456789"}


def _client(service: Any) -> TestClient:
    app.dependency_overrides[get_service] = lambda: service
    return TestClient(app)


# --- the allowlists that drifted ---
def test_put_quote_writes_exactly_the_columns_get_quote_reads() -> None:
    """The bug, made structurally impossible - on the second attempt.

    There were THREE lists of payload columns: a keyword-only signature on `put_quote`, an inline
    tuple in its body that did the actual writing, and `PAYLOAD_COLUMNS` on the read side.

    `plan_json` and `episodic_json` were added to the first two and forgotten in the third: written
    to Tablestore, read back by nobody, two dashboard panels empty in production, 310 tests green.
    The fix added the name to the signature and to PAYLOAD_COLUMNS and asserted *those two* agreed -
    and the very next column, `extraction_json`, was dropped by the inline tuple the test did not
    know about. Live. Twice. The same shape.

    So the other two lists are gone. This asserts the one that is left is the one that writes.
    """
    written: list[tuple[str, str]] = []

    class _Client:
        def update_row(self, _table: str, row: Any, _cond: Any) -> None:
            written.extend(row.attribute_columns["PUT"])

    store = QuoteStore.__new__(QuoteStore)
    store.client = _Client()  # type: ignore[assignment]
    record = QuoteRecord(
        quote_id="01J",
        quote_number="QM-2026-0001",
        status=Status.RECEIVED,
        channel=Channel.PASTE,
        language=Language.VI,
    )
    store.put_quote(record, **{name: f"<{name}>" for name in PAYLOAD_COLUMNS})

    reached_tablestore = {name for name, _ in written}
    for name in PAYLOAD_COLUMNS:
        assert name in reached_tablestore, (
            f"{name} is in PAYLOAD_COLUMNS - so get_quote will look for it - but put_quote never "
            "wrote it. It will be empty in production and green in CI."
        )


def test_put_quote_refuses_a_column_it_cannot_persist() -> None:
    """Raise, do not drop. A silent drop is what left a green suite and an empty panel."""
    store = QuoteStore.__new__(QuoteStore)
    record = QuoteRecord(
        quote_id="01J",
        quote_number="QM-2026-0001",
        status=Status.RECEIVED,
        channel=Channel.PASTE,
        language=Language.VI,
    )
    with pytest.raises(ValueError, match="not a persisted quote column"):
        store.put_quote(record, invented_json="{}")


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


# --- a revision must not throw away the lines it is revising ---
def test_revising_a_file_sourced_quote_keeps_its_line_items() -> None:
    """The last place still reaching for a source document that was never there.

    `revise()` used to append the instruction to `source_text` and re-run the *text* pipeline. For a
    quote that arrived as a spreadsheet, a PDF or a photo, `source_text` is a placeholder - the
    bytes are the document, and the text is only what a human reads on the record. So the parser was
    handed "[Excel: bao-gia.xlsx]" plus a discount request, and the revised quote came back with no
    line items at all.

    Every test passed, because every test revised a quote that had been *pasted as text* - the one
    channel where the placeholder happens to be the real thing.
    """
    import asyncio  # noqa: PLC0415

    store = FakeStore()
    service = _service(store)

    record, _ = service.submit(text="Cần 2 laptop", filename="bao-gia.xlsx")
    asyncio.run(service.process(record, "Cần 2 laptop"))

    # This is the state a file-sourced quote is actually in: the extraction is real, and the source
    # text is a placeholder, because the spreadsheet's *bytes* were the document and they are gone.
    store.rows[record.quote_id]["source_text"] = "[Excel: bao-gia.xlsx]"

    revised = asyncio.run(service.revise(record.quote_id, instruction="Chiết khấu thêm 3%"))

    # The old code re-parsed that placeholder. The fake revision pipeline asserts it is handed an
    # RFQExtraction rather than a string, which is precisely the distinction the bug erased.
    assert revised.status is Status.PENDING_APPROVAL
    assert revised.revision == 1
    stored = store.rows[record.quote_id]
    assert stored["extraction_json"], "the extraction is what a revision re-drafts from"
    assert "Laptop" in stored["extraction_json"]  # the lines survived the round trip


def test_a_quote_with_no_stored_extraction_is_sent_to_a_human_not_guessed_at() -> None:
    """Guessing from a placeholder is precisely what caused the bug. Refuse instead."""
    import asyncio  # noqa: PLC0415

    store = FakeStore()
    service = _service(store)
    record, _ = service.submit(text="Cần 2 laptop")
    store.rows.setdefault(record.quote_id, {})["record"] = record
    record.status = Status.PENDING_APPROVAL  # a legacy row: priced, but no extraction was kept

    revised = asyncio.run(service.revise(record.quote_id, instruction="Giảm 5%"))
    assert revised.status is Status.NEEDS_MANUAL
    events = [event.event for event in store.list_audit(record.quote_id)]
    assert "revision.no_extraction" in events  # it says why, rather than inventing a quote


@pytest.mark.parametrize("path", ["/api/quotes/nope/pdf", "/api/quotes/nope"])
def test_an_unknown_quote_is_still_a_404(path: str) -> None:
    client = _client(_service(FakeStore()))
    try:
        assert client.get(path, headers=_AUTH).status_code == 404
    finally:
        app.dependency_overrides.clear()
