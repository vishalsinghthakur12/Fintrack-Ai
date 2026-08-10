from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pytest
from fastapi.testclient import TestClient


@dataclass
class APITestContext:
    client: TestClient
    outbox: dict[str, str]


@pytest.fixture
def api_context(tmp_path, monkeypatch) -> APITestContext:
    monkeypatch.setenv("FINTRACK_DB_PATH", str(tmp_path / "test-fintrack.db"))
    monkeypatch.setenv("FINTRACK_SECRET_KEY", "test-secret-key-with-at-least-32-characters")
    monkeypatch.setenv("FINTRACK_OTP_TTL_SECONDS", "300")
    monkeypatch.setenv("FINTRACK_OTP_RESEND_COOLDOWN_SECONDS", "1")
    monkeypatch.setenv("FINTRACK_OTP_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("FINTRACK_SESSION_TTL_SECONDS", "3600")

    from app import create_app
    from services import auth_service

    outbox: dict[str, str] = {}

    def fake_send_otp_email(*, recipient_name: str, recipient_email: str, otp: str) -> None:
        del recipient_name
        outbox[recipient_email] = otp

    monkeypatch.setattr(auth_service, "send_otp_email", fake_send_otp_email)
    with TestClient(create_app()) as client:
        yield APITestContext(client=client, outbox=outbox)


@pytest.fixture
def register_user(api_context: APITestContext) -> Callable[..., dict]:
    counter = {"value": 0}

    def register(
        email: str | None = None,
        *,
        password: str = "SecurePass123",
        name: str = "Test User",
    ) -> dict:
        counter["value"] += 1
        selected_email = email or f"user{counter['value']}@example.com"
        start = api_context.client.post(
            "/api/auth/signup/start",
            json={
                "name": name,
                "email": selected_email,
                "gender": "Other",
                "password": password,
                "confirm_password": password,
            },
        )
        assert start.status_code == 200
        normalized = selected_email.lower()
        verify = api_context.client.post(
            "/api/auth/signup/verify",
            json={"email": normalized, "otp": api_context.outbox[normalized]},
        )
        assert verify.status_code == 201
        return verify.json()

    return register


def auth_headers(auth: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}


@pytest.fixture
def complete_profiles(api_context: APITestContext):
    def create(auth: dict, *, income: float = 100_000, expenses: float = 20_000) -> None:
        headers = auth_headers(auth)
        income_response = api_context.client.post(
            "/api/income",
            headers=headers,
            json={
                "income_type": "SALARIED",
                "monthly_income": income,
                "additional_income_type": "INVESTEMENTS",
                "additional_monthly_income": 0,
                "dependants": 0,
            },
        )
        assert income_response.status_code == 201
        each = expenses / 11
        expense_response = api_context.client.post(
            "/api/expenses",
            headers=headers,
            json={
                "groceries": each,
                "travel": each,
                "medfit": each,
                "lep": each,
                "monthly_rent": each,
                "m_bills": each,
                "fashion": each,
                "entertainment": each,
                "education": each,
                "emsaving": each,
                "miscellaneous": each,
            },
        )
        assert expense_response.status_code == 201

    return create
