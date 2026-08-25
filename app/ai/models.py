"""Strict schemas shared by AI adapters and Coachline workflows."""

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AIIntent(StrEnum):
    SHOW_TODAY = "show_today"
    SKIP_SESSION = "skip_session"
    RECORD_RESULT = "record_result"
    CLARIFY = "clarify"
    REPLY = "reply"


class AIInterpretation(BaseModel):
    """The only shape an AI provider may return to Coachline."""

    model_config = ConfigDict(extra="forbid")

    intent: AIIntent
    session_id: int | None
    summary: str | None
    reply_text: str | None = Field(max_length=1200)

    @model_validator(mode="after")
    def required_fields_match_intent(self) -> Self:
        if self.intent is AIIntent.SKIP_SESSION and self.session_id is None:
            raise ValueError("skip_session requires session_id")
        if self.intent is AIIntent.RECORD_RESULT:
            if self.session_id is None or not self.summary:
                raise ValueError("record_result requires session_id and summary")
        if self.intent in {AIIntent.CLARIFY, AIIntent.REPLY} and not self.reply_text:
            raise ValueError("clarify and reply require reply_text")
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
