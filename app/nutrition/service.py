"""Application workflows for nutrition targets and meal logging."""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.nutrition.models import (
    DailyNutritionSummary,
    MealEntry,
    MealEntryCreate,
    NutritionBalance,
    NutritionTarget,
    NutritionTargetCreate,
    NutritionValues,
    NutritionValueSource,
)
from app.nutrition.repository import NutritionRepository
from app.services import CoachlineService


class NutritionService:
    """Keep nutrition calculations deterministic and profile-scoped."""

    def __init__(
        self,
        coachline: CoachlineService,
        repository: NutritionRepository,
    ) -> None:
        self.coachline = coachline
        self.repository = repository

    def set_target(
        self,
        profile_id: int,
        effective_from: date,
        payload: NutritionTargetCreate,
    ) -> NutritionTarget:
        self.coachline.get_profile(profile_id)
        return self.repository.set_target(profile_id, effective_from, payload)

    def get_target(
        self, profile_id: int, on_date: date | None = None
    ) -> NutritionTarget | None:
        profile = self.coachline.get_profile(profile_id)
        target_date = on_date or datetime.now(ZoneInfo(profile.timezone)).date()
        return self.repository.get_target(profile_id, target_date)

    def create_meal(
        self, profile_id: int, payload: MealEntryCreate
    ) -> MealEntry:
        self.coachline.get_profile(profile_id)
        return self.repository.create_meal(
            profile_id, payload, NutritionValueSource.USER_SUPPLIED
        )

    def create_estimated_meal(
        self, profile_id: int, payload: MealEntryCreate
    ) -> MealEntry:
        self.coachline.get_profile(profile_id)
        return self.repository.create_meal(
            profile_id, payload, NutritionValueSource.AI_ESTIMATE
        )

    def get_meal(self, profile_id: int, meal_id: int) -> MealEntry:
        self.coachline.get_profile(profile_id)
        return self.repository.get_meal(profile_id, meal_id)

    def replace_meal(
        self,
        profile_id: int,
        meal_id: int,
        payload: MealEntryCreate,
    ) -> MealEntry:
        self.coachline.get_profile(profile_id)
        return self.repository.replace_meal(
            profile_id,
            meal_id,
            payload,
            NutritionValueSource.USER_SUPPLIED,
        )

    def list_meals(
        self, profile_id: int, on_date: date | None = None
    ) -> list[MealEntry]:
        profile = self.coachline.get_profile(profile_id)
        target_date = on_date or datetime.now(ZoneInfo(profile.timezone)).date()
        start, end = self._utc_day_bounds(target_date, profile.timezone)
        return self.repository.list_meals(profile_id, start, end)

    def daily_summary(
        self, profile_id: int, on_date: date | None = None
    ) -> DailyNutritionSummary:
        profile = self.coachline.get_profile(profile_id)
        target_date = on_date or datetime.now(ZoneInfo(profile.timezone)).date()
        start, end = self._utc_day_bounds(target_date, profile.timezone)
        meals = self.repository.list_meals(profile_id, start, end)
        target = self.repository.get_target(profile_id, target_date)
        totals = self._sum_meals(meals)
        remaining = self._remaining(target, totals) if target else None
        return DailyNutritionSummary(
            profile_id=profile_id,
            on=target_date,
            target=target,
            totals=totals,
            remaining=remaining,
            meals=meals,
        )

    @staticmethod
    def _utc_day_bounds(on_date: date, timezone_name: str) -> tuple[datetime, datetime]:
        zone = ZoneInfo(timezone_name)
        local_start = datetime.combine(on_date, time.min, tzinfo=zone)
        local_end = datetime.combine(
            on_date + timedelta(days=1), time.min, tzinfo=zone
        )
        return (
            local_start.astimezone(timezone.utc),
            local_end.astimezone(timezone.utc),
        )

    @classmethod
    def _sum_meals(cls, meals: list[MealEntry]) -> NutritionValues:
        return NutritionValues(
            calories_kcal=cls._rounded_sum(meals, "calories_kcal"),
            protein_g=cls._rounded_sum(meals, "protein_g"),
            carbohydrates_g=cls._rounded_sum(meals, "carbohydrates_g"),
            fat_g=cls._rounded_sum(meals, "fat_g"),
            fiber_g=cls._rounded_sum(meals, "fiber_g"),
        )

    @staticmethod
    def _rounded_sum(meals: list[MealEntry], field: str) -> float:
        return round(sum(float(getattr(meal, field)) for meal in meals), 2)

    @staticmethod
    def _remaining(
        target: NutritionTarget, totals: NutritionValues
    ) -> NutritionBalance:
        return NutritionBalance(
            calories_kcal=round(target.calories_kcal - totals.calories_kcal, 2),
            protein_g=round(target.protein_g - totals.protein_g, 2),
            carbohydrates_g=round(
                target.carbohydrates_g - totals.carbohydrates_g, 2
            ),
            fat_g=round(target.fat_g - totals.fat_g, 2),
            fiber_g=round(target.fiber_g - totals.fiber_g, 2),
        )
