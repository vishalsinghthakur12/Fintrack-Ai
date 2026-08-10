from __future__ import annotations

import math
from datetime import date

from recommendation import RecommendationResult, calculate_recommendation
from tests.conftest import APITestContext


def test_typed_recommendation_missing_profiles(api_context: APITestContext, register_user):
    auth = register_user("recommendation-missing@example.com")
    result = calculate_recommendation(
        auth["user"]["user_id"],
        100_000,
        date(2026, 1, 1),
        date(2027, 1, 1),
    )
    assert isinstance(result, RecommendationResult)
    assert result.feasible is False
    assert result.missing_prerequisites == ["income", "expenses"]


def test_typed_recommendation_is_finite(api_context, register_user, complete_profiles):
    auth = register_user("recommendation-finite@example.com")
    complete_profiles(auth, income=150_000, expenses=45_000)
    result = calculate_recommendation(
        auth["user"]["user_id"],
        300_000,
        date(2026, 1, 1),
        date(2027, 6, 1),
    )
    assert result.feasible is True
    assert result.estimated_duration_months is not None
    assert math.isfinite(result.recommended_monthly_saving)
    assert result.recommended_monthly_saving > 0


def test_recommendation_rejects_invalid_duration(api_context, register_user):
    auth = register_user("recommendation-duration@example.com")
    try:
        calculate_recommendation(
            auth["user"]["user_id"],
            100_000,
            date(2026, 1, 1),
            date(2026, 1, 1),
        )
    except ValueError as exc:
        assert "End date" in str(exc)
    else:
        raise AssertionError("Invalid duration was accepted")
