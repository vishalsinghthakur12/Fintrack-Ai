"""Owned goal, recommendation, and monthly-saving history operations."""

from __future__ import annotations

import sqlite3
from typing import Any

from db import allocate_id, connection, transaction, utc_now_iso
from errors import conflict, forbidden, not_found
from recommendation import calculate_recommendation
from schemas import GoalHistoryPayload, GoalPayload


def _owned_goal(conn: sqlite3.Connection, user_id: int, goal_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM GOALS WHERE GOALID = ?", (goal_id,)).fetchone()
    if row is None:
        raise not_found("Goal")
    if int(row["USER_ID"]) != user_id:
        raise forbidden()
    return row


def _goal_dict(row: sqlite3.Row, total_saved: float = 0.0) -> dict[str, Any]:
    amount = float(row["GOAL_AMOUNT"] or 0)
    saved = float(total_saved or 0)
    progress = round((saved / amount) * 100, 2) if amount > 0 else 0.0
    return {
        "goal_id": int(row["GOALID"]),
        "goal_name": row["GOAL_NAME"],
        "goal_amount": amount,
        "start_date": str(row["START_DATE"])[:10],
        "end_date": str(row["END_DATE"])[:10],
        "monthly_saving_target": float(row["MONTHLY_SAVING_T"] or 0),
        "goal_status": row["GOAL_STATUS"],
        "created_at": row["CREATED_AT"],
        "updated_at": row["UPDATED_AT"],
        "total_saved": round(saved, 2),
        "progress_percent": progress,
        "recommendation": None,
    }


def preview_recommendation(user_id: int, payload: GoalPayload) -> dict[str, Any]:
    return calculate_recommendation(
        user_id,
        payload.goal_amount,
        payload.start_date,
        payload.end_date,
    ).as_dict()


def list_goals(user_id: int) -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT G.*, COALESCE(SUM(H.SAVE_MONTH), 0) AS TOTAL_SAVED
            FROM GOALS AS G
            LEFT JOIN GOAL_HISTORY AS H ON H.GOALID = G.GOALID
            WHERE G.USER_ID = ?
            GROUP BY G.GOALID
            ORDER BY G.CREATED_AT DESC, G.GOALID DESC
            """,
            (user_id,),
        ).fetchall()
    return [_goal_dict(row, row["TOTAL_SAVED"]) for row in rows]


def get_goal(user_id: int, goal_id: int) -> dict[str, Any]:
    with connection() as conn:
        row = _owned_goal(conn, user_id, goal_id)
        saved = conn.execute(
            "SELECT COALESCE(SUM(SAVE_MONTH), 0) FROM GOAL_HISTORY WHERE GOALID = ?",
            (goal_id,),
        ).fetchone()[0]
    return _goal_dict(row, saved)


def create_goal(user_id: int, payload: GoalPayload) -> dict[str, Any]:
    with transaction(immediate=True) as conn:
        recommendation = calculate_recommendation(
            user_id,
            payload.goal_amount,
            payload.start_date,
            payload.end_date,
            conn=conn,
        )
        if recommendation.missing_prerequisites:
            raise conflict(
                "missing_profiles",
                "Complete income and expense setup before creating a goal.",
                missing_prerequisites=recommendation.missing_prerequisites,
            )
        goal_id = allocate_id(conn, "GOALS")
        now = utc_now_iso()
        values = payload.model_dump()
        conn.execute(
            """
            INSERT INTO GOALS(
                GOALID, USER_ID, GOAL_NAME, START_DATE, END_DATE,
                GOAL_AMOUNT, MONTHLY_SAVING_T, GOAL_STATUS,
                CREATED_AT, UPDATED_AT
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                goal_id,
                user_id,
                values["goal_name"],
                values["start_date"].isoformat(),
                values["end_date"].isoformat(),
                values["goal_amount"],
                recommendation.recommended_monthly_saving,
                values["goal_status"],
                now,
                now,
            ),
        )
        row = conn.execute("SELECT * FROM GOALS WHERE GOALID = ?", (goal_id,)).fetchone()
    result = _goal_dict(row)
    result["recommendation"] = recommendation.as_dict()
    return result


def update_goal(user_id: int, goal_id: int, payload: GoalPayload) -> dict[str, Any]:
    with transaction(immediate=True) as conn:
        _owned_goal(conn, user_id, goal_id)
        recommendation = calculate_recommendation(
            user_id,
            payload.goal_amount,
            payload.start_date,
            payload.end_date,
            conn=conn,
        )
        if recommendation.missing_prerequisites:
            raise conflict(
                "missing_profiles",
                "Complete income and expense setup before updating this goal.",
                missing_prerequisites=recommendation.missing_prerequisites,
            )
        values = payload.model_dump()
        conn.execute(
            """
            UPDATE GOALS
            SET GOAL_NAME = ?, START_DATE = ?, END_DATE = ?,
                GOAL_AMOUNT = ?, MONTHLY_SAVING_T = ?, GOAL_STATUS = ?,
                UPDATED_AT = ?
            WHERE GOALID = ? AND USER_ID = ?
            """,
            (
                values["goal_name"],
                values["start_date"].isoformat(),
                values["end_date"].isoformat(),
                values["goal_amount"],
                recommendation.recommended_monthly_saving,
                values["goal_status"],
                utc_now_iso(),
                goal_id,
                user_id,
            ),
        )
        row = conn.execute("SELECT * FROM GOALS WHERE GOALID = ?", (goal_id,)).fetchone()
        saved = conn.execute(
            "SELECT COALESCE(SUM(SAVE_MONTH), 0) FROM GOAL_HISTORY WHERE GOALID = ?",
            (goal_id,),
        ).fetchone()[0]
    result = _goal_dict(row, saved)
    result["recommendation"] = recommendation.as_dict()
    return result


def list_history(user_id: int, goal_id: int) -> list[dict[str, Any]]:
    with connection() as conn:
        _owned_goal(conn, user_id, goal_id)
        rows = conn.execute(
            """
            SELECT HISTORY_ID, GOALID, CREATED_AT, SAVE_MONTH
            FROM GOAL_HISTORY
            WHERE GOALID = ?
            ORDER BY DATE(CREATED_AT) ASC, CREATED_AT ASC, HISTORY_ID ASC
            """,
            (goal_id,),
        ).fetchall()
    return [
        {
            "history_id": int(row["HISTORY_ID"]),
            "goal_id": int(row["GOALID"]),
            "saving_date": str(row["CREATED_AT"])[:10],
            "amount_saved": float(row["SAVE_MONTH"]),
        }
        for row in rows
    ]


def record_history(
    user_id: int, goal_id: int, payload: GoalHistoryPayload
) -> dict[str, Any]:
    with transaction(immediate=True) as conn:
        _owned_goal(conn, user_id, goal_id)
        duplicate = conn.execute(
            """
            SELECT HISTORY_ID FROM GOAL_HISTORY
            WHERE GOALID = ? AND DATE(CREATED_AT) = ? AND SAVE_MONTH = ?
            """,
            (goal_id, payload.saving_date.isoformat(), payload.amount_saved),
        ).fetchone()
        if duplicate:
            raise conflict(
                "duplicate_goal_history",
                "This saving entry has already been recorded for the goal and date.",
            )
        history_id = allocate_id(conn, "GOAL_HISTORY")
        conn.execute(
            """
            INSERT INTO GOAL_HISTORY(HISTORY_ID, GOALID, CREATED_AT, SAVE_MONTH)
            VALUES(?, ?, ?, ?)
            """,
            (
                history_id,
                goal_id,
                payload.saving_date.isoformat(),
                payload.amount_saved,
            ),
        )
    return {
        "history_id": history_id,
        "goal_id": goal_id,
        "saving_date": payload.saving_date.isoformat(),
        "amount_saved": payload.amount_saved,
    }
