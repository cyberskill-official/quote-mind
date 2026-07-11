"""FR-031: PDF rasterization.

Pages become PNGs at 200 DPI, downscaled so the long edge is at most 2560 px, capped at 10 pages.

Each of those three limits is doing work, and the reason is the same in every case: a vision model
is billed by image tokens, and image tokens scale with pixels.

- **200 DPI** is where Vietnamese diacritics stay legible on a scan. Below it, the marks that
  distinguish "sổ" from "so" start to dissolve, and an OCR error on a diacritic is not a typo - it
  is a different word.
- **2560 px** is the cap because doubling the long edge quadruples the pixels and therefore roughly
  quadruples the cost, for a document whose text was already legible.
- **10 pages** is a circuit breaker. A 300-page catalogue dropped into the inbox by accident should
  cost a few cents and get refused, not silently bill for a rasterised novel.
"""

from __future__ import annotations

import base64
import io

import pypdfium2
from PIL import Image

DPI = 200
BASE_DPI = 72  # pypdfium2's scale=1
MAX_LONG_EDGE = 2560
MAX_PAGES = 10


class TooManyPagesError(ValueError):
    """The document is longer than the page budget - refuse rather than quietly bill for it."""


def rasterize_pdf(data: bytes, *, max_pages: int = MAX_PAGES) -> list[bytes]:
    """Render each page to a PNG. Raises if the document is over the page budget."""
    document = pypdfium2.PdfDocument(data)
    try:
        page_count = len(document)
        if page_count > max_pages:
            raise TooManyPagesError(
                f"{page_count} pages exceeds the {max_pages}-page limit for vision extraction"
            )
        return [_render(document[index]) for index in range(page_count)]
    finally:
        document.close()


def _render(page: pypdfium2.PdfPage) -> bytes:
    image = page.render(scale=DPI / BASE_DPI).to_pil().convert("RGB")

    longest = max(image.size)
    if longest > MAX_LONG_EDGE:
        ratio = MAX_LONG_EDGE / longest
        image = image.resize(
            (int(image.width * ratio), int(image.height * ratio)), Image.Resampling.LANCZOS
        )

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def to_data_url(png: bytes) -> str:
    """The OpenAI-compatible content array wants a data URL, not raw bytes."""
    return f"data:image/png;base64,{base64.b64encode(png).decode()}"
