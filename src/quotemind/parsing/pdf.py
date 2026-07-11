"""FR-031: digital PDF text extraction.

A born-digital PDF already carries its text; the job is only to get it out in reading order and hand
it to the text parser (FR-030). No model call, no OCR, no cost.

The distinction that matters is digital vs scanned. A scanned PDF is a picture of a document: it has
pages but no extractable text, and pretending otherwise would hand the parser an empty string and
produce a confidently empty quote. So `is_scanned()` is checked first and a scanned file is refused
here, to be routed to vision OCR (FR-032) instead of silently parsed into nothing.
"""

from __future__ import annotations

import pypdfium2

MIN_TEXT_CHARS = 40  # below this a "digital" PDF is really a scan with a stray watermark


class ScannedPdfError(ValueError):
    """The PDF carries no extractable text - it needs OCR (FR-032), not text extraction."""


def extract_pdf_text(data: bytes) -> str:
    """Text from a born-digital PDF, pages joined in order. Raises on a scan."""
    document = pypdfium2.PdfDocument(data)
    try:
        pages = [
            document[index].get_textpage().get_text_bounded()
            for index in range(len(document))
        ]
    finally:
        document.close()

    text = "\n".join(page.strip() for page in pages if page.strip()).strip()
    if len(text) < MIN_TEXT_CHARS:
        raise ScannedPdfError(
            f"PDF yielded {len(text)} extractable characters; it looks scanned and needs OCR"
        )
    return text


def is_scanned(data: bytes) -> bool:
    """True when the PDF has no usable text layer."""
    try:
        extract_pdf_text(data)
    except ScannedPdfError:
        return True
    return False
