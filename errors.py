"""Application-safe exceptions shared by API and service layers."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def bad_request(code: str, message: str, **details: Any) -> AppError:
    return AppError(400, code, message, details=details)


def unauthorized(message: str = "Authentication is required.") -> AppError:
    return AppError(401, "unauthorized", message)


def forbidden(message: str = "You do not have access to this resource.") -> AppError:
    return AppError(403, "forbidden", message)


def not_found(resource: str) -> AppError:
    return AppError(404, "not_found", f"{resource} was not found.")


def conflict(code: str, message: str, **details: Any) -> AppError:
    return AppError(409, code, message, details=details)


def rate_limited(message: str, *, retry_after: int | None = None) -> AppError:
    details = {"retry_after_seconds": retry_after} if retry_after is not None else {}
    return AppError(429, "rate_limited", message, details=details)


def service_unavailable(message: str) -> AppError:
    return AppError(503, "service_unavailable", message)
