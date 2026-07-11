"""AGT-07 Reviewer: the critic's narrative (FR-073).

The deterministic critic in `quote/critic.py` recomputes every number and raises the flags. It is
the guardrail, and it is code. This module writes the *sentence a human reads at the gate* - what
was checked, and why it passed or did not.

The order matters and is load-bearing: **the verdict exists before the narrative does.** The model
is handed a finished CriticReport and asked to explain it. It cannot set `passed`, it cannot add or
remove a flag, and it never sees a number it could disagree with, because the numbers it is given
are the ones the deterministic engine already computed. If this call fails, times out, or returns
nonsense, the quote is unaffected: the narrative is simply absent, and the gate still shows the
flags and the diffs. An explanation that can change a verdict is not an explanation - it is a
second, unaccountable critic.

FR-073 caps it at 80 words per language. The cap is enforced in code after generation, not merely
requested in the prompt, because "concise" is not something a prompt can promise.
"""

from __future__ import annotations

from agentscope.message import Msg
from pydantic import BaseModel, Field

from ..config.models import MODEL_CRITIC
from ..config.settings import Settings
from ..models import BilingualText, CriticReport, Quote
from .model import UsageSink, build_agent

WORD_CAP = 80  # FR-073

REVIEWER_SYS = """Bạn là người soát báo giá. Một hệ thống tính toán đã kiểm tra xong và ĐÃ CÓ KẾT
LUẬN. Việc của bạn là VIẾT LẠI kết luận đó thành hai đoạn ngắn cho người duyệt đọc - một tiếng Việt,
một tiếng Anh.

Quy tắc:
- KHÔNG đảo ngược kết luận. Nếu hệ thống nói đạt, bạn giải thích vì sao đạt; nếu không đạt, bạn nói
  rõ điều gì đã chặn nó.
- KHÔNG tự tính toán. KHÔNG bịa ra con số nào không có trong dữ liệu được đưa.
- Tối đa 80 từ mỗi ngôn ngữ. Văn phong trang trọng, không quảng cáo, không cảm thán.
- Nói cụ thể: đã đối chiếu điều gì, còn điều gì người duyệt cần tự quyết.
- Giữ nguyên dấu tiếng Việt."""


class ReviewNarrative(BaseModel):
    """FR-073 + FR-133: the review note, as structured output rather than parsed prose."""

    vi: str = Field(description="Nhận xét bằng tiếng Việt, tối đa 80 từ.")
    en: str = Field(description="The same review in English, at most 80 words.")


def _cap(text: str, words: int = WORD_CAP) -> str:
    """Enforce FR-073's word cap in code. A prompt can ask for brevity; it cannot guarantee it."""
    parts = text.split()
    if len(parts) <= words:
        return text.strip()
    return " ".join(parts[:words]).rstrip(",;:") + "..."


def _facts(quote: Quote, report: CriticReport) -> str:
    """Everything the model is allowed to know - all of it already computed, none of it its own."""
    lines = "\n".join(
        f"- {line.sku or 'KHÔNG KHỚP / NO MATCH'}: {line.qty} x {line.unit_price_vnd:,} VND"
        f" = {line.line_total_vnd:,} VND ({line.source.value})"
        for line in quote.lines
    )
    verdict = "ĐẠT / PASSED" if report.passed else "KHÔNG ĐẠT / FAILED"
    return (
        f"Kết luận của hệ thống / System verdict: {verdict}\n"
        f"Cờ chặn / Blocking flags: {report.blocking or 'không có / none'}\n"
        f"Cờ cảnh báo / Non-blocking flags: {report.non_blocking or 'không có / none'}\n"
        f"Sai lệch khi tính lại / Recompute diffs: "
        f"{[d.field for d in report.recompute_diffs] or 'không có / none'}\n"
        f"\nCác dòng / Lines:\n{lines}\n"
        f"\nTổng trước thuế / Subtotal: {quote.subtotal_vnd:,} VND"
        f"\nThuế GTGT / VAT: {sum(e.amount for e in quote.vat_breakdown):,} VND"
        f"\nTổng cộng / Total: {quote.total_vnd:,} VND"
    )


async def review_note(
    quote: Quote,
    report: CriticReport,
    settings: Settings,
    *,
    usage: UsageSink | None = None,
) -> BilingualText:
    """FR-073: explain the verdict that has already been reached. Never reach a different one."""
    agent = build_agent(
        name="reviewer",
        sys_prompt=REVIEWER_SYS,
        model_name=MODEL_CRITIC,
        settings=settings,
        usage=usage,
    )
    reply = await agent(
        Msg("user", _facts(quote, report), "user"), structured_model=ReviewNarrative
    )
    narrative = ReviewNarrative.model_validate(reply.metadata)
    return BilingualText(vi=_cap(narrative.vi), en=_cap(narrative.en))
