"""Domain and API models for factual nutrition tracking."""

from datetime import date, datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator


class NutritionValueSource(StrEnum):
    USER_SUPPLIED = "user_supplied"
    AI_ESTIMATE = "ai_estimate"


class NutritionValues(BaseModel):
    calories_kcal: float = Field(default=0, ge=0, allow_inf_nan=False)
    protein_g: float = Field(default=0, ge=0, allow_inf_nan=False)
    carbohydrates_g: float = Field(default=0, ge=0, allow_inf_nan=False)
    fat_g: float = Field(default=0, ge=0, allow_inf_nan=False)
    fiber_g: float = Field(default=0, ge=0, allow_inf_nan=False)


class NutritionBalance(BaseModel):
    calories_kcal: float
    protein_g: float
    carbohydrates_g: float
    fat_g: float
    fiber_g: float


class NutritionTargetCreate(NutritionValues):
    @model_validator(mode="after")
    def target_must_contain_a_value(self) -> "NutritionTargetCreate":
        if not any(self.model_dump().values()):
            raise ValueError("a nutrition target must contain at least one value")
        return self


class NutritionTarget(NutritionValues):
    id: int
    profile_id: int
    effective_from: date


class MealEntryCreate(NutritionValues):
    name: str = Field(min_length=1, max_length=160)
    eaten_at: datetime
    notes: str | None = Field(default=None, max_length=2_000)

    @field_validator("eaten_at")
    @classmethod
    def eaten_at_must_include_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("eaten_at must include a timezone offset")
        return value.astimezone(timezone.utc)


class MealEntry(MealEntryCreate):
    id: int
    profile_id: int
    value_source: NutritionValueSource


class DailyNutritionSummary(BaseModel):
    profile_id: int
    on: date
    target: NutritionTarget | None
    totals: NutritionValues
    remaining: NutritionBalance | None
    meals: list[MealEntry]
