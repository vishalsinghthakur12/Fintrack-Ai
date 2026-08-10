from __future__ import annotations

import math

from tests.conftest import APITestContext, auth_headers


def goal_payload(name: str = "Emergency fund", status: str = "ACTIVE") -> dict:
    return {
        "goal_name": name,
        "goal_amount": 120_000,
        "start_date": "2026-01-01",
        "end_date": "2027-01-01",
        "goal_status": status,
    }


def test_goal_requires_profiles(api_context: APITestContext, register_user):
    auth = register_user("missing-profiles@example.com")
    response = api_context.client.post(
        "/api/goals", headers=auth_headers(auth), json=goal_payload()
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "missing_profiles"


def test_create_update_goal_and_validate(api_context, register_user, complete_profiles):
    owner = register_user("goal-owner@example.com")
    other = register_user("goal-other@example.com")
    complete_profiles(owner)
    complete_profiles(other)
    created = api_context.client.post(
        "/api/goals", headers=auth_headers(owner), json=goal_payload()
    )
    assert created.status_code == 201
    body = created.json()
    assert body["recommendation"]["feasible"] is True
    assert math.isfinite(body["monthly_saving_target"])

    changed = goal_payload("Updated emergency fund", "PAUSED")
    updated = api_context.client.put(
        f"/api/goals/{body['goal_id']}", headers=auth_headers(owner), json=changed
    )
    assert updated.status_code == 200
    assert updated.json()["goal_status"] == "PAUSED"
    assert api_context.client.put(
        f"/api/goals/{body['goal_id']}", headers=auth_headers(other), json=changed
    ).status_code == 403

    invalid_dates = goal_payload()
    invalid_dates["end_date"] = invalid_dates["start_date"]
    assert api_context.client.post(
        "/api/goals/recommendation", headers=auth_headers(owner), json=invalid_dates
    ).status_code == 422
    invalid_amount = goal_payload()
    invalid_amount["goal_amount"] = 0
    assert api_context.client.post(
        "/api/goals", headers=auth_headers(owner), json=invalid_amount
    ).status_code == 422


def test_goal_history_order_duplicate_and_ownership(api_context, register_user, complete_profiles):
    owner = register_user("history-owner@example.com")
    other = register_user("history-other@example.com")
    complete_profiles(owner)
    complete_profiles(other)
    goal = api_context.client.post(
        "/api/goals", headers=auth_headers(owner), json=goal_payload()
    ).json()
    goal_id = goal["goal_id"]
    later = {"saving_date": "2026-03-01", "amount_saved": 5000}
    earlier = {"saving_date": "2026-02-01", "amount_saved": 4000}
    assert api_context.client.post(
        f"/api/goals/{goal_id}/history", headers=auth_headers(owner), json=later
    ).status_code == 201
    assert api_context.client.post(
        f"/api/goals/{goal_id}/history", headers=auth_headers(owner), json=earlier
    ).status_code == 201
    duplicate = api_context.client.post(
        f"/api/goals/{goal_id}/history", headers=auth_headers(owner), json=earlier
    )
    assert duplicate.status_code == 409
    history = api_context.client.get(
        f"/api/goals/{goal_id}/history", headers=auth_headers(owner)
    ).json()
    assert [item["saving_date"] for item in history] == ["2026-02-01", "2026-03-01"]
    assert api_context.client.get(
        f"/api/goals/{goal_id}", headers=auth_headers(other)
    ).status_code == 403
    assert api_context.client.post(
        f"/api/goals/{goal_id}/history", headers=auth_headers(other), json=later
    ).status_code == 403


def test_recommendation_infeasible_and_finite(api_context, register_user, complete_profiles):
    high_expense = register_user("infeasible@example.com")
    complete_profiles(high_expense, income=10_000, expenses=20_000)
    result = api_context.client.post(
        "/api/goals/recommendation", headers=auth_headers(high_expense), json=goal_payload()
    )
    assert result.status_code == 200
    assert result.json()["feasible"] is False
    assert result.json()["recommended_monthly_saving"] == 0
    saved = api_context.client.post(
        "/api/goals", headers=auth_headers(high_expense), json=goal_payload()
    )
    assert saved.status_code == 201
    assert isinstance(saved.json()["monthly_saving_target"], float)

    zero_income = register_user("zero-income@example.com")
    complete_profiles(zero_income, income=0, expenses=0)
    zero = api_context.client.post(
        "/api/goals/recommendation", headers=auth_headers(zero_income), json=goal_payload()
    ).json()
    assert zero["feasible"] is False
    assert math.isfinite(zero["recommended_monthly_saving"])


def test_empty_analytics_returns_partial_response(api_context, register_user):
    auth = register_user("empty-analytics@example.com")
    response = api_context.client.get("/api/analytics/summary", headers=auth_headers(auth))
    assert response.status_code == 200
    body = response.json()
    assert body["income_profile"] is None
    assert body["expense_profile"] is None
    assert body["goals"] == []
    assert body["profile_completion"] == {
        "has_income": False,
        "has_expenses": False,
        "has_goals": False,
    }
    assert len(body["warnings"]) == 3


def test_analytics_latest_totals_status_counts_and_scope(api_context, register_user, complete_profiles):
    owner = register_user("analytics-owner@example.com")
    other = register_user("analytics-other@example.com")
    complete_profiles(owner, income=50_000, expenses=11_000)
    complete_profiles(owner, income=100_000, expenses=22_000)
    complete_profiles(other, income=999_999, expenses=11)
    for name, status in (("Active one", "ACTIVE"), ("Paused one", "PAUSED")):
        api_context.client.post(
            "/api/goals", headers=auth_headers(owner), json=goal_payload(name, status)
        )
    api_context.client.post(
        "/api/goals", headers=auth_headers(other), json=goal_payload("Other goal", "ACHIEVED")
    )

    body = api_context.client.get(
        "/api/analytics/summary", headers=auth_headers(owner)
    ).json()
    assert body["total_monthly_income"] == 100_000
    assert body["total_monthly_expenses"] == 22_000
    assert body["free_cash_flow"] == 78_000
    assert body["goal_status_counts"]["ACTIVE"] == 1
    assert body["goal_status_counts"]["PAUSED"] == 1
    assert body["goal_status_counts"]["ACHIEVED"] == 0
    assert len(body["goals"]) == 2
