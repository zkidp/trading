from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


def send_email(*, subject: str, body_text: str) -> None:
    """Send email via SMTP.

    Env vars required:
    - SMTP_HOST
    - SMTP_PORT (default 587)
    - SMTP_USER
    - SMTP_PASS
    - MAIL_FROM (default SMTP_USER)
    - MAIL_TO

    This avoids relying on system sendmail/msmtp.
    """

    host = os.getenv("SMTP_HOST")
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")
    mail_to = os.getenv("MAIL_TO")
    if not host or not user or not password or not mail_to:
        raise RuntimeError("SMTP_HOST/SMTP_USER/SMTP_PASS/MAIL_TO 未配置")

    port = int(os.getenv("SMTP_PORT", "587"))
    mail_from = os.getenv("MAIL_FROM", user)

    msg = EmailMessage()
    msg["From"] = mail_from
    msg["To"] = mail_to
    msg["Subject"] = subject
    msg.set_content(body_text)

    with smtplib.SMTP(host, port, timeout=30) as s:
        s.starttls()
        s.login(user, password)
        s.send_message(msg)
