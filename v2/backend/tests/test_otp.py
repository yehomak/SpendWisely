"""OTP confirmation: code generation, TTL, attempt limit, resend, and the gated delete endpoint."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.services.otp import (
    ChallengeExpired,
    ChallengeNotFound,
    IncorrectCode,
    InvalidToken,
    OtpStore,
    ResendTooSoon,
    TooManyAttempts,
    generate_code,
)


class FakeClock:
    def __init__(self, t: float = 1000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def store(clock):
    return OtpStore(
        ttl_seconds=600, max_attempts=5, resend_cooldown_seconds=30, clock=clock
    )


def _wrong(code: str) -> str:
    return "".join(str((int(c) + 1) % 10) for c in code)


# ── generation ─────────────────────────────────────────────────────────────
def test_generate_code_is_six_digits():
    for _ in range(200):
        assert re.fullmatch(r"\d{6}", generate_code())


def test_codes_are_random_and_new_per_request(store):
    codes = {store.request("delete_all_transactions").code for _ in range(50)}
    # 50 draws from 10^6: a collision-free set is overwhelmingly likely; allow one dup
    assert len(codes) >= 49


def test_plaintext_code_is_not_stored(store):
    issued = store.request("p")
    assert issued.challenge.code_hash != issued.code
    assert issued.code not in repr(store._challenges)


# ── verify / TTL ───────────────────────────────────────────────────────────
def test_correct_code_returns_single_use_token(store):
    issued = store.request("p")
    token = store.verify(issued.challenge.id, issued.code)
    store.consume_token(token, "p")
    with pytest.raises(InvalidToken):
        store.consume_token(token, "p")  # single use


def test_challenge_cannot_be_reused_after_success(store):
    issued = store.request("p")
    store.verify(issued.challenge.id, issued.code)
    with pytest.raises(ChallengeNotFound):
        store.verify(issued.challenge.id, issued.code)


def test_token_is_bound_to_purpose(store):
    issued = store.request("p")
    token = store.verify(issued.challenge.id, issued.code)
    with pytest.raises(InvalidToken):
        store.consume_token(token, "other")


def test_code_valid_just_before_ttl(store, clock):
    issued = store.request("p")
    clock.advance(599)
    assert store.verify(issued.challenge.id, issued.code)


def test_code_expires_after_ttl(store, clock):
    issued = store.request("p")
    clock.advance(600)
    with pytest.raises(ChallengeExpired):
        store.verify(issued.challenge.id, issued.code)
    with pytest.raises(ChallengeNotFound):  # expired challenge is dropped
        store.verify(issued.challenge.id, issued.code)


def test_confirmation_token_expires(store, clock):
    issued = store.request("p")
    token = store.verify(issued.challenge.id, issued.code)
    clock.advance(store.token_ttl_seconds)
    with pytest.raises(InvalidToken):
        store.consume_token(token, "p")


# ── attempt limit ──────────────────────────────────────────────────────────
def test_wrong_code_reports_attempts_left(store):
    issued = store.request("p")
    with pytest.raises(IncorrectCode) as e:
        store.verify(issued.challenge.id, _wrong(issued.code))
    assert e.value.message == "Incorrect code"
    assert e.value.extra["attempts_left"] == 4


def test_locks_after_max_attempts_even_with_correct_code(store):
    issued = store.request("p")
    for left in (4, 3, 2, 1):
        with pytest.raises(IncorrectCode) as e:
            store.verify(issued.challenge.id, _wrong(issued.code))
        assert e.value.extra["attempts_left"] == left
    with pytest.raises(TooManyAttempts):  # 5th wrong attempt locks
        store.verify(issued.challenge.id, _wrong(issued.code))
    with pytest.raises(TooManyAttempts):  # correct code no longer accepted
        store.verify(issued.challenge.id, issued.code)


# ── resend ─────────────────────────────────────────────────────────────────
def test_resend_respects_cooldown(store, clock):
    issued = store.request("p")
    clock.advance(10)
    with pytest.raises(ResendTooSoon) as e:
        store.resend(issued.challenge.id)
    assert e.value.extra["resend_in"] == 20


def test_resend_invalidates_old_code_and_resets_attempts(store, clock):
    issued = store.request("p")
    for _ in range(4):
        with pytest.raises(IncorrectCode):
            store.verify(issued.challenge.id, _wrong(issued.code))
    clock.advance(30)
    fresh = store.resend(issued.challenge.id)
    assert fresh.challenge.id == issued.challenge.id
    if fresh.code != issued.code:  # 1-in-a-million chance they collide
        with pytest.raises(IncorrectCode) as e:
            store.verify(issued.challenge.id, issued.code)
        assert e.value.extra["attempts_left"] == 4  # attempts were reset
    assert store.verify(issued.challenge.id, fresh.code)


def test_resend_extends_ttl(store, clock):
    issued = store.request("p")
    clock.advance(590)
    fresh = store.resend(issued.challenge.id)
    clock.advance(300)  # 890s after the first request, 300s after resend
    assert store.verify(issued.challenge.id, fresh.code)


# ── HTTP: /otp/* and gated DELETE /transactions ────────────────────────────
@pytest.fixture
def api(monkeypatch, clock):
    from app import main
    from app.routers import otp as otp_router

    sent: list[dict] = []
    monkeypatch.setattr(
        otp_router.mailer,
        "send_otp_email",
        lambda to, code, label, ttl: sent.append(
            {"to": to, "code": code, "label": label}
        ),
    )
    monkeypatch.setattr(otp_router.store, "clock", clock)
    with TestClient(main.app) as client:
        yield client, sent


def _seed_one_transaction():
    from app.database import db

    with db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO transactions (id, booking_date, month, counterparty, amount,"
            " abs_amount, currency, direction) VALUES ('t1', DATE '2026-11-01', '2026-11',"
            " 'Shop', -10, 10, 'PLN', 'expense')"
        )


def _count() -> int:
    from app.database import db

    with db() as conn:
        return conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]


def test_delete_all_requires_confirmation(api):
    client, _ = api
    _seed_one_transaction()
    r = client.delete("/api/v1/transactions")
    assert r.status_code == 403
    assert _count() == 1
    r = client.delete(
        "/api/v1/transactions", headers={"X-Confirmation-Token": "forged"}
    )
    assert r.status_code == 403
    assert _count() == 1


def test_full_flow_code_only_in_email(api):
    client, sent = api
    _seed_one_transaction()

    r = client.post("/api/v1/otp/request", json={"purpose": "delete_all_transactions"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"challenge_id", "email_hint", "expires_in", "resend_in"}
    code = sent[-1]["code"]
    assert code not in r.text  # never leaked in the response
    assert sent[-1]["to"] == "owner@example.test"

    r = client.post(
        "/api/v1/otp/verify",
        json={"challenge_id": body["challenge_id"], "code": _wrong(code)},
    )
    assert r.status_code == 400
    assert r.json() == {"detail": "Incorrect code", "attempts_left": 4}

    r = client.post(
        "/api/v1/otp/verify", json={"challenge_id": body["challenge_id"], "code": code}
    )
    assert r.status_code == 200
    token = r.json()["confirmation_token"]

    r = client.delete("/api/v1/transactions", headers={"X-Confirmation-Token": token})
    assert r.status_code == 200
    assert r.json()["deleted"] == 1
    assert _count() == 0

    # token is single-use
    r = client.delete("/api/v1/transactions", headers={"X-Confirmation-Token": token})
    assert r.status_code == 403


def test_http_attempt_limit_and_expiry(api, clock):
    client, sent = api
    cid = client.post(
        "/api/v1/otp/request", json={"purpose": "delete_all_transactions"}
    ).json()["challenge_id"]
    code = sent[-1]["code"]
    for _ in range(5):
        r = client.post(
            "/api/v1/otp/verify", json={"challenge_id": cid, "code": _wrong(code)}
        )
    assert r.status_code == 429
    assert (
        client.post(
            "/api/v1/otp/verify", json={"challenge_id": cid, "code": code}
        ).status_code
        == 429
    )

    cid = client.post(
        "/api/v1/otp/request", json={"purpose": "delete_all_transactions"}
    ).json()["challenge_id"]
    code = sent[-1]["code"]
    clock.advance(601)
    assert (
        client.post(
            "/api/v1/otp/verify", json={"challenge_id": cid, "code": code}
        ).status_code
        == 410
    )


def test_http_resend_cooldown_and_new_code(api, clock):
    client, sent = api
    first = client.post(
        "/api/v1/otp/request", json={"purpose": "delete_all_transactions"}
    ).json()
    assert first["resend_in"] == 30
    r = client.post("/api/v1/otp/resend", json={"challenge_id": first["challenge_id"]})
    assert r.status_code == 429 and r.json()["resend_in"] == 30
    clock.advance(30)
    r = client.post("/api/v1/otp/resend", json={"challenge_id": first["challenge_id"]})
    assert r.status_code == 200
    assert len(sent) == 2


def test_unknown_purpose_rejected(api):
    client, sent = api
    r = client.post("/api/v1/otp/request", json={"purpose": "nope"})
    assert r.status_code == 400 and not sent


def test_smtp_failure_returns_503(api, monkeypatch):
    client, _ = api
    from app.routers import otp as otp_router

    def boom(*a, **k):
        raise ConnectionRefusedError("no smtp")

    monkeypatch.setattr(otp_router.mailer, "send_otp_email", boom)
    r = client.post("/api/v1/otp/request", json={"purpose": "delete_all_transactions"})
    assert r.status_code == 503
