"""FR-022 classification, FR-024 idempotency hash, FR-025 upload guards."""

from __future__ import annotations

import pytest

from quotemind.intake import (
    MAX_UPLOAD_BYTES,
    UnsupportedPayloadError,
    classify,
    detect_language,
    detect_urgency,
    payload_hash,
    validate_upload,
)
from quotemind.models import DocType, Language, Urgency


def test_payload_hash_is_stable_and_content_addressed() -> None:
    assert payload_hash("xin chào") == payload_hash("xin chào")
    assert payload_hash("xin chào") != payload_hash("xin chao")
    assert len(payload_hash(b"bytes")) == 64


def test_detect_language() -> None:
    assert detect_language("Cần báo giá 10 máy tính xách tay") == Language.VI
    assert detect_language("Please quote 10 laptops") == Language.EN
    assert detect_language("Please quote 10 laptops\nCần gấp trước thứ sáu") == Language.MIXED
    assert detect_language("   ") == Language.EN  # nothing to judge


def test_detect_urgency() -> None:
    assert detect_urgency("Cần báo giá gấp") == Urgency.HIGH
    assert detect_urgency("we need this ASAP") == Urgency.HIGH
    assert detect_urgency("Vui lòng gửi báo giá") == Urgency.NORMAL


def test_doc_type_from_filename() -> None:
    assert validate_upload("rfq.xlsx", 1000) == DocType.EXCEL
    assert validate_upload("scan.pdf", 1000) == DocType.PDF_DIGITAL
    assert validate_upload("photo.JPG", 1000) == DocType.IMAGE


def test_oversize_and_unsupported_are_rejected() -> None:
    with pytest.raises(UnsupportedPayloadError, match="exceeds"):
        validate_upload("rfq.xlsx", MAX_UPLOAD_BYTES + 1)
    with pytest.raises(UnsupportedPayloadError, match="unsupported file type"):
        validate_upload("virus.exe", 10)


def test_classify_text_rfq() -> None:
    result = classify(text="Cần báo giá gấp 10 laptop Dell")
    assert result.doc_type == DocType.EMAIL_TEXT
    assert result.language == Language.VI
    assert result.urgency == Urgency.HIGH
    # The customer is resolved by the pipeline against the live tenant, not guessed here.
    assert result.customer_match.customer_id is None
    assert result.customer_match.method == "deferred_to_pipeline"
