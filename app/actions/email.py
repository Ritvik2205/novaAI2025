from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.config import get_settings
from app.utils.logging import configure_logging

logger = configure_logging()


def send_quote_email(to_address: str, subject: str, body: str) -> None:
    settings = get_settings()
    if not to_address:
        logger.warning("missing recipient, skipping email")
        return
    message = EmailMessage()
    message["From"] = "quotes@novarag.local"
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body)
    try:
        with smtplib.SMTP("localhost", 25) as smtp:
            smtp.send_message(message)
    except Exception:
        logger.warning("SMTP unavailable, logging email to console")
        logger.info("EMAIL %s | %s", to_address, body)
