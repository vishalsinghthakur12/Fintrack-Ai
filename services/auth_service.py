"""Persistent signup, login, bearer-session, and logout services."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash

from db import allocate_id, connection, transaction, utc_now, utc_now_iso
from errors import AppError, bad_request, conflict, rate_limited, service_unavailable, unauthorized
from schemas import LoginRequest, SignupStartRequest, SignupVerifyRequest
from services.email_service import send_otp_email


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: int
    session_id: str
    name: str
    gender: str
    email: str
    created_at: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "name": self.name,
            "gender": self.gender,
            "email": self.email,
            "created_at": self.created_at,
        }


def _positive_env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def otp_ttl_seconds() -> int:
    return _positive_env_int("FINTRACK_OTP_TTL_SECONDS", 300)


def otp_resend_cooldown_seconds() -> int:
    return _positive_env_int("FINTRACK_OTP_RESEND_COOLDOWN_SECONDS", 60)


def otp_max_attempts() -> int:
    return _positive_env_int("FINTRACK_OTP_MAX_ATTEMPTS", 5)


def session_ttl_seconds() -> int:
    return _positive_env_int("FINTRACK_SESSION_TTL_SECONDS", 86_400)


def _secret_key() -> bytes:
    value = os.getenv("FINTRACK_SECRET_KEY", "")
    if len(value) < 16:
        raise service_unavailable(
            "Authentication is not configured. FINTRACK_SECRET_KEY must contain at least 16 characters."
        )
    return value.encode("utf-8")


def _secret_hash(value: str, purpose: str) -> str:
    return hmac.new(
        _secret_key(), f"{purpose}:{value}".encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _users_for_email(conn: sqlite3.Connection, email: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT USER_ID, USER_NAME, GENDER, EMAIL, PASSWORD_HASH, CREATED_AT
        FROM USER
        WHERE LOWER(TRIM(EMAIL)) = ?
        ORDER BY USER_ID
        """,
        (email.lower(),),
    ).fetchall()


def _assert_new_email(conn: sqlite3.Connection, email: str) -> None:
    matches = _users_for_email(conn, email)
    if len(matches) > 1:
        raise conflict(
            "ambiguous_existing_email",
            "Multiple existing accounts use this email with different capitalization. Contact support before continuing.",
        )
    if matches:
        raise conflict("email_exists", "An account with this email already exists.")


def _new_session(conn: sqlite3.Connection, user_id: int) -> tuple[str, str, str]:
    raw_token = secrets.token_urlsafe(32)
    token_hash = _secret_hash(raw_token, "session")
    session_id = uuid.uuid4().hex
    created_at = utc_now()
    expires_at = created_at + timedelta(seconds=session_ttl_seconds())
    conn.execute(
        """
        INSERT INTO AUTH_SESSION(
            SESSION_ID, USER_ID, TOKEN_HASH, CREATED_AT, EXPIRES_AT, REVOKED_AT
        ) VALUES(?, ?, ?, ?, ?, NULL)
        """,
        (
            session_id,
            user_id,
            token_hash,
            created_at.isoformat(timespec="seconds"),
            expires_at.isoformat(timespec="seconds"),
        ),
    )
    return raw_token, session_id, expires_at.isoformat(timespec="seconds")


def start_signup(payload: SignupStartRequest) -> dict[str, Any]:
    email = str(payload.email).lower()
    now = utc_now()

    with connection() as conn:
        _assert_new_email(conn, email)
        pending = conn.execute(
            "SELECT LAST_SENT_AT, STATUS FROM PENDING_SIGNUP WHERE EMAIL = ?",
            (email,),
        ).fetchone()
        if pending and pending["STATUS"] == "PENDING":
            elapsed = int((now - _parse_timestamp(pending["LAST_SENT_AT"])).total_seconds())
            cooldown = otp_resend_cooldown_seconds()
            if elapsed < cooldown:
                raise rate_limited(
                    "Please wait before requesting another verification code.",
                    retry_after=cooldown - elapsed,
                )

    otp = f"{secrets.randbelow(9000) + 1000:04d}"
    password_hash = generate_password_hash(payload.password)
    otp_hash = _secret_hash(otp, f"otp:{email}")
    expires_at = now + timedelta(seconds=otp_ttl_seconds())

    # Persist the new pending state only after successful delivery.
    send_otp_email(
        recipient_name=payload.name,
        recipient_email=email,
        otp=otp,
    )

    with transaction(immediate=True) as conn:
        _assert_new_email(conn, email)
        conn.execute(
            """
            INSERT INTO PENDING_SIGNUP(
                EMAIL, USER_NAME, GENDER, PASSWORD_HASH, OTP_HASH,
                OTP_CREATION, OTP_EXP, FAILED_ATTEMPTS, LAST_SENT_AT, STATUS
            ) VALUES(?, ?, ?, ?, ?, ?, ?, 0, ?, 'PENDING')
            ON CONFLICT(EMAIL) DO UPDATE SET
                USER_NAME = excluded.USER_NAME,
                GENDER = excluded.GENDER,
                PASSWORD_HASH = excluded.PASSWORD_HASH,
                OTP_HASH = excluded.OTP_HASH,
                OTP_CREATION = excluded.OTP_CREATION,
                OTP_EXP = excluded.OTP_EXP,
                FAILED_ATTEMPTS = 0,
                LAST_SENT_AT = excluded.LAST_SENT_AT,
                STATUS = 'PENDING'
            """,
            (
                email,
                payload.name,
                payload.gender,
                password_hash,
                otp_hash,
                now.isoformat(timespec="seconds"),
                expires_at.isoformat(timespec="seconds"),
                now.isoformat(timespec="seconds"),
            ),
        )

    return {
        "message": "A verification code was sent to your email.",
        "expires_in_seconds": otp_ttl_seconds(),
        "resend_after_seconds": otp_resend_cooldown_seconds(),
    }


def verify_signup(payload: SignupVerifyRequest) -> dict[str, Any]:
    email = str(payload.email).lower()
    failure: AppError | None = None
    response: dict[str, Any] | None = None

    with transaction(immediate=True) as conn:
        pending = conn.execute(
            "SELECT * FROM PENDING_SIGNUP WHERE EMAIL = ?",
            (email,),
        ).fetchone()
        if pending is None:
            failure = bad_request(
                "pending_signup_not_found",
                "No active signup was found. Please start signup again.",
            )
        elif pending["STATUS"] == "LOCKED":
            failure = rate_limited(
                "Too many incorrect attempts. Request a new verification code."
            )
        elif pending["STATUS"] != "PENDING" or utc_now() > _parse_timestamp(pending["OTP_EXP"]):
            conn.execute(
                "UPDATE PENDING_SIGNUP SET STATUS = 'EXPIRED' WHERE EMAIL = ?",
                (email,),
            )
            failure = bad_request(
                "otp_expired",
                "The verification code has expired. Request a new code.",
            )
        elif not hmac.compare_digest(
            pending["OTP_HASH"], _secret_hash(payload.otp, f"otp:{email}")
        ):
            attempts = int(pending["FAILED_ATTEMPTS"]) + 1
            locked = attempts >= otp_max_attempts()
            conn.execute(
                "UPDATE PENDING_SIGNUP SET FAILED_ATTEMPTS = ?, STATUS = ? WHERE EMAIL = ?",
                (attempts, "LOCKED" if locked else "PENDING", email),
            )
            failure = (
                rate_limited(
                    "Too many incorrect attempts. Request a new verification code."
                )
                if locked
                else bad_request(
                    "incorrect_otp",
                    "The verification code is incorrect.",
                    attempts_remaining=otp_max_attempts() - attempts,
                )
            )
        else:
            _assert_new_email(conn, email)
            user_id = allocate_id(conn, "USER")
            otp_id = allocate_id(conn, "VERIFICATION")
            created_at = utc_now_iso()
            conn.execute(
                """
                INSERT INTO USER(
                    USER_ID, USER_NAME, GENDER, EMAIL, PASSWORD_HASH, CREATED_AT
                ) VALUES(?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    pending["USER_NAME"],
                    pending["GENDER"],
                    email,
                    pending["PASSWORD_HASH"],
                    created_at,
                ),
            )
            # Legacy EMAIL_OTP is retained for schema compatibility but no OTP secret is stored.
            conn.execute(
                """
                INSERT INTO VERIFICATION(
                    OTP_ID, USER_ID, EMAIL_OTP, OTP_EXP, OTP_CREATION, OTP_STATUS
                ) VALUES(?, ?, 0, ?, ?, 'VERIFIED')
                """,
                (otp_id, user_id, pending["OTP_EXP"], pending["OTP_CREATION"]),
            )
            conn.execute("DELETE FROM PENDING_SIGNUP WHERE EMAIL = ?", (email,))
            raw_token, _session_id, expires_at = _new_session(conn, user_id)
            response = {
                "access_token": raw_token,
                "token_type": "bearer",
                "expires_at": expires_at,
                "user": {
                    "user_id": user_id,
                    "name": pending["USER_NAME"],
                    "gender": pending["GENDER"],
                    "email": email,
                    "created_at": created_at,
                },
            }

    if failure:
        raise failure
    if response is None:
        raise RuntimeError("Signup verification reached an invalid state")
    return response


def login(payload: LoginRequest) -> dict[str, Any]:
    email = str(payload.email).lower()
    with transaction(immediate=True) as conn:
        matches = _users_for_email(conn, email)
        if len(matches) > 1:
            raise conflict(
                "ambiguous_existing_email",
                "Multiple existing accounts use this email. Contact support before continuing.",
            )
        if not matches:
            raise unauthorized("The email or password is incorrect.")
        user = matches[0]
        try:
            password_valid = check_password_hash(user["PASSWORD_HASH"] or "", payload.password)
        except (TypeError, ValueError):
            password_valid = False
        if not password_valid:
            raise unauthorized("The email or password is incorrect.")

        raw_token, _session_id, expires_at = _new_session(conn, int(user["USER_ID"]))
        return {
            "access_token": raw_token,
            "token_type": "bearer",
            "expires_at": expires_at,
            "user": {
                "user_id": int(user["USER_ID"]),
                "name": user["USER_NAME"] or "FinTrack user",
                "gender": user["GENDER"] or "",
                "email": str(user["EMAIL"]).lower(),
                "created_at": user["CREATED_AT"],
            },
        }


def authenticate_token(raw_token: str | None) -> AuthenticatedUser:
    if not raw_token:
        raise unauthorized()
    token_hash = _secret_hash(raw_token, "session")
    with connection() as conn:
        row = conn.execute(
            """
            SELECT S.SESSION_ID, S.EXPIRES_AT, S.REVOKED_AT,
                   U.USER_ID, U.USER_NAME, U.GENDER, U.EMAIL, U.CREATED_AT
            FROM AUTH_SESSION AS S
            JOIN USER AS U ON U.USER_ID = S.USER_ID
            WHERE S.TOKEN_HASH = ?
            """,
            (token_hash,),
        ).fetchone()

    if row is None or row["REVOKED_AT"] is not None:
        raise unauthorized("The session is invalid or has been revoked.")
    if utc_now() >= _parse_timestamp(row["EXPIRES_AT"]):
        with transaction(immediate=True) as conn:
            conn.execute(
                "UPDATE AUTH_SESSION SET REVOKED_AT = COALESCE(REVOKED_AT, ?) WHERE SESSION_ID = ?",
                (utc_now_iso(), row["SESSION_ID"]),
            )
        raise unauthorized("The session has expired. Please log in again.")

    return AuthenticatedUser(
        user_id=int(row["USER_ID"]),
        session_id=row["SESSION_ID"],
        name=row["USER_NAME"] or "FinTrack user",
        gender=row["GENDER"] or "",
        email=str(row["EMAIL"]).lower(),
        created_at=row["CREATED_AT"],
    )


def logout(user: AuthenticatedUser) -> dict[str, str]:
    with transaction(immediate=True) as conn:
        conn.execute(
            "UPDATE AUTH_SESSION SET REVOKED_AT = COALESCE(REVOKED_AT, ?) WHERE SESSION_ID = ? AND USER_ID = ?",
            (utc_now_iso(), user.session_id, user.user_id),
        )
    return {"message": "You have been logged out."}
