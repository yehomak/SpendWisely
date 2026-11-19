"""One-time-code (OTP) confirmation for sensitive actions.

Flow:
  1. request(purpose)            → new challenge, random 6-digit code e-mailed to the owner
  2. verify(challenge_id, code)  → on success returns a single-use confirmation token
  3. consume_token(token, purpose) is called by the protected endpoint

Codes are random per request (`secrets`), only their SHA-256 is kept, they expire after
`ttl_seconds` and a challenge is locked after `max_attempts` wrong codes. `resend()` issues a
fresh code (the old one stops working) after a cooldown.

State is in-process memory: fine for the single-process backend (DuckDB is single-writer anyway).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

CODE_LENGTH = 6


class OtpError(Exception):
    """Base class; `status` maps to an HTTP status code in the router."""

    status = 400

    def __init__(self, message: str, **extra):
        super().__init__(message)
        self.message = message
        self.extra = extra


class ChallengeNotFound(OtpError):
    status = 404


class ChallengeExpired(OtpError):
    status = 410


class TooManyAttempts(OtpError):
    status = 429


class IncorrectCode(OtpError):
    status = 400


class ResendTooSoon(OtpError):
    status = 429


class InvalidToken(OtpError):
    status = 403


def generate_code(length: int = CODE_LENGTH) -> str:
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


@dataclass
class Challenge:
    id: str
    purpose: str
    code_hash: str
    expires_at: float
    resend_available_at: float
    attempts: int = 0
    resends: int = 0


@dataclass
class IssuedCode:
    challenge: Challenge
    code: str  # plaintext — only handed to the mailer, never returned to the client


@dataclass
class OtpStore:
    ttl_seconds: int = 600
    max_attempts: int = 5
    resend_cooldown_seconds: int = 30
    max_resends: int = 5
    token_ttl_seconds: int = 300
    clock: Callable[[], float] = time.monotonic
    _challenges: dict[str, Challenge] = field(default_factory=dict)
    _tokens: dict[str, tuple[str, float]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    # ── issuing ────────────────────────────────────────────────────────────
    def request(self, purpose: str) -> IssuedCode:
        now = self.clock()
        code = generate_code()
        ch = Challenge(
            id=secrets.token_urlsafe(16),
            purpose=purpose,
            code_hash=_hash(code),
            expires_at=now + self.ttl_seconds,
            resend_available_at=now + self.resend_cooldown_seconds,
        )
        with self._lock:
            self._purge(now)
            self._challenges[ch.id] = ch
        return IssuedCode(ch, code)

    def resend(self, challenge_id: str) -> IssuedCode:
        now = self.clock()
        with self._lock:
            ch = self._get(challenge_id)
            if now < ch.resend_available_at:
                wait = int(ch.resend_available_at - now + 0.999)
                raise ResendTooSoon(f"Resend available in {wait}s", resend_in=wait)
            if ch.resends >= self.max_resends:
                raise TooManyAttempts("Too many resends — start over")
            code = generate_code()
            ch.code_hash = _hash(code)
            ch.expires_at = now + self.ttl_seconds
            ch.resend_available_at = now + self.resend_cooldown_seconds
            ch.attempts = 0
            ch.resends += 1
        return IssuedCode(ch, code)

    # ── verifying ──────────────────────────────────────────────────────────
    def verify(self, challenge_id: str, code: str) -> str:
        now = self.clock()
        with self._lock:
            ch = self._get(challenge_id)
            if now >= ch.expires_at:
                del self._challenges[ch.id]
                raise ChallengeExpired("Code expired — request a new one")
            if ch.attempts >= self.max_attempts:
                raise TooManyAttempts(
                    "Too many incorrect attempts — request a new code"
                )
            if not hmac.compare_digest(ch.code_hash, _hash(code.strip())):
                ch.attempts += 1
                left = self.max_attempts - ch.attempts
                if left <= 0:
                    raise TooManyAttempts(
                        "Too many incorrect attempts — request a new code",
                        attempts_left=0,
                    )
                raise IncorrectCode("Incorrect code", attempts_left=left)
            del self._challenges[ch.id]
            token = secrets.token_urlsafe(24)
            self._tokens[token] = (ch.purpose, now + self.token_ttl_seconds)
            return token

    def consume_token(self, token: str | None, purpose: str) -> None:
        now = self.clock()
        with self._lock:
            entry = self._tokens.pop(token or "", None)
        if entry is None or entry[0] != purpose or now >= entry[1]:
            raise InvalidToken("Confirmation required")

    # ── helpers ────────────────────────────────────────────────────────────
    def _get(self, challenge_id: str) -> Challenge:
        ch = self._challenges.get(challenge_id)
        if ch is None:
            raise ChallengeNotFound(
                "Unknown or finished confirmation — request a new code"
            )
        return ch

    def _purge(self, now: float) -> None:
        for cid in [c.id for c in self._challenges.values() if now >= c.expires_at]:
            del self._challenges[cid]
        for tok in [t for t, (_, exp) in self._tokens.items() if now >= exp]:
            del self._tokens[tok]
