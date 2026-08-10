"""Safe, typed goal-saving recommendation logic."""

from __future__ import annotations

import math
import sqlite3
import statistics
from contextlib import nullcontext
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from db import connection


EXPENSE_COLUMNS = (
    "GROCERIES",
    "TRAVEL",
    "MEDFIT",
    "LEP",
    "MONTHLY_RENT",
    "M_BILLS",
    "FASHION",
    "ENTERTAINMENT",
    "EDUCATION",
    "EMSAVING",
    "MISCELLANEOUS",
)


@dataclass(frozen=True)
class RecommendationResult:
    feasible: bool
    recommended_monthly_saving: float
    estimated_duration_months: int | None
    requested_duration_months: int
    message: str
    warnings: list[str] = field(default_factory=list)
    missing_prerequisites: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _requested_months(start_date: date, end_date: date) -> int:
    duration_days = (end_date - start_date).days
    if duration_days <= 0:
        raise ValueError("End date must be after start date.")
    return max(1, math.ceil(duration_days / 30.0))


def _row_expense_total(row: sqlite3.Row) -> float:
    return sum(float(row[column] or 0) for column in EXPENSE_COLUMNS)


def _legacy_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _goal_compliance_factor(conn: sqlite3.Connection, user_id: int) -> tuple[float, list[str]]:
    warnings: list[str] = []
    goal = conn.execute(
        """
        SELECT GOALID, GOAL_AMOUNT, START_DATE, END_DATE
        FROM GOALS
        WHERE USER_ID = ?
        ORDER BY DATETIME(CREATED_AT) DESC, CREATED_AT DESC, GOALID DESC
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()
    if goal is None:
        return 1.0, warnings

    history = conn.execute(
        """
        SELECT SAVE_MONTH, CREATED_AT
        FROM GOAL_HISTORY
        WHERE GOALID = ?
        ORDER BY DATE(CREATED_AT) ASC, CREATED_AT ASC, HISTORY_ID ASC
        """,
        (goal["GOALID"],),
    ).fetchall()
    if not history:
        return 1.0, warnings

    historical_start = _legacy_date(goal["START_DATE"])
    historical_end = _legacy_date(goal["END_DATE"])
    if historical_start is None or historical_end is None or historical_end <= historical_start:
        warnings.append("A previous goal has invalid dates, so its saving history was not used.")
        return 1.0, warnings

    fixed_months = max(1, math.ceil((historical_end - historical_start).days / 30.0))
    goal_amount = float(goal["GOAL_AMOUNT"] or 0)
    if not math.isfinite(goal_amount) or goal_amount <= 0:
        warnings.append("A previous goal has an invalid amount, so its saving history was not used.")
        return 1.0, warnings

    saved_so_far = 0.0
    targeted: list[float] = []
    actual: list[float] = []
    for index, row in enumerate(history):
        remaining_months = fixed_months - index
        if remaining_months <= 0:
            break
        amount = float(row["SAVE_MONTH"] or 0)
        if not math.isfinite(amount) or amount < 0:
            continue
        required = max(0.0, (goal_amount - saved_so_far) / remaining_months)
        targeted.append(required)
        actual.append(amount)
        saved_so_far += amount

    target_total = sum(targeted)
    if target_total <= 0:
        return 1.0, warnings
    completion_ratio = sum(actual) / target_total
    if completion_ratio >= 1.0:
        return 1.05, warnings
    if completion_ratio >= 0.85:
        return 1.0, warnings
    if completion_ratio >= 0.60:
        return 0.90, warnings
    return 0.80, warnings


def calculate_recommendation(
    user_id: int,
    goal_amount: float,
    start_date: date,
    end_date: date,
    *,
    conn: sqlite3.Connection | None = None,
) -> RecommendationResult:
    """Calculate a recommendation from latest profiles plus expense history."""

    requested_months = _requested_months(start_date, end_date)
    if not math.isfinite(goal_amount) or goal_amount <= 0:
        raise ValueError("Goal amount must be a finite value greater than zero.")

    context = nullcontext(conn) if conn is not None else connection()
    with context as active_conn:
        income = active_conn.execute(
            """
            SELECT * FROM INCOMEPROFILE
            WHERE USER_ID = ?
            ORDER BY CREATED_AT DESC, PROFILE_ID DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        expense = active_conn.execute(
            """
            SELECT * FROM EXPENSEPROFILE
            WHERE USER_ID = ?
            ORDER BY CREATED_AT DESC, EXPENSE_ID DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()

        missing: list[str] = []
        if income is None:
            missing.append("income")
        if expense is None:
            missing.append("expenses")
        if missing:
            return RecommendationResult(
                feasible=False,
                recommended_monthly_saving=0.0,
                estimated_duration_months=None,
                requested_duration_months=requested_months,
                message="Complete the missing financial profiles before calculating this goal.",
                warnings=[],
                missing_prerequisites=missing,
            )

        total_income = float(income["MONTHLY_INCOME"] or 0) + float(
            income["ADDITIONAL_MONTHLY_INCOME"] or 0
        )
        current_expenses = _row_expense_total(expense)
        if not math.isfinite(total_income) or total_income <= 0:
            return RecommendationResult(
                feasible=False,
                recommended_monthly_saving=0.0,
                estimated_duration_months=None,
                requested_duration_months=requested_months,
                message="A positive monthly income is required before this goal can be funded.",
                warnings=[],
            )
        if not math.isfinite(current_expenses) or current_expenses < 0:
            return RecommendationResult(
                feasible=False,
                recommended_monthly_saving=0.0,
                estimated_duration_months=None,
                requested_duration_months=requested_months,
                message="The latest expense profile contains invalid values.",
                warnings=[],
            )

        net_cash = total_income - current_expenses
        if net_cash <= 0:
            return RecommendationResult(
                feasible=False,
                recommended_monthly_saving=0.0,
                estimated_duration_months=None,
                requested_duration_months=requested_months,
                message="Current expenses are greater than or equal to income, so this goal is not presently feasible.",
                warnings=["Reduce expenses or increase income before committing a monthly target."],
            )

        dependants = max(0, int(income["DEPENDANTS"] or 0))
        dependant_factor = 1 - min(0.03 * dependants, 0.18)
        dependant_adjusted_cash = net_cash * dependant_factor

        free_cash_ratio = net_cash / total_income
        if free_cash_ratio < 0.15:
            buffer_rate = 0.30
        elif free_cash_ratio < 0.30:
            buffer_rate = 0.20
        else:
            buffer_rate = 0.10
        buffered_saving = dependant_adjusted_cash * (1 - buffer_rate)

        # The legacy variable-overwrite bug is corrected: actual M_BILLS is included.
        fixed_expenses = sum(
            float(expense[column] or 0)
            for column in ("LEP", "MONTHLY_RENT", "M_BILLS", "MEDFIT", "EDUCATION")
        )
        fixed_ratio = fixed_expenses / total_income
        if fixed_ratio >= 0.60:
            fixed_factor = 0.85
        elif fixed_ratio >= 0.40:
            fixed_factor = 0.92
        else:
            fixed_factor = 1.0
        fixed_adjusted_saving = buffered_saving * fixed_factor

        expense_rows = active_conn.execute(
            """
            SELECT * FROM EXPENSEPROFILE
            WHERE USER_ID = ?
            ORDER BY CREATED_AT ASC, EXPENSE_ID ASC
            """,
            (user_id,),
        ).fetchall()
        expense_totals = [_row_expense_total(row) for row in expense_rows]
        mean_expense = statistics.fmean(expense_totals) if expense_totals else 0.0
        if mean_expense > 0 and len(expense_totals) > 1:
            coefficient = statistics.pstdev(expense_totals) / mean_expense
            volatility_factor = max(0.80, 1 - 0.5 * coefficient)
        else:
            volatility_factor = 1.0

        compliance_factor, warnings = _goal_compliance_factor(active_conn, user_id)
        recommended = max(
            0.0, fixed_adjusted_saving * volatility_factor * compliance_factor
        )
        if not math.isfinite(recommended) or recommended <= 0:
            return RecommendationResult(
                feasible=False,
                recommended_monthly_saving=0.0,
                estimated_duration_months=None,
                requested_duration_months=requested_months,
                message="A safe finite monthly target could not be calculated from the current profiles.",
                warnings=warnings,
            )

        estimated_months = max(1, math.ceil(goal_amount / recommended))
        if estimated_months > requested_months:
            warnings.append(
                "The estimated saving duration is longer than the requested date range."
            )
            message = "The goal is feasible, but the requested end date may require a higher monthly contribution."
        else:
            message = "The goal is feasible with the recommended monthly contribution."

        return RecommendationResult(
            feasible=True,
            recommended_monthly_saving=round(recommended, 2),
            estimated_duration_months=estimated_months,
            requested_duration_months=requested_months,
            message=message,
            warnings=warnings,
        )
