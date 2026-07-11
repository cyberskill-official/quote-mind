"""FR-021/022/024/031/032/033: a file that arrives as a file is parsed as a file.

The regression suite for a bug that lived in production while the eval reported 97% on the very
files it broke. Both intake channels - the API upload and the OSS drop - decoded *every* payload
with `raw.decode("utf-8", errors="replace")`, so a spreadsheet became mojibake and a scanned PDF
became noise. The eval never caught it, because the eval calls `quote_from_excel` and
`quote_from_pdf` directly: it proved the parsers and never touched the seam joining them to the
product.

So these tests assert on the *seam*. They check which pipeline a channel selects and what it hands
it - not whether the parser works, which is tested elsewhere. A test that merely asserted "a quote
came out" would have passed against the broken code, because a quote did come out. It was just
parked at `received` with nothing in it.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient

from quotemind.api.app import app, get_service
from quotemind.models import Channel, DocType, Status
from quotemind.service import QuoteService

from .test_service import FakeStore, _result, _Settings

_AUTH = {"Authorization": "Bearer test-token-abcdef0123456789"}

XLSX = b"PK\x03\x04fake-spreadsheet-bytes"
PDF = b"%PDF-1.7\nfake-pdf-bytes"
PNG = b"\x89PNG\r\n\x1a\nfake-image-bytes"


class Spy:
    """Records which pipeline ran and exactly what payload it was handed."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def pipeline(self, name: str) -> Any:
        async def run(payload: Any, *, sequence: int, **_kwargs: Any) -> Any:
            self.calls.append((name, payload))
            return _result(sequence)

        return run

    @property
    def routed_to(self) -> str:
        assert len(self.calls) == 1, f"expected exactly one pipeline call, got {self.calls}"
        return self.calls[0][0]

    @property
    def payload(self) -> Any:
        return self.calls[0][1]


class _IngestSettings(_Settings):  # type: ignore[misc, valid-type]
    """The drop path builds source_uri from the bucket name, which the base fake does not carry."""

    oss_bucket_inbox = "quotemind-inbox"


def _service(store: FakeStore, spy: Spy) -> QuoteService:
    return QuoteService(
        store=store,  # type: ignore[arg-type]
        facade=object(),  # type: ignore[arg-type]
        settings=_IngestSettings(),  # type: ignore[arg-type]
        seller_block={"name": "CyberSkill JSC"},
        pipeline=spy.pipeline("text"),
        excel_pipeline=spy.pipeline("excel"),
        pdf_pipeline=spy.pipeline("pdf"),
        image_pipeline=spy.pipeline("image"),
    )


def _client(spy: Spy, store: FakeStore | None = None) -> TestClient:
    service = _service(store or FakeStore(), spy)  # built once: one store for the whole request set
    app.dependency_overrides[get_service] = lambda: service
    return TestClient(app)


def _upload(client: TestClient, name: str, data: bytes) -> dict[str, Any]:
    response = client.post("/api/rfq", files={"file": (name, data)}, headers=_AUTH)
    assert response.status_code == 202, response.text
    body: dict[str, Any] = response.json()
    return body


# --- the API upload channel ---
@pytest.mark.parametrize(
    ("filename", "data", "expected"),
    [
        ("rfq.xlsx", XLSX, "excel"),
        ("rfq.pdf", PDF, "pdf"),
        ("rfq.png", PNG, "image"),
        ("rfq.txt", "Cần báo giá 2 laptop".encode(), "text"),
    ],
)
def test_an_upload_is_routed_by_document_type(filename: str, data: bytes, expected: str) -> None:
    spy = Spy()
    client = _client(spy)
    try:
        _upload(client, filename, data)
        assert spy.routed_to == expected
    finally:
        app.dependency_overrides.clear()


def test_a_spreadsheet_reaches_the_parser_as_bytes_not_as_mojibake() -> None:
    # The whole bug in one assertion. The old code handed the pipeline
    # `XLSX.decode("utf-8", errors="replace")` - a string of replacement characters.
    spy = Spy()
    client = _client(spy)
    try:
        _upload(client, "rfq.xlsx", XLSX)
        assert spy.payload == XLSX
        assert isinstance(spy.payload, bytes)
    finally:
        app.dependency_overrides.clear()


def test_a_text_rfq_still_reaches_the_parser_as_text() -> None:
    spy = Spy()
    client = _client(spy)
    try:
        client.post("/api/rfq", json={"text": "Cần báo giá 2 laptop"}, headers=_AUTH)
        assert spy.routed_to == "text"
        assert spy.payload == "Cần báo giá 2 laptop"
    finally:
        app.dependency_overrides.clear()


def test_the_record_shows_a_label_not_forty_kilobytes_of_decoded_spreadsheet() -> None:
    spy = Spy()
    store = FakeStore()
    client = _client(spy, store)
    try:
        body = _upload(client, "báo-giá.xlsx", XLSX)
        row = store.get_quote(body["quote_id"])
        assert row is not None
        # The reviewer sees a label, not the replacement characters a decoded .xlsx turns into.
        assert row["source_text"] == "[excel] báo-giá.xlsx"  # diacritics intact
        assert "\ufffd" not in row["source_text"]
    finally:
        app.dependency_overrides.clear()


def test_an_upload_ends_at_the_approval_gate_and_never_parked_at_received() -> None:
    # The observable symptom in production: a numbered quote, stuck at `received`, forever.
    spy = Spy()
    client = _client(spy)
    try:
        body = _upload(client, "rfq.xlsx", XLSX)
        review = client.get(f"/api/quotes/{body['quote_id']}", headers=_AUTH).json()
        assert review["status"] == Status.PENDING_APPROVAL.value
        assert review["status"] != Status.RECEIVED.value
    finally:
        app.dependency_overrides.clear()


# --- FR-024, which the old code got wrong for files ---
def test_the_same_file_under_a_different_name_is_still_one_quote() -> None:
    spy = Spy()
    client = _client(spy)
    try:
        first = _upload(client, "rfq.xlsx", XLSX)
        second = _upload(client, "rfq-copy.xlsx", XLSX)
        assert second["quote_id"] == first["quote_id"]
        assert second["duplicate"] is True
    finally:
        app.dependency_overrides.clear()


def test_two_different_files_sharing_a_name_are_two_quotes() -> None:
    # The old code hashed the placeholder text, so these two collided into one quote and the second
    # customer silently received the first customer's prices.
    spy = Spy()
    client = _client(spy)
    try:
        first = _upload(client, "rfq.xlsx", XLSX)
        second = _upload(client, "rfq.xlsx", XLSX + b"different")
        assert second["quote_id"] != first["quote_id"]
        assert second["duplicate"] is False
    finally:
        app.dependency_overrides.clear()


# --- the OSS drop channel: the same routing, because it is the same code ---
class FakeArtifacts:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects

    def get_inbox_object(self, key: str) -> bytes:
        return self.objects[key]

    def list_inbox(self) -> list[str]:
        return list(self.objects)


@pytest.mark.parametrize(
    ("key", "data", "expected"),
    [
        ("rfq/order.xlsx", XLSX, "excel"),
        ("rfq/scan.pdf", PDF, "pdf"),
        ("rfq/photo.jpg", PNG, "image"),
        ("rfq/email.txt", "Cần báo giá".encode(), "text"),
    ],
)
def test_an_oss_drop_is_routed_by_document_type(key: str, data: bytes, expected: str) -> None:
    from deploy.ingest import ingest_key  # noqa: PLC0415 - deploy/ is not an installed package

    spy = Spy()
    service = _service(FakeStore(), spy)
    record = asyncio.run(ingest_key(service, FakeArtifacts({key: data}), key))  # type: ignore[arg-type]

    assert spy.routed_to == expected
    assert record.channel is Channel.OSS_DROP
    # The symptom that started this: a dropped spreadsheet became a quote stuck at `received`.
    assert record.status is not Status.RECEIVED
    assert record.source_uri == f"oss://quotemind-inbox/{key}"


def test_a_dropped_spreadsheet_reaches_the_parser_as_bytes() -> None:
    from deploy.ingest import ingest_key  # noqa: PLC0415

    spy = Spy()
    service = _service(FakeStore(), spy)
    asyncio.run(ingest_key(service, FakeArtifacts({"rfq/o.xlsx": XLSX}), "rfq/o.xlsx"))  # type: ignore[arg-type]
    assert spy.payload == XLSX


def test_the_same_bytes_dropped_twice_is_one_quote() -> None:
    from deploy.ingest import ingest_key  # noqa: PLC0415

    spy = Spy()
    service = _service(FakeStore(), spy)
    artifacts = FakeArtifacts({"rfq/a.xlsx": XLSX, "rfq/b.xlsx": XLSX})

    first = asyncio.run(ingest_key(service, artifacts, "rfq/a.xlsx"))  # type: ignore[arg-type]
    second = asyncio.run(ingest_key(service, artifacts, "rfq/b.xlsx"))  # type: ignore[arg-type]

    assert second.quote_id == first.quote_id  # FR-024
    assert len(spy.calls) == 1, "the duplicate must not re-run the pipeline (or re-bill for it)"


def test_every_document_type_has_a_pipeline() -> None:
    # A DocType with no route is a KeyError in production, on the one path nobody is watching.
    service = _service(FakeStore(), Spy())
    assert set(service._pipelines) == set(DocType)
