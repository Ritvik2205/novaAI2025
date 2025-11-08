from __future__ import annotations

import logging
import re
from typing import Any

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"\+?\d[\d\-\s]{7,}\d")


def mask_pii(text: str) -> str:
    text = EMAIL_RE.sub("[email-redacted]", text)
    text = PHONE_RE.sub("[phone-redacted]", text)
    return text


def configure_logging(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("nova")
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger


def audit(logger: logging.Logger, message: str, **payload: Any) -> None:
    safe = {k: mask_pii(str(v)) for k, v in payload.items()}
    logger.info("AUDIT %s %s", message, safe)
