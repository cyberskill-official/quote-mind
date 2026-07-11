"""AGT-03 DocumentParser: vision extraction from scans (FR-032).

A scanned công văn is a photograph of a document. `qwen-vl-ocr` reads it; everything else about the
pipeline is unchanged, because the output is the same `RFQExtraction` the text parser produces.

Three things here are load-bearing and worth stating, because each is a place where a plausible
shortcut would quietly corrupt a quote:

- **The model is asked for JSON, not for a description.** A vision model asked to "read this
  document" will happily narrate it, and the narration will contain numbers that are almost right.
  So the instruction demands JSON conforming to the schema, and the code parses it rather than
  interpreting prose.
- **Fences are stripped, and only fences.** Vision models wrap JSON in ```json blocks far more often
  than text models do. Stripping the fence is fine. "Repairing" the JSON inside it is not - a model
  that emitted malformed JSON was confused, and a regex that patches it into something parseable
  just launders that confusion into a confident quote.
- **Pages are merged with de-duplication by (description, quantity).** A line item that straddles a
  page break, or a repeated table header, otherwise becomes a second line - and a duplicated line is
  a doubled charge. De-duplication is on the *pair*, not on the description alone: two genuine lines
  for the same product at different quantities must both survive.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from openai import OpenAI

from ..config.models import MODEL_PARSER_VISION
from ..config.settings import Settings
from ..models import Buyer, Language, RFQExtraction, RFQLine
from ..parsing.raster import rasterize_pdf, to_data_url
from .model import UsageSink

VISION_SYS = """Bạn đọc một trang yêu cầu báo giá (RFQ) đã được scan.

Trích xuất CHÍNH XÁC những gì nhìn thấy trên trang, trả về JSON thuần (không giải thích, không văn
xuôi) theo đúng cấu trúc:

{"buyer": {"company": string|null, "email": string|null,
           "contact": string|null, "mst": string|null},
 "lines": [{"raw_text": string, "description_normalized": string,
            "quantity": number|null, "unit": string|null, "confidence": number}]}

Quy tắc:
- Giữ nguyên dấu tiếng Việt. "sổ" và "so" là hai từ khác nhau.
- quantity là con số trên trang. Nếu không đọc được, đặt null - TUYỆT ĐỐI không đoán.
- confidence trong [0,1]: bạn tự tin đến đâu là đọc đúng dòng đó.
- Nếu trang này không có dòng hàng nào (bìa, chữ ký, trang trắng), trả về "lines": [].
- Chỉ trả về JSON. Không có ```."""

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)


class VisionParseError(ValueError):
    """The model did not return usable JSON. A confused model must not produce a confident quote."""


def strip_fence(raw: str) -> str:
    """Remove a ```json wrapper. Nothing else - malformed JSON inside stays malformed."""
    return _FENCE.sub("", raw).strip()


def _quantity(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None  # unreadable is null, never a guess


def parse_page(raw: str, *, page: int) -> tuple[Buyer, list[RFQLine]]:
    """One page's JSON -> a buyer and its lines."""
    try:
        payload = json.loads(strip_fence(raw))
    except json.JSONDecodeError as exc:
        raise VisionParseError(f"page {page}: model did not return JSON ({exc})") from exc
    if not isinstance(payload, dict):
        raise VisionParseError(f"page {page}: expected a JSON object, got {type(payload).__name__}")

    buyer_raw = payload.get("buyer") or {}
    buyer = Buyer(
        company=buyer_raw.get("company"),
        email=buyer_raw.get("email"),
        contact=buyer_raw.get("contact"),
        mst=buyer_raw.get("mst"),
    )

    lines: list[RFQLine] = []
    for item in payload.get("lines") or []:
        if not isinstance(item, dict):
            continue
        description = (item.get("description_normalized") or item.get("raw_text") or "").strip()
        if not description:
            continue  # a line with no description cannot be matched; the FR-034 gate will see it
        lines.append(
            RFQLine(
                raw_text=(item.get("raw_text") or description).strip(),
                description_normalized=description,
                quantity=_quantity(item.get("quantity")),
                unit=str(item.get("unit") or ""),
                unit_original=str(item.get("unit") or ""),
                confidence=float(item.get("confidence") or 0.5),
            )
        )
    return buyer, lines


def merge_pages(pages: list[tuple[Buyer, list[RFQLine]]]) -> RFQExtraction:
    """Merge the pages, de-duplicating on (description, quantity). See the module docstring."""
    buyer = Buyer()
    for page_buyer, _ in pages:
        # First non-empty value wins: the buyer block is on the first page of a công văn, and a
        # later page's letterhead is not more authoritative than the one that named the sender.
        buyer = Buyer(
            company=buyer.company or page_buyer.company,
            email=buyer.email or page_buyer.email,
            contact=buyer.contact or page_buyer.contact,
            mst=buyer.mst or page_buyer.mst,
        )

    seen: set[tuple[str, str]] = set()
    lines: list[RFQLine] = []
    for _, page_lines in pages:
        for line in page_lines:
            key = (line.description_normalized.casefold(), str(line.quantity))
            if key in seen:
                continue  # a repeated header or a straddling line, not a second order
            seen.add(key)
            lines.append(line)

    # FR-035: a scanned công văn is Vietnamese by construction; per-line language is recorded so the
    # drafter can still handle an English product name inside a Vietnamese document.
    return RFQExtraction(
        buyer=buyer,
        lines=lines,
        language_per_line=[Language.VI for _ in lines],
    )


async def extract_scanned_rfq(
    data: bytes,
    settings: Settings,
    *,
    usage: UsageSink | None = None,
    client: Any | None = None,
) -> RFQExtraction:
    """FR-031 + FR-032: rasterize a scan and read every page with the vision model."""
    pages = rasterize_pdf(data)
    vision = client or OpenAI(
        api_key=settings.dashscope_api_key, base_url=settings.dashscope_base_url
    )

    results: list[tuple[Buyer, list[RFQLine]]] = []
    for index, png in enumerate(pages, start=1):
        response = vision.chat.completions.create(
            model=MODEL_PARSER_VISION,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": to_data_url(png)}},
                        {"type": "text", "text": VISION_SYS},
                    ],
                }
            ],
        )
        if usage is not None:
            counts = getattr(response, "usage", None)
            usage.usage(
                int(getattr(counts, "prompt_tokens", 0) or 0),
                int(getattr(counts, "completion_tokens", 0) or 0),
            )
        results.append(parse_page(response.choices[0].message.content or "", page=index))

    return merge_pages(results)
