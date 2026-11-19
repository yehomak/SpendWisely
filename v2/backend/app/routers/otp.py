"""OTP confirmation endpoints.

POST /otp/request  {purpose}            → {challenge_id, email_hint, expires_in, resend_in}
POST /otp/resend   {challenge_id}       → same shape, new code (old one invalidated)
POST /otp/verify   {challenge_id, code} → {confirmation_token}
                    400 "Incorrect code" (+attempts_left) | 410 expired | 429 locked

The confirmation token is then sent as `X-Confirmation-Token` to the protected endpoint.
The code itself is only ever delivered by e-mail — never in a response.
"""

from __future__ import annotations

import logging
import smtplib

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.services import mailer
from app.services.otp import IssuedCode, OtpError, OtpStore

log = logging.getLogger("spendwisely.otp")

router = APIRouter(prefix="/otp", tags=["otp"])

# purpose → human label used in the e-mail
PURPOSES: dict[str, str] = {
    "delete_all_transactions": "deleting all transactions",
}

store = OtpStore(
    ttl_seconds=settings.otp_ttl_seconds,
    max_attempts=settings.otp_max_attempts,
    resend_cooldown_seconds=settings.otp_resend_cooldown_seconds,
)


class OtpRequestIn(BaseModel):
    purpose: str


class OtpResendIn(BaseModel):
    challenge_id: str


class OtpVerifyIn(BaseModel):
    challenge_id: str
    code: str = Field(min_length=1, max_length=12)


def _mask(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"


def _deliver(issued: IssuedCode) -> dict:
    ch = issued.challenge
    try:
        mailer.send_otp_email(
            settings.otp_email_to,
            issued.code,
            PURPOSES[ch.purpose],
            max(1, settings.otp_ttl_seconds // 60),
        )
    except (OSError, smtplib.SMTPException) as e:
        log.error("OTP e-mail delivery failed: %s", e)
        raise HTTPException(503, "Could not send the confirmation e-mail")
    log.info("OTP issued challenge=%s purpose=%s", ch.id[:8], ch.purpose)
    now = store.clock()
    return {
        "challenge_id": ch.id,
        "email_hint": _mask(settings.otp_email_to),
        "expires_in": int(ch.expires_at - now),
        "resend_in": max(0, int(ch.resend_available_at - now + 0.999)),
    }


def _error(e: OtpError) -> JSONResponse:
    return JSONResponse(status_code=e.status, content={"detail": e.message, **e.extra})


@router.post("/request")
def request_code(body: OtpRequestIn):
    if body.purpose not in PURPOSES:
        raise HTTPException(400, f"Unknown purpose: {body.purpose}")
    return _deliver(store.request(body.purpose))


@router.post("/resend")
def resend_code(body: OtpResendIn):
    try:
        issued = store.resend(body.challenge_id)
    except OtpError as e:
        return _error(e)
    return _deliver(issued)


@router.post("/verify")
def verify_code(body: OtpVerifyIn):
    try:
        token = store.verify(body.challenge_id, body.code)
    except OtpError as e:
        # Never log the submitted code — only that an attempt failed.
        log.warning(
            "OTP verify failed challenge=%s reason=%s %s",
            body.challenge_id[:8],
            type(e).__name__,
            e.extra,
        )
        return _error(e)
    log.info("OTP verified challenge=%s", body.challenge_id[:8])
    return {"confirmation_token": token}
