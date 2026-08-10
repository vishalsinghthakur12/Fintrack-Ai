"""Pydantic API contracts for FinTrack AI."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class APIModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        use_enum_values=True,
        allow_inf_nan=False,
    )


class Gender(str, Enum):
    MALE = "Male"
    FEMALE = "Female"
    OTHER = "Other"
    PREFER_NOT_TO_SAY = "Prefer not to say"


class IncomeType(str, Enum):
    SALARIED = "SALARIED"
    PROFESSIONAL = "PROFESSIONAL"
    BUSINESS = "BUSINESS"
    OTHERS = "OTHERS"


class AdditionalIncomeType(str, Enum):
    STOCK = "STOCK"
    INVESTMENTS = "INVESTEMENTS"
    BUSINESS = "BUSINESS"
    OTHERS = "OTHERS"


class GoalStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ACHIEVED = "ACHIEVED"
    EXPIRED = "EXPIRED"
    INACTIVE = "INACTIVE"


NonNegativeMoney = Annotated[float, Field(ge=0)]
PositiveMoney = Annotated[float, Field(gt=0)]


def _normalize_email(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip().lower()
    return value


class SignupStartRequest(APIModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    gender: Gender
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: Any) -> Any:
        return _normalize_email(value)

    @model_validator(mode="after")
    def passwords_match(self) -> "SignupStartRequest":
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        return self


class SignupStartResponse(APIModel):
    message: str
    expires_in_seconds: int
    resend_after_seconds: int


class SignupVerifyRequest(APIModel):
    email: EmailStr
    otp: str = Field(pattern=r"^\d{4}$")

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: Any) -> Any:
        return _normalize_email(value)


class LoginRequest(APIModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: Any) -> Any:
        return _normalize_email(value)


class UserResponse(APIModel):
    user_id: int
    name: str
    gender: str
    email: EmailStr
    created_at: str | None = None


class AuthResponse(APIModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: str
    user: UserResponse


class MessageResponse(APIModel):
    message: str


class IncomePayload(APIModel):
    income_type: IncomeType
    monthly_income: NonNegativeMoney
    additional_income_type: AdditionalIncomeType
    additional_monthly_income: NonNegativeMoney
    dependants: int = Field(ge=0, le=19)


class IncomeResponse(IncomePayload):
    profile_id: int
    created_at: str | None
    updated_at: str | None


class ExpensePayload(APIModel):
    groceries: NonNegativeMoney
    travel: NonNegativeMoney
    medfit: NonNegativeMoney
    lep: NonNegativeMoney
    monthly_rent: NonNegativeMoney
    m_bills: NonNegativeMoney
    fashion: NonNegativeMoney
    entertainment: NonNegativeMoney
    education: NonNegativeMoney
    emsaving: NonNegativeMoney
    miscellaneous: NonNegativeMoney


class ExpenseResponse(ExpensePayload):
    expense_id: int
    created_at: str | None
    total_expenses: float


class GoalPayload(APIModel):
    goal_name: str = Field(min_length=1, max_length=100)
    goal_amount: PositiveMoney
    start_date: date
    end_date: date
    goal_status: GoalStatus

    @field_validator("goal_name", mode="before")
    @classmethod
    def trim_goal_name(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def valid_date_range(self) -> "GoalPayload":
        if self.end_date <= self.start_date:
            raise ValueError("End date must be after start date.")
        return self


class RecommendationResponse(APIModel):
    feasible: bool
    recommended_monthly_saving: float
    estimated_duration_months: int | None
    requested_duration_months: int
    message: str
    warnings: list[str] = Field(default_factory=list)
    missing_prerequisites: list[str] = Field(default_factory=list)


class GoalResponse(GoalPayload):
    goal_id: int
    monthly_saving_target: float
    created_at: str | None
    updated_at: str | None
    total_saved: float = 0
    progress_percent: float = 0
    recommendation: RecommendationResponse | None = None


class GoalHistoryPayload(APIModel):
    saving_date: date
    amount_saved: PositiveMoney


class GoalHistoryResponse(GoalHistoryPayload):
    history_id: int
    goal_id: int


class ProfileCompletion(APIModel):
    has_income: bool
    has_expenses: bool
    has_goals: bool


class AnalyticsResponse(APIModel):
    income_profile: IncomeResponse | None
    expense_profile: ExpenseResponse | None
    goals: list[GoalResponse]
    goal_status_counts: dict[str, int]
    total_monthly_income: float
    total_monthly_expenses: float
    free_cash_flow: float
    total_goal_amount: float
    profile_completion: ProfileCompletion
    warnings: list[str]


class HealthResponse(APIModel):
    status: str
    database: str
