"""Authenticated income and expense profile operations."""

from __future__ import annotations

import sqlite3
from typing import Any

from db import allocate_id, connection, transaction, utc_now_iso
from errors import forbidden, not_found
from schemas import ExpensePayload, IncomePayload


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


def _income_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "profile_id": int(row["PROFILE_ID"]),
        "income_type": row["INCOME_TYPE"],
        "monthly_income": float(row["MONTHLY_INCOME"] or 0),
        "additional_income_type": row["ADDITIONAL_INCOME_TYPE"],
        "additional_monthly_income": float(row["ADDITIONAL_MONTHLY_INCOME"] or 0),
        "dependants": int(row["DEPENDANTS"] or 0),
        "created_at": row["CREATED_AT"],
        "updated_at": row["UPDATED_AT"],
    }


def _expense_dict(row: sqlite3.Row) -> dict[str, Any]:
    values = {column.lower(): float(row[column] or 0) for column in EXPENSE_COLUMNS}
    return {
        "expense_id": int(row["EXPENSE_ID"]),
        **values,
        "created_at": row["CREATED_AT"],
        "total_expenses": round(sum(values.values()), 2),
    }


def list_income(user_id: int) -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM INCOMEPROFILE
            WHERE USER_ID = ?
            ORDER BY CREATED_AT DESC, PROFILE_ID DESC
            """,
            (user_id,),
        ).fetchall()
    return [_income_dict(row) for row in rows]


def latest_income(user_id: int) -> dict[str, Any]:
    profiles = list_income(user_id)
    if not profiles:
        raise not_found("Income profile")
    return profiles[0]


def create_income(user_id: int, payload: IncomePayload) -> dict[str, Any]:
    values = payload.model_dump()
    now = utc_now_iso()
    with transaction(immediate=True) as conn:
        profile_id = allocate_id(conn, "INCOMEPROFILE")
        conn.execute(
            """
            INSERT INTO INCOMEPROFILE(
                PROFILE_ID, USER_ID, INCOME_TYPE, MONTHLY_INCOME,
                ADDITIONAL_INCOME_TYPE, ADDITIONAL_MONTHLY_INCOME,
                DEPENDANTS, CREATED_AT, UPDATED_AT
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile_id,
                user_id,
                values["income_type"],
                values["monthly_income"],
                values["additional_income_type"],
                values["additional_monthly_income"],
                values["dependants"],
                now,
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM INCOMEPROFILE WHERE PROFILE_ID = ?", (profile_id,)
        ).fetchone()
    return _income_dict(row)


def update_income(user_id: int, profile_id: int, payload: IncomePayload) -> dict[str, Any]:
    values = payload.model_dump()
    with transaction(immediate=True) as conn:
        current = conn.execute(
            "SELECT USER_ID FROM INCOMEPROFILE WHERE PROFILE_ID = ?", (profile_id,)
        ).fetchone()
        if current is None:
            raise not_found("Income profile")
        if int(current["USER_ID"]) != user_id:
            raise forbidden()
        conn.execute(
            """
            UPDATE INCOMEPROFILE
            SET INCOME_TYPE = ?, MONTHLY_INCOME = ?,
                ADDITIONAL_INCOME_TYPE = ?, ADDITIONAL_MONTHLY_INCOME = ?,
                DEPENDANTS = ?, UPDATED_AT = ?
            WHERE PROFILE_ID = ? AND USER_ID = ?
            """,
            (
                values["income_type"],
                values["monthly_income"],
                values["additional_income_type"],
                values["additional_monthly_income"],
                values["dependants"],
                utc_now_iso(),
                profile_id,
                user_id,
            ),
        )
        row = conn.execute(
            "SELECT * FROM INCOMEPROFILE WHERE PROFILE_ID = ?", (profile_id,)
        ).fetchone()
    return _income_dict(row)


def list_expenses(user_id: int) -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM EXPENSEPROFILE
            WHERE USER_ID = ?
            ORDER BY CREATED_AT DESC, EXPENSE_ID DESC
            """,
            (user_id,),
        ).fetchall()
    return [_expense_dict(row) for row in rows]


def latest_expenses(user_id: int) -> dict[str, Any]:
    profiles = list_expenses(user_id)
    if not profiles:
        raise not_found("Expense profile")
    return profiles[0]


def create_expenses(user_id: int, payload: ExpensePayload) -> dict[str, Any]:
    values = payload.model_dump()
    now = utc_now_iso()
    with transaction(immediate=True) as conn:
        expense_id = allocate_id(conn, "EXPENSEPROFILE")
        conn.execute(
            """
            INSERT INTO EXPENSEPROFILE(
                EXPENSE_ID, USER_ID, GROCERIES, TRAVEL, MEDFIT, LEP,
                MONTHLY_RENT, M_BILLS, FASHION, ENTERTAINMENT,
                EDUCATION, EMSAVING, MISCELLANEOUS, CREATED_AT
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                expense_id,
                user_id,
                values["groceries"],
                values["travel"],
                values["medfit"],
                values["lep"],
                values["monthly_rent"],
                values["m_bills"],
                values["fashion"],
                values["entertainment"],
                values["education"],
                values["emsaving"],
                values["miscellaneous"],
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM EXPENSEPROFILE WHERE EXPENSE_ID = ?", (expense_id,)
        ).fetchone()
    return _expense_dict(row)


def update_expenses(
    user_id: int, expense_id: int, payload: ExpensePayload
) -> dict[str, Any]:
    values = payload.model_dump()
    with transaction(immediate=True) as conn:
        current = conn.execute(
            "SELECT USER_ID FROM EXPENSEPROFILE WHERE EXPENSE_ID = ?", (expense_id,)
        ).fetchone()
        if current is None:
            raise not_found("Expense profile")
        if int(current["USER_ID"]) != user_id:
            raise forbidden()
        conn.execute(
            """
            UPDATE EXPENSEPROFILE
            SET GROCERIES = ?, TRAVEL = ?, MEDFIT = ?, LEP = ?,
                MONTHLY_RENT = ?, M_BILLS = ?, FASHION = ?,
                ENTERTAINMENT = ?, EDUCATION = ?, EMSAVING = ?,
                MISCELLANEOUS = ?
            WHERE EXPENSE_ID = ? AND USER_ID = ?
            """,
            (
                values["groceries"],
                values["travel"],
                values["medfit"],
                values["lep"],
                values["monthly_rent"],
                values["m_bills"],
                values["fashion"],
                values["entertainment"],
                values["education"],
                values["emsaving"],
                values["miscellaneous"],
                expense_id,
                user_id,
            ),
        )
        row = conn.execute(
            "SELECT * FROM EXPENSEPROFILE WHERE EXPENSE_ID = ?", (expense_id,)
        ).fetchone()
    return _expense_dict(row)
