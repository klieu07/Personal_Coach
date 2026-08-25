"""API and domain schemas for Coachline's training data."""

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator


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

    @field_validator("timezone")
    @classmethod
    def timezone_must_exist(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return value


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


class LiftingExercise(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    sets: int = Field(ge=1, le=20)
    reps: int = Field(ge=1, le=100)
    target_weight_kg: float | None = Field(default=None, ge=0, le=2000)
    rest_seconds: int | None = Field(default=None, ge=0, le=3600)


class RunningSegmentKind(StrEnum):
    WARMUP = "warmup"
    WORK = "work"
    RECOVERY = "recovery"
    STEADY = "steady"
    COOLDOWN = "cooldown"


class RunningSegment(BaseModel):
    kind: RunningSegmentKind
    distance_m: int | None = Field(default=None, ge=1, le=200_000)
    duration_seconds: int | None = Field(default=None, ge=1, le=86_400)
    target_pace_seconds_per_km: int | None = Field(
        default=None, ge=60, le=3600
    )

    @model_validator(mode="after")
    def segment_needs_distance_or_duration(self) -> Self:
        if self.distance_m is None and self.duration_seconds is None:
            raise ValueError("a running segment needs a distance or duration")
        return self


class LiftingPrescription(BaseModel):
    discipline: Literal[Discipline.LIFTING] = Discipline.LIFTING
    exercises: list[LiftingExercise] = Field(min_length=1, max_length=30)


class RunningPrescription(BaseModel):
    discipline: Literal[Discipline.RUNNING] = Discipline.RUNNING
    segments: list[RunningSegment] = Field(min_length=1, max_length=50)


Prescription = Annotated[
    LiftingPrescription | RunningPrescription,
    Field(discriminator="discipline"),
]


class LiftingSetResult(BaseModel):
    exercise_name: str = Field(min_length=1, max_length=120)
    set_number: int = Field(ge=1, le=100)
    reps: int = Field(ge=0, le=100)
    weight_kg: float | None = Field(default=None, ge=0, le=2000)


class RunningResultMetrics(BaseModel):
    distance_m: int = Field(ge=1, le=200_000)
    duration_seconds: int = Field(ge=1, le=86_400)
    average_heart_rate: int | None = Field(default=None, ge=20, le=260)


class WorkoutResultCreate(BaseModel):
    summary: str = Field(min_length=1, max_length=4000)
    completed_at: datetime | None = None
    lifting_sets: list[LiftingSetResult] = Field(default_factory=list, max_length=200)
    running_metrics: RunningResultMetrics | None = None

    @model_validator(mode="after")
    def lifting_set_numbers_must_be_unique(self) -> Self:
        identities = [
            (item.exercise_name, item.set_number) for item in self.lifting_sets
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("lifting set numbers must be unique per exercise")
        return self


class WorkoutResult(BaseModel):
    id: int
    session_id: int
    summary: str
    completed_at: datetime
    lifting_sets: list[LiftingSetResult] = Field(default_factory=list)
    running_metrics: RunningResultMetrics | None = None


class SessionPlan(BaseModel):
    session: TrainingSession
    prescription: Prescription | None


class ProgressionCreate(BaseModel):
    scheduled_for: date
    lifting_weight_increment_kg: float = Field(default=2.5, ge=0, le=100)
    running_increase_percent: float = Field(default=10, ge=0, le=100)
