"""FR-048 seed: the reseller's standard operating procedures, as retrievable memory.

These are the sentences that used to be hardcoded in `orchestrator.DEFAULT_TERMS` - payment terms,
delivery norms, warranty language, validity bounds, how a substitution is worded. Hardcoding them
made every quote say the same thing regardless of what was being quoted, which is wrong in an
obvious way: a server with a 30-day lead time cannot promise delivery in 7 working days, and a
software licence has no warranty to speak of.

So they live in the `sop` KnowledgeStore tenant instead, and the drafter retrieves the two most
relevant per topic (FR-048). This is *procedural* memory - what the business always does - as
distinct from the *episodic* memory in memory/recall.py, which is what happened last time with this
particular customer. Both inform the draft; neither is allowed near the arithmetic.

Vietnamese is the governing language (FR-061), so the vi text is what a reader is held to and the
en text is its translation. Both are written in the trang trọng business register FR-065 asks for.
"""

from __future__ import annotations

from ..models import BilingualText, SOPSnippet, SopTopic

SOPS: list[SOPSnippet] = [
    # --- payment ---
    SOPSnippet(
        topic=SopTopic.PAYMENT,
        text=BilingualText(
            vi="Thanh toán 100% trong vòng 30 ngày kể từ ngày nhận hàng, bằng chuyển khoản.",
            en="100% payment within 30 days of delivery, by bank transfer.",
        ),
    ),
    SOPSnippet(
        topic=SopTopic.PAYMENT,
        text=BilingualText(
            vi=(
                "Đối với đơn hàng trên 500.000.000 VND: tạm ứng 30% khi ký hợp đồng, "
                "70% còn lại trong vòng 30 ngày kể từ ngày nghiệm thu."
            ),
            en=(
                "For orders above 500,000,000 VND: 30% advance on signing, the remaining 70% "
                "within 30 days of acceptance."
            ),
        ),
    ),
    SOPSnippet(
        topic=SopTopic.PAYMENT,
        text=BilingualText(
            vi="Bản quyền phần mềm và dịch vụ triển khai: thanh toán 100% trước khi kích hoạt.",
            en=("Software licences and implementation services: paid in full before activation."),
        ),
    ),
    # --- delivery ---
    SOPSnippet(
        topic=SopTopic.DELIVERY,
        text=BilingualText(
            vi="Giao hàng trong vòng 7 ngày làm việc đối với các mặt hàng có sẵn trong kho.",
            en="Delivery within 7 working days for items held in stock.",
        ),
    ),
    SOPSnippet(
        topic=SopTopic.DELIVERY,
        text=BilingualText(
            vi=(
                "Mặt hàng đặt theo yêu cầu (máy chủ, thiết bị mạng cấu hình riêng): "
                "thời gian giao hàng theo lịch của hãng, thông báo trong báo giá."
            ),
            en=(
                "Made-to-order items (servers, custom-configured network hardware) ship on the "
                "manufacturer's lead time, which is stated on the quotation."
            ),
        ),
    ),
    SOPSnippet(
        topic=SopTopic.DELIVERY,
        text=BilingualText(
            vi="Giao hàng tận nơi trong nội thành Thành phố Hồ Chí Minh và Hà Nội, miễn phí.",
            en="Free delivery within Ho Chi Minh City and Hanoi.",
        ),
    ),
    # --- warranty ---
    SOPSnippet(
        topic=SopTopic.WARRANTY,
        text=BilingualText(
            vi="Bảo hành chính hãng 12 tháng, đổi mới trong 30 ngày đầu nếu lỗi do nhà sản xuất.",
            en=(
                "12 months manufacturer warranty; replacement within the first 30 days for "
                "manufacturing defects."
            ),
        ),
    ),
    SOPSnippet(
        topic=SopTopic.WARRANTY,
        text=BilingualText(
            vi=(
                "Máy chủ và thiết bị mạng doanh nghiệp: bảo hành 36 tháng theo chính sách "
                "của hãng, hỗ trợ tại chỗ trong giờ hành chính."
            ),
            en=(
                "Enterprise servers and network hardware: 36 months under the manufacturer's "
                "policy, with on-site support during business hours."
            ),
        ),
    ),
    SOPSnippet(
        topic=SopTopic.WARRANTY,
        text=BilingualText(
            vi=(
                "Bản quyền phần mềm: hỗ trợ kỹ thuật theo điều khoản của nhà cung cấp, "
                "không áp dụng bảo hành phần cứng."
            ),
            en=(
                "Software licences: technical support under the vendor's terms; hardware warranty "
                "does not apply."
            ),
        ),
    ),
    # --- validity ---
    SOPSnippet(
        topic=SopTopic.VALIDITY,
        text=BilingualText(
            vi=(
                "Báo giá có hiệu lực 14 ngày kể từ ngày phát hành. Giá có thể thay đổi theo tỷ giá "
                "USD/VND đối với hàng nhập khẩu."
            ),
            en=(
                "This quotation is valid for 14 days from the date of issue. Prices on imported "
                "goods may change with the USD/VND rate."
            ),
        ),
    ),
    # --- substitution ---
    SOPSnippet(
        topic=SopTopic.SUBSTITUTION,
        text=BilingualText(
            vi=(
                "Trường hợp mã hàng yêu cầu không còn kinh doanh, chúng tôi đề xuất mã tương đương "
                "và ghi rõ trên từng dòng để Quý khách xác nhận trước khi đặt hàng."
            ),
            en=(
                "Where a requested part is no longer available we propose an equivalent and mark "
                "the line, for your confirmation before ordering."
            ),
        ),
    ),
]
