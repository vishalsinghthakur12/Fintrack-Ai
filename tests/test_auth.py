from __future__ import annotations

from datetime import timedelta

from werkzeug.security import generate_password_hash

from db import transaction, utc_now
from tests.conftest import APITestContext, auth_headers


def test_signup_validation(api_context: APITestContext):
    response = api_context.client.post(
        "/api/auth/signup/start",
        json={
            "name": "A",
            "email": "not-an-email",
            "gender": "Other",
            "password": "short",
            "confirm_password": "different",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert '"short"' not in response.text


def test_case_insensitive_duplicate_rejected(api_context, register_user):
    register_user("MixedCase@Example.com")
    response = api_context.client.post(
        "/api/auth/signup/start",
        json={
            "name": "Another User",
            "email": "MIXEDCASE@EXAMPLE.COM",
            "gender": "Female",
            "password": "SecurePass123",
            "confirm_password": "SecurePass123",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_exists"


def test_otp_expiry(api_context: APITestContext):
    payload = {
        "name": "Expiry User",
        "email": "expiry@example.com",
        "gender": "Male",
        "password": "SecurePass123",
        "confirm_password": "SecurePass123",
    }
    assert api_context.client.post("/api/auth/signup/start", json=payload).status_code == 200
    with transaction(immediate=True) as conn:
        conn.execute(
            "UPDATE PENDING_SIGNUP SET OTP_EXP = ? WHERE EMAIL = ?",
            ((utc_now() - timedelta(seconds=1)).isoformat(), payload["email"]),
        )
    response = api_context.client.post(
        "/api/auth/signup/verify",
        json={"email": payload["email"], "otp": api_context.outbox[payload["email"]]},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "otp_expired"


def test_incorrect_otp_attempts_lock_signup(api_context: APITestContext):
    email = "attempts@example.com"
    payload = {
        "name": "Attempt User",
        "email": email,
        "gender": "Other",
        "password": "SecurePass123",
        "confirm_password": "SecurePass123",
    }
    api_context.client.post("/api/auth/signup/start", json=payload)
    assert api_context.client.post("/api/auth/signup/verify", json={"email": email, "otp": "0000"}).status_code == 400
    assert api_context.client.post("/api/auth/signup/verify", json={"email": email, "otp": "0000"}).status_code == 400
    locked = api_context.client.post("/api/auth/signup/verify", json={"email": email, "otp": "0000"})
    assert locked.status_code == 429
    correct_after_lock = api_context.client.post(
        "/api/auth/signup/verify", json={"email": email, "otp": api_context.outbox[email]}
    )
    assert correct_after_lock.status_code == 429


def test_successful_verification_and_safe_response(api_context, register_user):
    auth = register_user("safe@example.com")
    assert auth["token_type"] == "bearer"
    assert auth["user"]["email"] == "safe@example.com"
    serialized = str(auth).lower()
    assert "password_hash" not in serialized
    assert "otp_hash" not in serialized
    assert "email_otp" not in serialized
    me = api_context.client.get("/api/auth/me", headers=auth_headers(auth))
    assert me.status_code == 200
    assert set(me.json()) == {"user_id", "name", "gender", "email", "created_at"}


def test_existing_werkzeug_password_hash_login(api_context: APITestContext):
    with transaction(immediate=True) as conn:
        conn.execute(
            "INSERT INTO USER(USER_ID, USER_NAME, GENDER, EMAIL, PASSWORD_HASH, CREATED_AT) VALUES(?, ?, ?, ?, ?, ?)",
            (1, "Legacy User", "OTHER", "Legacy@Example.com", generate_password_hash("LegacyPass123"), utc_now().isoformat()),
        )
    response = api_context.client.post(
        "/api/auth/login",
        json={"email": "legacy@example.com", "password": "LegacyPass123"},
    )
    assert response.status_code == 200
    assert response.json()["user"]["email"] == "legacy@example.com"


def test_invalid_login_and_protected_endpoint(api_context: APITestContext):
    invalid = api_context.client.post(
        "/api/auth/login",
        json={"email": "missing@example.com", "password": "WrongPass123"},
    )
    assert invalid.status_code == 401
    assert api_context.client.get("/api/income").status_code == 401


def test_expired_and_revoked_sessions(api_context, register_user):
    auth = register_user("sessions@example.com")
    headers = auth_headers(auth)
    with transaction(immediate=True) as conn:
        conn.execute(
            "UPDATE AUTH_SESSION SET EXPIRES_AT = ?",
            ((utc_now() - timedelta(seconds=1)).isoformat(),),
        )
    assert api_context.client.get("/api/auth/me", headers=headers).status_code == 401

    login = api_context.client.post(
        "/api/auth/login",
        json={"email": "sessions@example.com", "password": "SecurePass123"},
    ).json()
    login_headers = auth_headers(login)
    assert api_context.client.post("/api/auth/logout", headers=login_headers).status_code == 200
    assert api_context.client.get("/api/auth/me", headers=login_headers).status_code == 401


def test_pending_signup_and_session_are_restart_safe(api_context: APITestContext, monkeypatch):
    email = "restart@example.com"
    payload = {
        "name": "Restart User",
        "email": email,
        "gender": "Other",
        "password": "SecurePass123",
        "confirm_password": "SecurePass123",
    }
    assert api_context.client.post("/api/auth/signup/start", json=payload).status_code == 200
    from app import create_app

    from fastapi.testclient import TestClient

    with TestClient(create_app()) as restarted:
        verified = restarted.post(
            "/api/auth/signup/verify",
            json={"email": email, "otp": api_context.outbox[email]},
        )
        assert verified.status_code == 201
        assert restarted.get("/api/auth/me", headers=auth_headers(verified.json())).status_code == 200
