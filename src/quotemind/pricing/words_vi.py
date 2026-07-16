"""Vietnamese amount-in-words (bằng chữ) converter (TASK-055). Deterministic and pure.

Conventions follow the one worked example in the spec (1234000 -> "Một triệu hai trăm ba
mươi bốn nghìn đồng"): 4 is read "bốn", 1 after a tens digit is "mốt", 5 after a tens digit
is "lăm", and a missing tens digit inside a group is spoken as "linh". Zero-hundreds inside a
non-leading group are spoken as "không trăm" for an unambiguous banking-style reading.
"""

from __future__ import annotations

from decimal import Decimal

_UNITS = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]
_SCALES = ["", "nghìn", "triệu", "tỷ", "nghìn tỷ", "triệu tỷ", "tỷ tỷ"]


def _read_group(value: int, force_hundred: bool) -> str:
    hundreds, remainder = divmod(value, 100)
    tens, ones = divmod(remainder, 10)
    parts: list[str] = []
    if hundreds > 0:
        parts.append(f"{_UNITS[hundreds]} trăm")
    elif force_hundred and remainder > 0:
        parts.append("không trăm")
    if tens > 1:
        parts.append(f"{_UNITS[tens]} mươi")
        if ones == 1:
            parts.append("mốt")
        elif ones == 5:
            parts.append("lăm")
        elif ones > 0:
            parts.append(_UNITS[ones])
    elif tens == 1:
        parts.append("mười")
        if ones == 5:
            parts.append("lăm")
        elif ones > 0:
            parts.append(_UNITS[ones])
    elif ones > 0:
        if hundreds > 0 or force_hundred:
            parts.append("linh")
        parts.append(_UNITS[ones])
    return " ".join(parts)


def amount_in_words_vi(amount: Decimal | int) -> str:
    """Convert a whole-đồng amount to Vietnamese words, e.g. 1234000 -> 'Một triệu ...'."""
    total = int(amount)
    if total < 0:
        raise ValueError("amount_in_words_vi does not support negative amounts")
    if total == 0:
        return "Không đồng"
    groups: list[int] = []
    while total > 0:
        total, remainder = divmod(total, 1000)
        groups.append(remainder)
    chunks: list[str] = []
    last = len(groups) - 1
    for index in range(last, -1, -1):
        group = groups[index]
        if group == 0:
            continue
        words = _read_group(group, force_hundred=index != last)
        scale = _SCALES[index]
        chunks.append(f"{words} {scale}" if scale else words)
    sentence = " ".join(chunks) + " đồng"
    return sentence[0].upper() + sentence[1:]
