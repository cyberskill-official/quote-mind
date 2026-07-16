"""TASK-092 bilingual email + TASK-093 stub transport to the OSS outbox."""

from __future__ import annotations

from typing import Any

from quotemind.dispatch import MAX_ATTACHMENT_BYTES, build_message, send_quote, subject_for

from .test_render import _quote


class FakeArtifacts:
    """Stand-in for ArtifactStore."""

    def __init__(self, *, trace_fails: bool = False) -> None:
        self.pdfs: dict[str, bytes] = {}
        self.emls: dict[str, bytes] = {}
        self.traces: dict[str, str] = {}
        self.trace_fails = trace_fails

    def put_pdf(self, quote_number: str, data: bytes) -> str:
        key = f"quotes/{quote_number}.pdf"
        self.pdfs[key] = data
        return key

    def put_trace(self, quote_id: str, payload: str) -> str:
        if self.trace_fails:
            raise RuntimeError("OSS unreachable")
        key = f"traces/{quote_id}.json"
        self.traces[key] = payload
        return key

    def put_eml(self, quote_number: str, data: bytes) -> str:
        key = f"outbox/{quote_number}.eml"
        self.emls[key] = data
        return key

    def presigned_get(self, key: str, expires: int = 600) -> str:
        return f"https://signed.example/{key}?exp={expires}"

    def exists(self, key: str) -> bool:
        return key in self.pdfs


class _Settings:
    mail_from = "quotes@demo.cyberskill.world"
    mail_transport = "stub"
    directmail_smtp_host = "smtpdm-ap-southeast-1.aliyun.com"
    directmail_smtp_port = 465
    directmail_user = None
    directmail_password = None


def test_subject_is_the_frozen_bilingual_line() -> None:
    assert subject_for(_quote(), "CyberSkill JSC") == (
        "Báo giá / Quotation QM-2026-0042 — CyberSkill JSC"
    )


def test_message_is_bilingual_vietnamese_first_and_attaches_a_small_pdf() -> None:
    message, attached = build_message(
        _quote(),
        settings=_Settings(),  # type: ignore[arg-type]
        seller_name="CyberSkill JSC",
        recipient="mua.hang@thanhcong.vn",
        link="https://signed.example/quotes/QM-2026-0042.pdf",
        contact="Chị Lan",
        pdf=b"%PDF-1.7 small",
    )
    assert attached is True
    assert message["To"] == "mua.hang@thanhcong.vn"

    plain = message.get_body(("plain",)).get_content()  # type: ignore[union-attr]
    html = message.get_body(("html",)).get_content()  # type: ignore[union-attr]
    # Vietnamese is the governing language, so it leads; English follows.
    assert plain.index("Kính gửi Chị Lan") < plain.index("Dear Chị Lan")
    assert "signed.example" in plain and "signed.example" in html
    assert any(part.get_filename() == "QM-2026-0042.pdf" for part in message.iter_attachments())


def test_oversized_pdf_is_linked_not_attached() -> None:
    _, attached = build_message(
        _quote(),
        settings=_Settings(),  # type: ignore[arg-type]
        seller_name="CyberSkill JSC",
        recipient="a@b.vn",
        link="https://signed.example/x.pdf",
        pdf=b"x" * (MAX_ATTACHMENT_BYTES + 1),
    )
    assert attached is False  # TASK-092: attach only when <= 3 MB


def test_stub_transport_writes_the_eml_to_the_outbox() -> None:
    artifacts = FakeArtifacts()
    result = send_quote(
        _quote(),
        settings=_Settings(),  # type: ignore[arg-type]
        artifacts=artifacts,  # type: ignore[arg-type]
        seller_name="CyberSkill JSC",
        recipient="mua.hang@thanhcong.vn",
        link="https://signed.example/quotes/QM-2026-0042.pdf",
        contact="Chị Lan",
        pdf=b"%PDF-1.7",
    )
    assert result.transport == "stub"  # TASK-093
    assert result.outbox_key == "outbox/QM-2026-0042.eml"
    assert result.message_id.startswith("<")

    raw: Any = artifacts.emls[result.outbox_key].decode("utf-8", errors="replace")
    assert "QM-2026-0042" in raw  # the subject header (RFC2047-encoded) carries the number
    assert result.attached is True
