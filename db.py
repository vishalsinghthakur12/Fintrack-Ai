"""SQLite connection, transaction, and additive schema migration helpers."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "fintrackai.db"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat(timespec="seconds")


def get_database_path() -> Path:
    configured = os.getenv("FINTRACK_DB_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return DEFAULT_DATABASE_PATH


def _busy_timeout_ms() -> int:
    try:
        return max(1_000, int(os.getenv("FINTRACK_SQLITE_BUSY_TIMEOUT_MS", "5000")))
    except ValueError:
        return 5_000


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    """Open a configured SQLite connection and always close it."""

    database_path = get_database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        database_path,
        timeout=_busy_timeout_ms() / 1_000,
        isolation_level=None,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {_busy_timeout_ms()}")
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction(*, immediate: bool = False) -> Iterator[sqlite3.Connection]:
    """Run a transaction, using an immediate write lock when allocating legacy IDs."""

    with connection() as conn:
        conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()


_ID_COLUMNS = {
    "USER": "USER_ID",
    "VERIFICATION": "OTP_ID",
    "INCOMEPROFILE": "PROFILE_ID",
    "EXPENSEPROFILE": "EXPENSE_ID",
    "GOALS": "GOALID",
    "GOAL_HISTORY": "HISTORY_ID",
}


def allocate_id(conn: sqlite3.Connection, table: str) -> int:
    """Allocate an ID while the caller holds a BEGIN IMMEDIATE transaction."""

    column = _ID_COLUMNS.get(table)
    if column is None:
        raise ValueError("Unsupported ID allocation table")
    row = conn.execute(
        f'SELECT COALESCE(MAX("{column}"), 0) + 1 AS NEXT_ID FROM "{table}"'
    ).fetchone()
    return int(row["NEXT_ID"])


def initialize_database() -> None:
    """Create missing base/support objects without altering or deleting existing rows."""

    schema_statements = (
        """
        CREATE TABLE IF NOT EXISTS USER(
            USER_ID INT PRIMARY KEY,
            USER_NAME VARCHAR(40),
            GENDER VARCHAR(20),
            EMAIL VARCHAR(100),
            PASSWORD_HASH TEXT,
            CREATED_AT DATETIME
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS VERIFICATION(
            OTP_ID INT PRIMARY KEY,
            USER_ID INT,
            EMAIL_OTP INT,
            OTP_EXP DATETIME,
            OTP_CREATION DATETIME,
            OTP_STATUS VARCHAR(30) CHECK(OTP_STATUS IN('VERIFIED','NOT VERIFIED')),
            FOREIGN KEY(USER_ID) REFERENCES USER(USER_ID)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS INCOMEPROFILE(
            PROFILE_ID INT PRIMARY KEY,
            USER_ID INT,
            INCOME_TYPE VARCHAR(40) CHECK(INCOME_TYPE IN('SALARIED','PROFESSIONAL','BUSINESS','OTHERS')),
            MONTHLY_INCOME FLOAT,
            ADDITIONAL_INCOME_TYPE VARCHAR(50) CHECK(ADDITIONAL_INCOME_TYPE IN('STOCK','INVESTEMENTS','BUSINESS','OTHERS')),
            ADDITIONAL_MONTHLY_INCOME FLOAT,
            DEPENDANTS INT CHECK(DEPENDANTS<20),
            CREATED_AT DATETIME,
            UPDATED_AT DATETIME,
            FOREIGN KEY(USER_ID) REFERENCES USER(USER_ID)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS EXPENSEPROFILE(
            EXPENSE_ID INT PRIMARY KEY,
            USER_ID INT,
            GROCERIES FLOAT,
            TRAVEL FLOAT,
            MEDFIT FLOAT,
            LEP FLOAT,
            MONTHLY_RENT FLOAT,
            M_BILLS FLOAT,
            FASHION FLOAT,
            ENTERTAINMENT FLOAT,
            EDUCATION FLOAT,
            EMSAVING FLOAT,
            MISCELLANEOUS FLOAT,
            CREATED_AT DATETIME,
            FOREIGN KEY(USER_ID) REFERENCES USER(USER_ID)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS GOALS(
            GOALID INT PRIMARY KEY,
            USER_ID INT,
            GOAL_NAME VARCHAR(100),
            START_DATE DATETIME,
            END_DATE DATETIME,
            GOAL_AMOUNT FLOAT,
            MONTHLY_SAVING_T FLOAT,
            GOAL_STATUS VARCHAR(50) CHECK(GOAL_STATUS IN('ACTIVE','PAUSED','ACHIEVED','EXPIRED','INACTIVE')),
            CREATED_AT DATETIME,
            UPDATED_AT DATETIME,
            FOREIGN KEY(USER_ID) REFERENCES USER(USER_ID)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS GOAL_HISTORY(
            HISTORY_ID INT PRIMARY KEY,
            GOALID INT,
            CREATED_AT DATETIME,
            SAVE_MONTH FLOAT,
            FOREIGN KEY(GOALID) REFERENCES GOALS(GOALID)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS PENDING_SIGNUP(
            EMAIL TEXT PRIMARY KEY COLLATE NOCASE,
            USER_NAME TEXT NOT NULL,
            GENDER TEXT NOT NULL,
            PASSWORD_HASH TEXT NOT NULL,
            OTP_HASH TEXT NOT NULL,
            OTP_CREATION DATETIME NOT NULL,
            OTP_EXP DATETIME NOT NULL,
            FAILED_ATTEMPTS INTEGER NOT NULL DEFAULT 0,
            LAST_SENT_AT DATETIME NOT NULL,
            STATUS TEXT NOT NULL DEFAULT 'PENDING'
                CHECK(STATUS IN('PENDING','LOCKED','EXPIRED'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS AUTH_SESSION(
            SESSION_ID TEXT PRIMARY KEY,
            USER_ID INT NOT NULL,
            TOKEN_HASH TEXT NOT NULL UNIQUE,
            CREATED_AT DATETIME NOT NULL,
            EXPIRES_AT DATETIME NOT NULL,
            REVOKED_AT DATETIME,
            FOREIGN KEY(USER_ID) REFERENCES USER(USER_ID)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS SCHEMA_MIGRATION(
            MIGRATION_ID TEXT PRIMARY KEY,
            APPLIED_AT DATETIME NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS IDX_USER_EMAIL_NOCASE ON USER(EMAIL COLLATE NOCASE)",
        "CREATE INDEX IF NOT EXISTS IDX_INCOME_USER_CREATED ON INCOMEPROFILE(USER_ID, CREATED_AT DESC)",
        "CREATE INDEX IF NOT EXISTS IDX_EXPENSE_USER_CREATED ON EXPENSEPROFILE(USER_ID, CREATED_AT DESC)",
        "CREATE INDEX IF NOT EXISTS IDX_GOALS_USER_CREATED ON GOALS(USER_ID, CREATED_AT DESC)",
        "CREATE INDEX IF NOT EXISTS IDX_HISTORY_GOAL_CREATED ON GOAL_HISTORY(GOALID, CREATED_AT ASC)",
        "CREATE INDEX IF NOT EXISTS IDX_AUTH_USER ON AUTH_SESSION(USER_ID)",
        "CREATE INDEX IF NOT EXISTS IDX_AUTH_EXPIRY ON AUTH_SESSION(EXPIRES_AT)",
    )

    with transaction(immediate=True) as conn:
        for statement in schema_statements:
            conn.execute(statement)
        conn.execute(
            "INSERT OR IGNORE INTO SCHEMA_MIGRATION(MIGRATION_ID, APPLIED_AT) VALUES(?, ?)",
            ("2026-08-fastapi-auth-support", utc_now_iso()),
        )


def database_health() -> bool:
    try:
        with connection() as conn:
            return conn.execute("SELECT 1").fetchone()[0] == 1
    except sqlite3.Error:
        return False
