"""API and domain schemas for Coachline's training data."""

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Discipline(StrEnum):
    """Kinds of training programs supported by the initial domain model."""

    LIFTING = "lifting"
    RUNNING = "running"


class SessionStatus(StrEnum):
    """Lifecycle states for a scheduled training session."""

    PLANNED = "planned"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class ProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    timezone: str = Field(default="UTC", min_length=1, max_length=100)


class Profile(ProfileCreate):
    id: int


class ProgramCreate(BaseModel):
    profile_id: int
    name: str = Field(min_length=1, max_length=120)
    discipline: Discipline


class Program(ProgramCreate):
    id: int
    active: bool


class SessionCreate(BaseModel):
    program_id: int
    scheduled_for: date
    title: str = Field(min_length=1, max_length=160)
    notes: str | None = Field(default=None, max_length=2000)


class TrainingSession(SessionCreate):
    id: int
    status: SessionStatus


class SessionStatusUpdate(BaseModel):
    status: SessionStatus


class WorkoutResultCreate(BaseModel):
    summary: str = Field(min_length=1, max_length=4000)
    completed_at: datetime | None = None


class WorkoutResult(BaseModel):
    id: int
    session_id: int
    summary: str
    completed_at: datetime
