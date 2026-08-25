"""Strict schemas shared by AI adapters and Coachline workflows."""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class AIIntent(StrEnum):
    SHOW_TODAY = "show_today"
    SHOW_NUTRITION = "show_nutrition"
    SKIP_SESSION = "skip_session"
    RECORD_RESULT = "record_result"
    LOG_MEAL_ESTIMATE = "log_meal_estimate"
    CLARIFY = "clarify"
    REPLY = "reply"


class AIMealEstimate(BaseModel):
    """Nutrition values proposed by AI and never treated as user facts."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    eaten_at: datetime
    calories_kcal: float = Field(ge=0, le=20_000, allow_inf_nan=False)
    protein_g: float = Field(ge=0, le=2_000, allow_inf_nan=False)
    carbohydrates_g: float = Field(ge=0, le=3_000, allow_inf_nan=False)
    fat_g: float = Field(ge=0, le=1_000, allow_inf_nan=False)
    fiber_g: float = Field(ge=0, le=500, allow_inf_nan=False)

    @field_validator("eaten_at")
    @classmethod
    def eaten_at_must_include_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("eaten_at must include a timezone offset")
        return value.astimezone(timezone.utc)


class AIInterpretation(BaseModel):
    """The only shape an AI provider may return to Coachline."""

    model_config = ConfigDict(extra="forbid")

    intent: AIIntent
    session_id: int | None
    summary: str | None
    reply_text: str | None = Field(max_length=1200)
    meal: AIMealEstimate | None

    @model_validator(mode="after")
    def required_fields_match_intent(self) -> Self:
        if self.intent is AIIntent.SKIP_SESSION and self.session_id is None:
            raise ValueError("skip_session requires session_id")
        if self.intent is AIIntent.RECORD_RESULT:
            if self.session_id is None or not self.summary:
                raise ValueError("record_result requires session_id and summary")
        if self.intent in {AIIntent.CLARIFY, AIIntent.REPLY} and not self.reply_text:
            raise ValueError("clarify and reply require reply_text")
        if self.intent is AIIntent.LOG_MEAL_ESTIMATE and self.meal is None:
            raise ValueError("log_meal_estimate requires meal")
        if self.intent is not AIIntent.LOG_MEAL_ESTIMATE and self.meal is not None:
            raise ValueError("meal is only allowed for log_meal_estimate")
        return self


class AIInterpretationResult(BaseModel):
    interpretation: AIInterpretation
    response_id: str
    model: str


class PendingAction(BaseModel):
    contact_id: int
    interpretation: AIInterpretation
    confirmation_prompt: str
    expires_at: datetime
