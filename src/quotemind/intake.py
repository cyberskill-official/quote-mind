"""Intake classification and guards (FR-022, FR-024, FR-025).

Deterministic on purpose. Document type comes from the filename and content type, language from
Vietnamese diacritics, urgency from keywords - none of that needs a model, and code cannot
hallucinate a doc type. The customer match is left to the pipeline, which resolves it against the
live customers tenant (FR-043) rather than guessing here.
"""

from __future__ import annotations

import hashlib
import re

from .models import CustomerMatch, DocType, EmailMeta, IntakeResult, Language, Urgency

MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # FR-025: 15 MB

_EXTENSION_TYPES: dict[str, DocType] = {
    ".txt": DocType.EMAIL_TEXT,  # a dropped text file / saved email body
    ".eml": DocType.EMAIL_TEXT,
    ".md": DocType.EMAIL_TEXT,
    ".pdf": DocType.PDF_DIGITAL,  # scan vs digital is decided by the rasteriser (FR-031)
    ".xlsx": DocType.EXCEL,
    ".xlsm": DocType.EXCEL,
    ".png": DocType.IMAGE,
    ".jpg": DocType.IMAGE,
    ".jpeg": DocType.IMAGE,
}

_VN_CHARS = set("ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ")
_URGENT_PATTERN = re.compile(
    r"\b(gấp|khẩn|khan cap|urgent|asap|as soon as possible|ngay hôm nay|immediately)\b",
    re.IGNORECASE,
)
_WORD_PATTERN = re.compile(r"[^\W\d_]+", re.UNICODE)


class UnsupportedPayloadError(ValueError):
    """FR-025: the upload is too large or of a type we do not accept."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def payload_hash(payload: bytes | str) -> str:
    """FR-024: sha256 of the raw payload, used to deduplicate re-posts."""
    data = payload.encode("utf-8") if isinstance(payload, str) else payload
    return hashlib.sha256(data).hexdigest()


def doc_type_for(filename: str | None) -> DocType:
    """FR-025: map a filename to a supported doc type, or reject it."""
    if filename is None:
        return DocType.EMAIL_TEXT
    lowered = filename.lower()
    for extension, doc_type in _EXTENSION_TYPES.items():
        if lowered.endswith(extension):
            return doc_type
    raise UnsupportedPayloadError(f"unsupported file type: {filename}")


def validate_upload(filename: str, size_bytes: int) -> DocType:
    """FR-025: reject oversize or unsupported uploads before anything else happens."""
    doc_type = doc_type_for(filename)
    if size_bytes > MAX_UPLOAD_BYTES:
        raise UnsupportedPayloadError(
            f"file exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit: {size_bytes} bytes"
        )
    return doc_type


def detect_language(text: str) -> Language:
    """vi when every word-bearing line carries diacritics, en when none do, else mixed."""
    lines = [line for line in text.splitlines() if _WORD_PATTERN.search(line)]
    if not lines:
        return Language.EN
    with_diacritics = sum(1 for line in lines if any(char in _VN_CHARS for char in line.lower()))
    if with_diacritics == 0:
        return Language.EN
    if with_diacritics == len(lines):
        return Language.VI
    return Language.MIXED


def detect_urgency(text: str) -> Urgency:
    """FR-022 keyword heuristic."""
    return Urgency.HIGH if _URGENT_PATTERN.search(text) else Urgency.NORMAL


def classify(
    *,
    text: str | None = None,
    filename: str | None = None,
    email_meta: EmailMeta | None = None,
) -> IntakeResult:
    """FR-022: language, doc type, urgency. The customer match is resolved later by the pipeline."""
    doc_type = doc_type_for(filename)
    body = text or ""
    return IntakeResult(
        language=detect_language(body),
        doc_type=doc_type,
        urgency=detect_urgency(body),
        customer_match=CustomerMatch(
            customer_id=None, method="deferred_to_pipeline", confidence=0.0
        ),
        email_meta=email_meta,
    )
