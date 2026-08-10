from __future__ import annotations

from tests.conftest import APITestContext, auth_headers


def income_payload(monthly_income: float = 50_000) -> dict:
    return {
        "income_type": "SALARIED",
        "monthly_income": monthly_income,
        "additional_income_type": "INVESTEMENTS",
        "additional_monthly_income": 5_000,
        "dependants": 2,
    }


def expense_payload(base: float = 1_000) -> dict:
    return {
        "groceries": base,
        "travel": base + 1,
        "medfit": base + 2,
        "lep": base + 3,
        "monthly_rent": base + 4,
        "m_bills": base + 5,
        "fashion": base + 6,
        "entertainment": base + 7,
        "education": base + 8,
        "emsaving": base + 9,
        "miscellaneous": base + 10,
    }


def test_add_update_and_latest_income(api_context: APITestContext, register_user):
    auth = register_user("income@example.com")
    headers = auth_headers(auth)
    first = api_context.client.post("/api/income", headers=headers, json=income_payload(40_000))
    assert first.status_code == 201
    second = api_context.client.post("/api/income", headers=headers, json=income_payload(80_000))
    assert second.status_code == 201
    latest = api_context.client.get("/api/income/latest", headers=headers)
    assert latest.json()["profile_id"] == second.json()["profile_id"]

    created_at = latest.json()["created_at"]
    changed = income_payload(90_000)
    changed["dependants"] = 1
    updated = api_context.client.put(
        f"/api/income/{latest.json()['profile_id']}", headers=headers, json=changed
    )
    assert updated.status_code == 200
    assert updated.json()["monthly_income"] == 90_000
    assert updated.json()["created_at"] == created_at
    assert len(api_context.client.get("/api/income", headers=headers).json()) == 2


def test_income_ownership_and_validation(api_context: APITestContext, register_user):
    owner = register_user("income-owner@example.com")
    other = register_user("income-other@example.com")
    created = api_context.client.post(
        "/api/income", headers=auth_headers(owner), json=income_payload()
    ).json()
    forbidden = api_context.client.put(
        f"/api/income/{created['profile_id']}",
        headers=auth_headers(other),
        json=income_payload(60_000),
    )
    assert forbidden.status_code == 403
    invalid = income_payload(-1)
    assert api_context.client.post("/api/income", headers=auth_headers(owner), json=invalid).status_code == 422


def test_add_update_and_latest_expenses(api_context: APITestContext, register_user):
    auth = register_user("expenses@example.com")
    headers = auth_headers(auth)
    first = api_context.client.post("/api/expenses", headers=headers, json=expense_payload(100))
    assert first.status_code == 201
    second = api_context.client.post("/api/expenses", headers=headers, json=expense_payload(200))
    assert second.status_code == 201
    latest = api_context.client.get("/api/expenses/latest", headers=headers)
    assert latest.json()["expense_id"] == second.json()["expense_id"]
    assert latest.json()["total_expenses"] == sum(expense_payload(200).values())

    changed = expense_payload(300)
    updated = api_context.client.put(
        f"/api/expenses/{latest.json()['expense_id']}", headers=headers, json=changed
    )
    assert updated.status_code == 200
    assert updated.json()["groceries"] == 300
    assert len(api_context.client.get("/api/expenses", headers=headers).json()) == 2


def test_expense_ownership_and_validation(api_context: APITestContext, register_user):
    owner = register_user("expense-owner@example.com")
    other = register_user("expense-other@example.com")
    created = api_context.client.post(
        "/api/expenses", headers=auth_headers(owner), json=expense_payload()
    ).json()
    forbidden = api_context.client.put(
        f"/api/expenses/{created['expense_id']}",
        headers=auth_headers(other),
        json=expense_payload(2000),
    )
    assert forbidden.status_code == 403
    invalid = expense_payload()
    invalid["travel"] = -0.01
    assert api_context.client.post("/api/expenses", headers=auth_headers(owner), json=invalid).status_code == 422
