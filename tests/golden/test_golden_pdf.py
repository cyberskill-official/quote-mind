"""FR-124: the golden PDF snapshot.

One fixed quote is rendered and compared against a checked-in PNG. This is the only test that can
catch a change nobody wrote a test for: a CSS tweak that shifts the totals block, a font fallback
that mangles Vietnamese diacritics, a layout change that pushes the bank details off the page. Those
are all invisible to an assertion about numbers and immediately obvious in a picture.

The tolerance is 2% of pixels (per FR-124), which absorbs antialiasing differences between machines
without absorbing a real layout change. Regenerate deliberately, never reflexively:

    python tests/golden/test_golden_pdf.py --update

If a diff appears you did not intend, that is the test doing its job.

A caveat, stated rather than hidden: the golden is only portable across machines that resolve the
same fonts. Recorded on macOS it differs from Linux by ~25% of pixels - not a layout change, just a
different font fallback - which would make this test fail wherever it was not recorded. So the
golden is pinned to the CI platform (Linux) and the check is skipped elsewhere. Bundling the Be
Vietnam Pro TTFs is what makes it truly portable, and that is still outstanding (FR-090).
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from quotemind.config.seller import SELLER_BLOCK
from quotemind.models import BilingualText, LineSource, QuoteTerms, Tier
from quotemind.pricing import vat_policy_note
from quotemind.quote import AssemblyLine, assemble_quote, format_quote_number
from quotemind.seed.data import BY_SKU

GOLDEN = Path(__file__).parent / "quote_golden.png"
TOLERANCE = 0.02  # FR-124
GOLDEN_PLATFORM = "linux"  # the golden is recorded on the CI platform; fonts differ elsewhere
_ON = date(2026, 7, 11)

_TERMS = QuoteTerms(
    payment=BilingualText(
        vi="Thanh toán 100% trong vòng 30 ngày kể từ ngày nhận hàng.",
        en="100% payment within 30 days of delivery.",
    ),
    delivery=BilingualText(
        vi="Giao hàng trong vòng 7 ngày làm việc.", en="Delivery within 7 working days."
    ),
    warranty=BilingualText(
        vi="Bảo hành chính hãng 12 tháng.", en="12 months manufacturer warranty."
    ),
)
_NOTES = BilingualText(
    vi="Báo giá do QuoteMind lập, đã được kiểm tra số học tự động.",
    en="Quotation prepared by QuoteMind and automatically arithmetic-checked.",
)


def build_golden_quote() -> object:
    """A fixed quote: two goods lines plus the 10% telecom line, so VAT banding is on the page."""
    return assemble_quote(
        quote_id="01JGOLDEN000000000000000000",
        quote_number=format_quote_number(2026, 1),
        seller_block=SELLER_BLOCK,
        customer_block={
            "name": "Công ty TNHH Thành Công",
            "mst": "0301234567",
            "address": "12 Nguyễn Huệ, Quận 1, TP.HCM",
            "contact": "Chị Lan",
        },
        date=_ON.isoformat(),
        validity_days=14,
        lines=[
            AssemblyLine(
                product=BY_SKU["DELL-LAT-5450"],
                qty=Decimal(10),
                tier=Tier.DEALER,
                source=LineSource.MATCHED,
            ),
            AssemblyLine(
                product=BY_SKU["DELL-P2723DE"],
                qty=Decimal(10),
                tier=Tier.DEALER,
                source=LineSource.MATCHED,
            ),
            AssemblyLine(
                product=BY_SKU["VIET-SIM-DATA"],
                qty=Decimal(10),
                tier=Tier.DEALER,
                source=LineSource.MATCHED,
            ),
        ],
        terms=_TERMS,
        notes=_NOTES,
        on_date=_ON,
        project_discount_pct=3.0,
    )


def render_png() -> bytes:
    from quotemind.quote.render import render_pdf  # noqa: PLC0415

    pdf = render_pdf(
        build_golden_quote(),  # type: ignore[arg-type]
        vat_policy_note=vat_policy_note(_ON),
    )

    import pypdfium2  # noqa: PLC0415

    document = pypdfium2.PdfDocument(pdf)
    try:
        image = document[0].render(scale=1.5).to_pil()
    finally:
        document.close()

    import io  # noqa: PLC0415

    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def _pixel_diff(left: bytes, right: bytes) -> float:
    import io  # noqa: PLC0415

    from PIL import Image, ImageChops  # noqa: PLC0415

    first = Image.open(io.BytesIO(left)).convert("RGB")
    second = Image.open(io.BytesIO(right)).convert("RGB")
    if first.size != second.size:
        return 1.0  # a size change is a layout change, full stop
    diff = ImageChops.difference(first, second)
    changed = sum(1 for pixel in diff.getdata() if pixel != (0, 0, 0))
    return changed / (first.size[0] * first.size[1])


@pytest.mark.skipif(not GOLDEN.exists(), reason="golden PNG not recorded")
@pytest.mark.skipif(
    not sys.platform.startswith(GOLDEN_PLATFORM),
    reason="the golden is font-dependent and recorded on Linux (see the module docstring)",
)
def test_the_rendered_quote_still_looks_like_the_golden() -> None:
    ratio = _pixel_diff(render_png(), GOLDEN.read_bytes())
    assert ratio <= TOLERANCE, (
        f"{ratio:.1%} of pixels changed (tolerance {TOLERANCE:.0%}). "
        "If this was intentional, rerun with --update and eyeball the new PNG before committing it."
    )


if __name__ == "__main__":  # pragma: no cover - operational
    if "--update" in sys.argv:
        GOLDEN.write_bytes(render_png())
        print(f"golden updated: {GOLDEN} ({GOLDEN.stat().st_size} bytes)")
    else:
        print("pass --update to regenerate the golden PNG")
