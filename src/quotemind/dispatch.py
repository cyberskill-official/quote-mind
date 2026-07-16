"""Bilingual quote dispatch (TASK-092, TASK-093).

Two transports behind one interface. `smtp` sends through DirectMail over SSL 465. `stub` - the demo
default - builds the identical MIME message and writes it to oss://quotemind-artifacts/outbox/, so a
demo is deterministic and inspectable without waiting for DirectMail sender approval.

The message is the same either way: Vietnamese first (it is the governing language), English below,
the presigned link, and the PDF attached when it is small enough.
"""

from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid

from .cloud import ArtifactStore
from .config.settings import Settings
from .models import Quote

MAX_ATTACHMENT_BYTES = 3 * 1024 * 1024  # TASK-092: attach the PDF only when <= 3 MB
SMTP_PORT_SSL = 465


@dataclass(frozen=True)
class DispatchResult:
    """What actually happened, for the audit trail (TASK-094)."""

    transport: str  # "smtp" | "stub"
    message_id: str
    recipient: str
    attached: bool
    outbox_key: str | None = None


def subject_for(quote: Quote, seller_name: str) -> str:
    """TASK-092 frozen subject line."""
    return f"Báo giá / Quotation {quote.quote_number} — {seller_name}"


def _body(quote: Quote, seller_name: str, link: str, contact: str | None) -> tuple[str, str]:
    greeting_vi = f"Kính gửi {contact}," if contact else "Kính gửi Quý khách,"
    greeting_en = f"Dear {contact}," if contact else "Dear Sir or Madam,"
    plain = (
        f"{greeting_vi}\n\n"
        f"{seller_name} xin gửi báo giá {quote.quote_number} theo yêu cầu của Quý khách.\n"
        f"Tổng cộng: {quote.total_in_words_vi}\n"
        f"Báo giá có hiệu lực trong {quote.validity_days} ngày.\n"
        f"Tải bản PDF (liên kết có hiệu lực 10 phút): {link}\n\n"
        f"Trân trọng,\n{seller_name}\n\n"
        f"---\n\n"
        f"{greeting_en}\n\n"
        f"Please find quotation {quote.quote_number} attached.\n"
        f"The quotation is valid for {quote.validity_days} days.\n"
        f"Download the PDF (link valid for 10 minutes): {link}\n\n"
        f"Kind regards,\n{seller_name}\n"
    )
    html = (
        f"<p>{greeting_vi}</p>"
        f"<p>{seller_name} xin gửi báo giá <b>{quote.quote_number}</b> theo yêu cầu của Quý khách."
        f"<br>Tổng cộng: <b>{quote.total_in_words_vi}</b>"
        f"<br>Báo giá có hiệu lực trong {quote.validity_days} ngày.</p>"
        f'<p><a href="{link}">Tải bản PDF / Download the PDF</a> '
        f"(liên kết có hiệu lực 10 phút / link valid for 10 minutes)</p>"
        f"<hr>"
        f"<p>{greeting_en}</p>"
        f"<p>Please find quotation <b>{quote.quote_number}</b> attached. "
        f"It is valid for {quote.validity_days} days.</p>"
        f"<p>Kind regards,<br>{seller_name}</p>"
    )
    return plain, html


def build_message(
    quote: Quote,
    *,
    settings: Settings,
    seller_name: str,
    recipient: str,
    link: str,
    contact: str | None = None,
    pdf: bytes | None = None,
) -> tuple[EmailMessage, bool]:
    """The bilingual MIME message. Returns (message, attached)."""
    message = EmailMessage()
    message["Subject"] = subject_for(quote, seller_name)
    message["From"] = settings.mail_from
    message["To"] = recipient
    message["Message-ID"] = make_msgid(domain="cyberskill.world")

    plain, html = _body(quote, seller_name, link, contact)
    message.set_content(plain)
    message.add_alternative(html, subtype="html")

    attached = pdf is not None and len(pdf) <= MAX_ATTACHMENT_BYTES
    if attached and pdf is not None:
        message.add_attachment(
            pdf,
            maintype="application",
            subtype="pdf",
            filename=f"{quote.quote_number}.pdf",
        )
    return message, attached


def send_quote(
    quote: Quote,
    *,
    settings: Settings,
    artifacts: ArtifactStore,
    seller_name: str,
    recipient: str,
    link: str,
    contact: str | None = None,
    pdf: bytes | None = None,
) -> DispatchResult:
    """TASK-092 / TASK-093: send over DirectMail, or write the same message to the OSS outbox."""
    message, attached = build_message(
        quote,
        settings=settings,
        seller_name=seller_name,
        recipient=recipient,
        link=link,
        contact=contact,
        pdf=pdf,
    )
    message_id = str(message["Message-ID"])

    if settings.mail_transport == "stub":  # TASK-093
        key = artifacts.put_eml(quote.quote_number, message.as_bytes())
        return DispatchResult(
            transport="stub",
            message_id=message_id,
            recipient=recipient,
            attached=attached,
            outbox_key=key,
        )

    context = ssl.create_default_context()
    port = settings.directmail_smtp_port or SMTP_PORT_SSL
    with smtplib.SMTP_SSL(settings.directmail_smtp_host, port, context=context) as server:
        if settings.directmail_user and settings.directmail_password:
            server.login(settings.directmail_user, settings.directmail_password)
        server.send_message(message)
    return DispatchResult(
        transport="smtp", message_id=message_id, recipient=recipient, attached=attached
    )
