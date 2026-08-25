"""Models for timezone-aware proactive reminders."""

from datetime import date, datetime, time
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class ReminderJobStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReminderSettingsUpdate(BaseModel):
    enabled: bool = False
    reminder_time: time = time(hour=8)
    quiet_hours_start: time = time(hour=21)
    quiet_hours_end: time = time(hour=7)

    @field_validator(
        "reminder_time", "quiet_hours_start", "quiet_hours_end"
    )
    @classmethod
    def times_must_use_minute_precision(cls, value: time) -> time:
        if value.tzinfo is not None:
            raise ValueError("reminder times must be local times without an offset")
        if value.second or value.microsecond:
            raise ValueError("reminder times must use minute precision")
        return value


class ReminderSettings(ReminderSettingsUpdate):
    profile_id: int


class ReminderCandidate(BaseModel):
    profile_id: int
    session_id: int
    scheduled_for: date
    title: str
    timezone: str
    reminder_time: time
    quiet_hours_start: time
    quiet_hours_end: time


class ReminderJob(BaseModel):
    id: int
    profile_id: int
    session_id: int
    scheduled_at: datetime
    status: ReminderJobStatus
    attempt_count: int = Field(ge=0)


class ReminderRunResult(BaseModel):
    jobs_synced: int = 0
    jobs_cancelled: int = 0
    jobs_recovered: int = 0
    delivered: int = 0
    retrying: int = 0
    failed: int = 0
