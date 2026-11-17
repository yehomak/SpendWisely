"""Minimal SMTP mailer. In docker compose dev this points at Mailpit (smtp 1025, inbox :8025)."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.config import settings


def send_email(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)


def send_otp_email(to: str, code: str, action_label: str, ttl_minutes: int) -> None:
    send_email(
        to,
        subject=f"SpendWisely confirmation code: {code}",
        body=(
            f"Your SpendWisely confirmation code is: {code}\n\n"
            f"It confirms: {action_label}.\n"
            f"The code expires in {ttl_minutes} minutes and can only be used once.\n\n"
            "If you didn't request this, ignore this e-mail — nothing will happen."
        ),
    )
