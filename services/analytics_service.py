"""Authenticated, partial-data-friendly analytics aggregation."""

from __future__ import annotations

from errors import AppError
from services.goal_service import list_goals
from services.profile_service import latest_expenses, latest_income


GOAL_STATUSES = ("ACTIVE", "PAUSED", "ACHIEVED", "EXPIRED", "INACTIVE")


def analytics_summary(user_id: int) -> dict:
    warnings: list[str] = []

    try:
        income = latest_income(user_id)
    except AppError as exc:
        if exc.status_code != 404:
            raise
        income = None
        warnings.append("Add an income profile to complete income analytics.")

    try:
        expenses = latest_expenses(user_id)
    except AppError as exc:
        if exc.status_code != 404:
            raise
        expenses = None
        warnings.append("Add an expense profile to complete expense analytics.")

    goals = list_goals(user_id)
    if not goals:
        warnings.append("Create a goal to begin tracking saving progress.")

    total_income = 0.0
    if income:
        total_income = float(income["monthly_income"]) + float(
            income["additional_monthly_income"]
        )
    total_expenses = float(expenses["total_expenses"]) if expenses else 0.0
    status_counts = {status: 0 for status in GOAL_STATUSES}
    for goal in goals:
        status = goal["goal_status"]
        if status in status_counts:
            status_counts[status] += 1

    return {
        "income_profile": income,
        "expense_profile": expenses,
        "goals": goals,
        "goal_status_counts": status_counts,
        "total_monthly_income": round(total_income, 2),
        "total_monthly_expenses": round(total_expenses, 2),
        "free_cash_flow": round(total_income - total_expenses, 2),
        "total_goal_amount": round(sum(goal["goal_amount"] for goal in goals), 2),
        "profile_completion": {
            "has_income": income is not None,
            "has_expenses": expenses is not None,
            "has_goals": bool(goals),
        },
        "warnings": warnings,
    }
