"""Brevo OTP delivery without logging secrets or message payloads."""

from __future__ import annotations

import html
import os

import requests

from errors import service_unavailable


def send_otp_email(*, recipient_name: str, recipient_email: str, otp: str) -> None:
    api_key = os.getenv("BREVO_API_KEY")
    sender_email = os.getenv("BREVO_SENDER_EMAIL")
    sender_name = os.getenv("BREVO_SENDER_NAME", "FinTrack AI").strip() or "FinTrack AI"
    if not api_key or not sender_email:
        raise service_unavailable(
            "Email delivery is not configured. Please contact the administrator."
        )

    safe_recipient_name = html.escape(recipient_name)
    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json={
                "sender": {"name": sender_name, "email": sender_email},
                "to": [{"email": recipient_email, "name": recipient_name}],
                "subject": "Your FinTrack AI verification code",
                "htmlContent": (
                    "<div style='font-family:sans-serif;max-width:440px;margin:auto'>"
                    "<h2>FinTrack AI</h2>"
                    f"<p>Hello {safe_recipient_name},</p>"
                    "<p>Your four-digit verification code is:</p>"
                    f"<p style='font-size:32px;letter-spacing:8px'><strong>{otp}</strong></p>"
                    "<p>This code expires in five minutes. If you did not request it, "
                    "you can safely ignore this email.</p></div>"
                ),
            },
            timeout=10,
        )
    except requests.RequestException as exc:
        raise service_unavailable(
            "The verification email could not be sent. Please try again shortly."
        ) from exc

    if response.status_code not in (200, 201):
        raise service_unavailable(
            "The verification email could not be sent. Please try again shortly."
        )
