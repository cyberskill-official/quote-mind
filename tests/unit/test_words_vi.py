"""FR-055: Vietnamese amount-in-words converter."""

from __future__ import annotations

import pytest

from quotemind.pricing import amount_in_words_vi

CASES = [
    (0, "Không đồng"),
    (5, "Năm đồng"),
    (10, "Mười đồng"),
    (11, "Mười một đồng"),
    (14, "Mười bốn đồng"),
    (15, "Mười lăm đồng"),
    (20, "Hai mươi đồng"),
    (21, "Hai mươi mốt đồng"),
    (24, "Hai mươi bốn đồng"),
    (25, "Hai mươi lăm đồng"),
    (100, "Một trăm đồng"),
    (101, "Một trăm linh một đồng"),
    (105, "Một trăm linh năm đồng"),
    (110, "Một trăm mười đồng"),
    (111, "Một trăm mười một đồng"),
    (115, "Một trăm mười lăm đồng"),
    (120, "Một trăm hai mươi đồng"),
    (121, "Một trăm hai mươi mốt đồng"),
    (999, "Chín trăm chín mươi chín đồng"),
    (1000, "Một nghìn đồng"),
    (1005, "Một nghìn không trăm linh năm đồng"),
    (1234, "Một nghìn hai trăm ba mươi bốn đồng"),
    (1_000_000, "Một triệu đồng"),
    (1_000_034, "Một triệu không trăm ba mươi bốn đồng"),
    (1_234_000, "Một triệu hai trăm ba mươi bốn nghìn đồng"),
    (648_000_000, "Sáu trăm bốn mươi tám triệu đồng"),
    (1_000_000_000, "Một tỷ đồng"),
    (
        1_234_567_890,
        "Một tỷ hai trăm ba mươi bốn triệu năm trăm sáu mươi bảy nghìn tám trăm chín mươi đồng",
    ),
]


@pytest.mark.parametrize(("amount", "words"), CASES)
def test_amount_in_words(amount: int, words: str) -> None:
    assert amount_in_words_vi(amount) == words


def test_negative_amount_raises() -> None:
    with pytest.raises(ValueError, match="negative"):
        amount_in_words_vi(-1)
