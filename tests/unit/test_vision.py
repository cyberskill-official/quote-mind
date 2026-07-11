"""FR-031/032: rasterization, and the vision parser's contract with an unreliable model."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from quotemind.agents.vision import (
    VisionParseError,
    extract_scanned_rfq,
    merge_pages,
    parse_page,
    strip_fence,
)
from quotemind.models import Buyer, RFQLine
from quotemind.parsing.pdf import is_scanned
from quotemind.parsing.raster import (
    MAX_LONG_EDGE,
    MAX_PAGES,
    TooManyPagesError,
    rasterize_pdf,
    to_data_url,
)

DATASET = Path(__file__).resolve().parents[2] / "eval" / "dataset"
SCAN = DATASET / "vi_scan_001.pdf"
DIGITAL = DATASET / "en_pdf_001.pdf"

pytestmark = pytest.mark.skipif(not SCAN.exists(), reason="dataset not generated")


# --- the fixtures must actually be scans ---
def test_the_scan_fixtures_have_no_text_layer() -> None:
    # If a "scan" still carried extractable text it would take the digital-PDF path, the vision
    # model would never be called, and the OCR score would be the text parser's score wearing a hat.
    assert is_scanned(SCAN.read_bytes())
    assert not is_scanned(DIGITAL.read_bytes())


# --- FR-031: rasterization ---
def test_rasterize_produces_one_png_per_page_within_the_size_cap() -> None:
    import io  # noqa: PLC0415

    from PIL import Image  # noqa: PLC0415

    pages = rasterize_pdf(SCAN.read_bytes())
    assert len(pages) == 1
    image = Image.open(io.BytesIO(pages[0]))
    assert max(image.size) <= MAX_LONG_EDGE  # image tokens scale with pixels; the cap is the budget
    assert image.size[0] > 800  # but still legible - a downscale to thumbnail size would lose ...


def test_a_document_over_the_page_budget_is_refused_not_billed() -> None:
    # A 300-page catalogue dropped in the inbox by accident should cost cents and get refused.
    with pytest.raises(TooManyPagesError):
        rasterize_pdf(SCAN.read_bytes(), max_pages=0)
    assert MAX_PAGES == 10


def test_data_url_is_what_the_openai_content_array_wants() -> None:
    url = to_data_url(b"\x89PNG\r\n")
    assert url.startswith("data:image/png;base64,")


# --- FR-032: the parser's contract with the model ---
def test_a_json_fence_is_stripped() -> None:
    assert strip_fence('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert strip_fence('{"a": 1}') == '{"a": 1}'


def test_malformed_json_raises_rather_than_being_repaired() -> None:
    # A model that emitted broken JSON was confused. A regex that patches it into something
    # parseable launders that confusion into a confident quote.
    with pytest.raises(VisionParseError):
        parse_page('{"lines": [ {"description_normalized": "laptop"', page=1)


def test_prose_instead_of_json_is_a_failure_not_a_guess() -> None:
    with pytest.raises(VisionParseError):
        parse_page("The document appears to request 20 laptops.", page=1)


def test_an_unreadable_quantity_becomes_null_never_a_guess() -> None:
    buyer, lines = parse_page(
        '{"buyer": {"company": "Thành Công"},'
        ' "lines": [{"raw_text": "Laptop Dell", "description_normalized": "Laptop Dell",'
        '            "quantity": "khong doc duoc", "unit": "cái", "confidence": 0.4}]}',
        page=1,
    )
    assert buyer.company == "Thành Công"  # diacritics intact
    assert lines[0].quantity is None  # the FR-034 gate will stop this before it can be priced


def test_diacritics_survive_the_parse() -> None:
    _, lines = parse_page(
        '{"lines": [{"raw_text": "Máy chủ Dell PowerEdge R650",'
        ' "description_normalized": "Máy chủ Dell PowerEdge R650",'
        ' "quantity": 2, "unit": "cái", "confidence": 0.9}]}',
        page=1,
    )
    assert lines[0].description_normalized == "Máy chủ Dell PowerEdge R650"
    assert lines[0].quantity == Decimal(2)


def _line(description: str, qty: int) -> RFQLine:
    return RFQLine(
        raw_text=description,
        description_normalized=description,
        quantity=Decimal(qty),
        unit="cái",
        unit_original="cái",
        confidence=0.9,
    )


def test_a_line_repeated_across_a_page_break_is_not_charged_twice() -> None:
    merged = merge_pages(
        [
            (Buyer(company="Thành Công"), [_line("Laptop Dell Latitude 5450", 20)]),
            (Buyer(), [_line("Laptop Dell Latitude 5450", 20)]),  # the straddle / repeated header
        ]
    )
    assert len(merged.lines) == 1  # a duplicated line is a doubled charge


def test_two_genuine_lines_for_the_same_product_both_survive() -> None:
    # De-duplication is on (description, quantity), not description alone. An order for 20 laptops
    # for one office and 5 for another is two lines, and collapsing them would under-bill.
    merged = merge_pages(
        [
            (Buyer(), [_line("Laptop Dell Latitude 5450", 20)]),
            (Buyer(), [_line("Laptop Dell Latitude 5450", 5)]),
        ]
    )
    assert len(merged.lines) == 2


def test_the_buyer_comes_from_the_first_page_that_named_one() -> None:
    merged = merge_pages(
        [
            (Buyer(company="Thành Công", email="mua.hang@thanhcong.vn"), []),
            (Buyer(company="Trang 2 letterhead"), []),  # not more authoritative than the sender
        ]
    )
    assert merged.buyer.company == "Thành Công"
    assert merged.buyer.email == "mua.hang@thanhcong.vn"


# --- the whole path, with the model stubbed ---
class _FakeVision:
    def __init__(self, replies: list[str]) -> None:
        self.replies = replies
        self.calls: list[dict[str, Any]] = []
        self.chat = self

    @property
    def completions(self) -> _FakeVision:
        return self

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        raw = self.replies[len(self.calls) - 1]

        class _Message:
            content = raw

        class _Choice:
            message = _Message()

        class _Usage:
            prompt_tokens = 1500
            completion_tokens = 120

        class _Response:
            choices = [_Choice()]
            usage = _Usage()

        return _Response()


class _Settings:
    dashscope_api_key = "sk-test"
    dashscope_base_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"


class _Sink:
    def __init__(self) -> None:
        self.tokens_in = 0
        self.tokens_out = 0

    def usage(self, tokens_in: int = 0, tokens_out: int = 0) -> None:
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out


def test_the_scan_is_sent_as_an_image_and_the_tokens_are_reported() -> None:
    client = _FakeVision(
        ['```json\n{"buyer": {"company": "Công ty TNHH Thành Công"},'
         ' "lines": [{"raw_text": "Laptop Dell Latitude 5450",'
         '            "description_normalized": "Laptop Dell Latitude 5450",'
         '            "quantity": 20, "unit": "cái", "confidence": 0.92}]}\n```']
    )
    sink = _Sink()
    extraction = asyncio.run(
        extract_scanned_rfq(
            SCAN.read_bytes(),
            _Settings(),  # type: ignore[arg-type]
            usage=sink,
            client=client,
        )
    )

    # The page really went as an image part - a text-only message would be a 400 from the model.
    parts = client.calls[0]["messages"][0]["content"]
    assert any(part["type"] == "image_url" for part in parts)
    assert parts[0]["image_url"]["url"].startswith("data:image/png;base64,")

    assert extraction.buyer.company == "Công ty TNHH Thành Công"
    assert len(extraction.lines) == 1
    assert extraction.lines[0].quantity == Decimal(20)
    assert (sink.tokens_in, sink.tokens_out) == (1500, 120)  # real provider counts, for FR-112
