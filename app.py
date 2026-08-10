"""FinTrack AI FastAPI application."""

from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request, Security, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles

from db import database_health, initialize_database
from errors import AppError
from schemas import (
    AnalyticsResponse,
    AuthResponse,
    ExpensePayload,
    ExpenseResponse,
    GoalHistoryPayload,
    GoalHistoryResponse,
    GoalPayload,
    GoalResponse,
    HealthResponse,
    IncomePayload,
    IncomeResponse,
    LoginRequest,
    MessageResponse,
    RecommendationResponse,
    SignupStartRequest,
    SignupStartResponse,
    SignupVerifyRequest,
    UserResponse,
)
from services import analytics_service, auth_service, goal_service, profile_service
from services.auth_service import AuthenticatedUser


FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    initialize_database()
    yield


def create_app() -> FastAPI:
    api = FastAPI(
        title="FinTrack AI API",
        version="2.0.0",
        description="Authenticated financial-profile, goal, and analytics API.",
        lifespan=lifespan,
    )
    bearer = HTTPBearer(auto_error=False)

    @api.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @api.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        safe_errors = [
            {
                "location": [str(part) for part in error.get("loc", ())],
                "message": error.get("msg", "Invalid value"),
                "type": error.get("type", "validation_error"),
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Please correct the highlighted input values.",
                    "details": {"fields": safe_errors},
                }
            },
        )

    @api.exception_handler(sqlite3.IntegrityError)
    async def integrity_error_handler(
        _request: Request, _exc: sqlite3.IntegrityError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "data_conflict",
                    "message": "The requested change conflicts with existing data.",
                    "details": {},
                }
            },
        )

    @api.exception_handler(Exception)
    async def unexpected_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "An unexpected server error occurred.",
                    "details": {},
                }
            },
        )

    def current_user(
        credentials: HTTPAuthorizationCredentials | None = Security(bearer),
    ) -> AuthenticatedUser:
        token = credentials.credentials if credentials else None
        return auth_service.authenticate_token(token)

    @api.get("/api/health", response_model=HealthResponse, tags=["system"])
    def health() -> dict[str, str]:
        healthy = database_health()
        return {
            "status": "ok" if healthy else "degraded",
            "database": "connected" if healthy else "unavailable",
        }

    @api.post(
        "/api/auth/signup/start",
        response_model=SignupStartResponse,
        status_code=status.HTTP_200_OK,
        tags=["authentication"],
    )
    def signup_start(payload: SignupStartRequest):
        return auth_service.start_signup(payload)

    @api.post(
        "/api/auth/signup/verify",
        response_model=AuthResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["authentication"],
    )
    def signup_verify(payload: SignupVerifyRequest):
        return auth_service.verify_signup(payload)

    @api.post(
        "/api/auth/login",
        response_model=AuthResponse,
        tags=["authentication"],
    )
    def login(payload: LoginRequest):
        return auth_service.login(payload)

    @api.get("/api/auth/me", response_model=UserResponse, tags=["authentication"])
    def me(user: AuthenticatedUser = Depends(current_user)):
        return user.as_dict()

    @api.post(
        "/api/auth/logout", response_model=MessageResponse, tags=["authentication"]
    )
    def logout(user: AuthenticatedUser = Depends(current_user)):
        return auth_service.logout(user)

    @api.get("/api/income", response_model=list[IncomeResponse], tags=["income"])
    def income_list(user: AuthenticatedUser = Depends(current_user)):
        return profile_service.list_income(user.user_id)

    @api.get(
        "/api/income/latest", response_model=IncomeResponse, tags=["income"]
    )
    def income_latest(user: AuthenticatedUser = Depends(current_user)):
        return profile_service.latest_income(user.user_id)

    @api.post(
        "/api/income",
        response_model=IncomeResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["income"],
    )
    def income_create(
        payload: IncomePayload, user: AuthenticatedUser = Depends(current_user)
    ):
        return profile_service.create_income(user.user_id, payload)

    @api.put(
        "/api/income/{profile_id}", response_model=IncomeResponse, tags=["income"]
    )
    def income_update(
        profile_id: int,
        payload: IncomePayload,
        user: AuthenticatedUser = Depends(current_user),
    ):
        return profile_service.update_income(user.user_id, profile_id, payload)

    @api.get(
        "/api/expenses", response_model=list[ExpenseResponse], tags=["expenses"]
    )
    def expenses_list(user: AuthenticatedUser = Depends(current_user)):
        return profile_service.list_expenses(user.user_id)

    @api.get(
        "/api/expenses/latest", response_model=ExpenseResponse, tags=["expenses"]
    )
    def expenses_latest(user: AuthenticatedUser = Depends(current_user)):
        return profile_service.latest_expenses(user.user_id)

    @api.post(
        "/api/expenses",
        response_model=ExpenseResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["expenses"],
    )
    def expenses_create(
        payload: ExpensePayload, user: AuthenticatedUser = Depends(current_user)
    ):
        return profile_service.create_expenses(user.user_id, payload)

    @api.put(
        "/api/expenses/{expense_id}",
        response_model=ExpenseResponse,
        tags=["expenses"],
    )
    def expenses_update(
        expense_id: int,
        payload: ExpensePayload,
        user: AuthenticatedUser = Depends(current_user),
    ):
        return profile_service.update_expenses(user.user_id, expense_id, payload)

    @api.get("/api/goals", response_model=list[GoalResponse], tags=["goals"])
    def goals_list(user: AuthenticatedUser = Depends(current_user)):
        return goal_service.list_goals(user.user_id)

    @api.post(
        "/api/goals/recommendation",
        response_model=RecommendationResponse,
        tags=["goals"],
    )
    def goals_recommendation(
        payload: GoalPayload, user: AuthenticatedUser = Depends(current_user)
    ):
        return goal_service.preview_recommendation(user.user_id, payload)

    @api.get("/api/goals/{goal_id}", response_model=GoalResponse, tags=["goals"])
    def goals_get(goal_id: int, user: AuthenticatedUser = Depends(current_user)):
        return goal_service.get_goal(user.user_id, goal_id)

    @api.post(
        "/api/goals",
        response_model=GoalResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["goals"],
    )
    def goals_create(
        payload: GoalPayload, user: AuthenticatedUser = Depends(current_user)
    ):
        return goal_service.create_goal(user.user_id, payload)

    @api.put("/api/goals/{goal_id}", response_model=GoalResponse, tags=["goals"])
    def goals_update(
        goal_id: int,
        payload: GoalPayload,
        user: AuthenticatedUser = Depends(current_user),
    ):
        return goal_service.update_goal(user.user_id, goal_id, payload)

    @api.get(
        "/api/goals/{goal_id}/history",
        response_model=list[GoalHistoryResponse],
        tags=["goals"],
    )
    def goals_history_list(
        goal_id: int, user: AuthenticatedUser = Depends(current_user)
    ):
        return goal_service.list_history(user.user_id, goal_id)

    @api.post(
        "/api/goals/{goal_id}/history",
        response_model=GoalHistoryResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["goals"],
    )
    def goals_history_create(
        goal_id: int,
        payload: GoalHistoryPayload,
        user: AuthenticatedUser = Depends(current_user),
    ):
        return goal_service.record_history(user.user_id, goal_id, payload)

    @api.get(
        "/api/analytics/summary",
        response_model=AnalyticsResponse,
        tags=["analytics"],
    )
    def analytics(user: AuthenticatedUser = Depends(current_user)):
        return analytics_service.analytics_summary(user.user_id)

    @api.get("/", include_in_schema=False, response_class=FileResponse)
    def frontend():
        return FileResponse(FRONTEND_DIR / "index.html")

    api.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    return api


app = create_app()
