"""Persistence boundary for Coachline's nutrition domain."""

from datetime import date, datetime
from typing import Protocol

from app.database import Database
from app.nutrition.models import (
    MealEntry,
    MealEntryCreate,
    NutritionTarget,
    NutritionTargetCreate,
    NutritionValueSource,
)
from app.repository import NotFoundError


class NutritionRepository(Protocol):
    def set_target(
        self,
        profile_id: int,
        effective_from: date,
        payload: NutritionTargetCreate,
    ) -> NutritionTarget: ...

    def get_target(
        self, profile_id: int, on_date: date
    ) -> NutritionTarget | None: ...

    def create_meal(
        self,
        profile_id: int,
        payload: MealEntryCreate,
        source: NutritionValueSource,
    ) -> MealEntry: ...

    def get_meal(self, profile_id: int, meal_id: int) -> MealEntry: ...

    def list_meals(
        self, profile_id: int, start: datetime, end: datetime
    ) -> list[MealEntry]: ...

    def replace_meal(
        self,
        profile_id: int,
        meal_id: int,
        payload: MealEntryCreate,
        source: NutritionValueSource,
    ) -> MealEntry: ...


class SQLiteNutritionRepository:
    """Store targets and meal entries in SQLite."""

    _nutrition_columns = (
        "calories_kcal, protein_g, carbohydrates_g, fat_g, fiber_g"
    )

    def __init__(self, database: Database) -> None:
        self.database = database

    def set_target(
        self,
        profile_id: int,
        effective_from: date,
        payload: NutritionTargetCreate,
    ) -> NutritionTarget:
        values = self._nutrition_values(payload)
        with self.database.session() as connection:
            connection.execute(
                """
                INSERT INTO nutrition_targets
                    (profile_id, effective_from, calories_kcal, protein_g,
                     carbohydrates_g, fat_g, fiber_g, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(profile_id, effective_from) DO UPDATE SET
                    calories_kcal = excluded.calories_kcal,
                    protein_g = excluded.protein_g,
                    carbohydrates_g = excluded.carbohydrates_g,
                    fat_g = excluded.fat_g,
                    fiber_g = excluded.fiber_g,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (profile_id, effective_from.isoformat(), *values),
            )
            row = connection.execute(
                f"""
                SELECT id, profile_id, effective_from,
                       {self._nutrition_columns}
                FROM nutrition_targets
                WHERE profile_id = ? AND effective_from = ?
                """,
                (profile_id, effective_from.isoformat()),
            ).fetchone()
        return NutritionTarget(**dict(row))

    def get_target(
        self, profile_id: int, on_date: date
    ) -> NutritionTarget | None:
        with self.database.session() as connection:
            row = connection.execute(
                f"""
                SELECT id, profile_id, effective_from,
                       {self._nutrition_columns}
                FROM nutrition_targets
                WHERE profile_id = ? AND effective_from <= ?
                ORDER BY effective_from DESC, id DESC
                LIMIT 1
                """,
                (profile_id, on_date.isoformat()),
            ).fetchone()
        return NutritionTarget(**dict(row)) if row is not None else None

    def create_meal(
        self,
        profile_id: int,
        payload: MealEntryCreate,
        source: NutritionValueSource,
    ) -> MealEntry:
        values = self._nutrition_values(payload)
        with self.database.session() as connection:
            cursor = connection.execute(
                """
                INSERT INTO meal_entries
                    (profile_id, name, eaten_at, calories_kcal, protein_g,
                     carbohydrates_g, fat_g, fiber_g, notes, value_source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile_id,
                    payload.name,
                    payload.eaten_at.isoformat(),
                    *values,
                    payload.notes,
                    source.value,
                ),
            )
        return MealEntry(
            id=cursor.lastrowid,
            profile_id=profile_id,
            value_source=source,
            **payload.model_dump(),
        )

    def get_meal(self, profile_id: int, meal_id: int) -> MealEntry:
        with self.database.session() as connection:
            row = connection.execute(
                f"""
                SELECT id, profile_id, name, eaten_at,
                       {self._nutrition_columns}, notes, value_source
                FROM meal_entries
                WHERE id = ? AND profile_id = ?
                """,
                (meal_id, profile_id),
            ).fetchone()
        if row is None:
            raise NotFoundError(f"Meal {meal_id} was not found")
        return MealEntry(**dict(row))

    def list_meals(
        self, profile_id: int, start: datetime, end: datetime
    ) -> list[MealEntry]:
        with self.database.session() as connection:
            rows = connection.execute(
                f"""
                SELECT id, profile_id, name, eaten_at,
                       {self._nutrition_columns}, notes, value_source
                FROM meal_entries
                WHERE profile_id = ? AND eaten_at >= ? AND eaten_at < ?
                ORDER BY eaten_at, id
                """,
                (profile_id, start.isoformat(), end.isoformat()),
            ).fetchall()
        return [MealEntry(**dict(row)) for row in rows]

    def replace_meal(
        self,
        profile_id: int,
        meal_id: int,
        payload: MealEntryCreate,
        source: NutritionValueSource,
    ) -> MealEntry:
        self.get_meal(profile_id, meal_id)
        values = self._nutrition_values(payload)
        with self.database.session() as connection:
            connection.execute(
                """
                UPDATE meal_entries
                SET name = ?, eaten_at = ?, calories_kcal = ?, protein_g = ?,
                    carbohydrates_g = ?, fat_g = ?, fiber_g = ?, notes = ?,
                    value_source = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND profile_id = ?
                """,
                (
                    payload.name,
                    payload.eaten_at.isoformat(),
                    *values,
                    payload.notes,
                    source.value,
                    meal_id,
                    profile_id,
                ),
            )
        return MealEntry(
            id=meal_id,
            profile_id=profile_id,
            value_source=source,
            **payload.model_dump(),
        )

    @staticmethod
    def _nutrition_values(
        payload: NutritionTargetCreate | MealEntryCreate,
    ) -> tuple[float, float, float, float, float]:
        return (
            payload.calories_kcal,
            payload.protein_g,
            payload.carbohydrates_g,
            payload.fat_g,
            payload.fiber_g,
        )
