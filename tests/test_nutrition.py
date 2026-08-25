from pathlib import Path

from fastapi.testclient import TestClient

from app.database import Database
from app.main import create_app


def make_client(database_path: Path) -> TestClient:
    return TestClient(create_app(database_path))


def create_profile(
    client: TestClient,
    *,
    name: str = "Nutrition Test",
    timezone: str = "America/Los_Angeles",
) -> int:
    response = client.post(
        "/profiles",
        json={"name": name, "timezone": timezone},
    )
    assert response.status_code == 201
    return response.json()["id"]


def meal_payload(
    *,
    name: str,
    eaten_at: str,
    calories_kcal: float,
    protein_g: float,
    carbohydrates_g: float,
    fat_g: float,
    fiber_g: float = 0,
) -> dict[str, object]:
    return {
        "name": name,
        "eaten_at": eaten_at,
        "calories_kcal": calories_kcal,
        "protein_g": protein_g,
        "carbohydrates_g": carbohydrates_g,
        "fat_g": fat_g,
        "fiber_g": fiber_g,
    }


def test_effective_dated_targets_can_be_replaced(tmp_path: Path) -> None:
    with make_client(tmp_path / "coachline.sqlite3") as client:
        profile_id = create_profile(client)
        first = client.put(
            f"/profiles/{profile_id}/nutrition-targets/2026-08-01",
            json={
                "calories_kcal": 2_200,
                "protein_g": 160,
                "carbohydrates_g": 240,
                "fat_g": 70,
                "fiber_g": 30,
            },
        )
        replacement = client.put(
            f"/profiles/{profile_id}/nutrition-targets/2026-08-01",
            json={
                "calories_kcal": 2_100,
                "protein_g": 165,
                "carbohydrates_g": 220,
                "fat_g": 68,
                "fiber_g": 32,
            },
        )
        future = client.put(
            f"/profiles/{profile_id}/nutrition-targets/2026-09-01",
            json={"calories_kcal": 2_300, "protein_g": 170},
        )
        august = client.get(
            f"/profiles/{profile_id}/nutrition-targets",
            params={"on": "2026-08-25"},
        )
        september = client.get(
            f"/profiles/{profile_id}/nutrition-targets",
            params={"on": "2026-09-01"},
        )
        before_first = client.get(
            f"/profiles/{profile_id}/nutrition-targets",
            params={"on": "2026-07-31"},
        )

    assert first.status_code == 200
    assert replacement.json()["id"] == first.json()["id"]
    assert replacement.json()["calories_kcal"] == 2_100
    assert august.json() == replacement.json()
    assert september.json() == future.json()
    assert before_first.status_code == 200
    assert before_first.json() is None


def test_daily_summary_uses_profile_timezone_and_calculates_balance(
    tmp_path: Path,
) -> None:
    with make_client(tmp_path / "coachline.sqlite3") as client:
        profile_id = create_profile(client)
        client.put(
            f"/profiles/{profile_id}/nutrition-targets/2026-08-25",
            json={
                "calories_kcal": 2_000,
                "protein_g": 150,
                "carbohydrates_g": 220,
                "fat_g": 65,
                "fiber_g": 30,
            },
        )
        breakfast = client.post(
            f"/profiles/{profile_id}/meals",
            json=meal_payload(
                name="Breakfast",
                eaten_at="2026-08-25T08:00:00-07:00",
                calories_kcal=500,
                protein_g=35,
                carbohydrates_g=60,
                fat_g=15,
                fiber_g=8,
            ),
        )
        dinner = client.post(
            f"/profiles/{profile_id}/meals",
            json=meal_payload(
                name="Late dinner",
                eaten_at="2026-08-25T23:30:00-07:00",
                calories_kcal=800,
                protein_g=55,
                carbohydrates_g=90,
                fat_g=25,
                fiber_g=10,
            ),
        )
        client.post(
            f"/profiles/{profile_id}/meals",
            json=meal_payload(
                name="Next local day",
                eaten_at="2026-08-26T00:30:00-07:00",
                calories_kcal=300,
                protein_g=20,
                carbohydrates_g=30,
                fat_g=10,
            ),
        )
        summary = client.get(
            f"/profiles/{profile_id}/nutrition/daily",
            params={"on": "2026-08-25"},
        )
        meals = client.get(
            f"/profiles/{profile_id}/meals",
            params={"on": "2026-08-25"},
        )

    assert breakfast.status_code == 201
    assert dinner.status_code == 201
    assert breakfast.json()["value_source"] == "user_supplied"
    assert breakfast.json()["eaten_at"] == "2026-08-25T15:00:00Z"
    assert [meal["name"] for meal in meals.json()] == [
        "Breakfast",
        "Late dinner",
    ]
    assert summary.json()["totals"] == {
        "calories_kcal": 1_300,
        "protein_g": 90,
        "carbohydrates_g": 150,
        "fat_g": 40,
        "fiber_g": 18,
    }
    assert summary.json()["remaining"] == {
        "calories_kcal": 700,
        "protein_g": 60,
        "carbohydrates_g": 70,
        "fat_g": 25,
        "fiber_g": 12,
    }


def test_user_replacement_overrides_estimate_and_enforces_ownership(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "coachline.sqlite3"
    with make_client(database_path) as client:
        owner_id = create_profile(client, name="Owner")
        other_id = create_profile(client, name="Other")
        with Database(database_path).session() as connection:
            cursor = connection.execute(
                """
                INSERT INTO meal_entries
                    (profile_id, name, eaten_at, calories_kcal, protein_g,
                     carbohydrates_g, fat_g, fiber_g, value_source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ai_estimate')
                RETURNING id
                """,
                (
                    owner_id,
                    "Estimated lunch",
                    "2026-08-25T19:00:00+00:00",
                    700,
                    30,
                    80,
                    25,
                    5,
                ),
            )
            meal_id = cursor.fetchone()["id"]

        hidden = client.get(f"/profiles/{other_id}/meals/{meal_id}")
        replaced = client.put(
            f"/profiles/{owner_id}/meals/{meal_id}",
            json=meal_payload(
                name="Measured lunch",
                eaten_at="2026-08-25T12:00:00-07:00",
                calories_kcal=620,
                protein_g=42,
                carbohydrates_g=65,
                fat_g=20,
                fiber_g=7,
            ),
        )
        still_hidden = client.put(
            f"/profiles/{other_id}/meals/{meal_id}",
            json=meal_payload(
                name="Not allowed",
                eaten_at="2026-08-25T12:00:00-07:00",
                calories_kcal=1,
                protein_g=1,
                carbohydrates_g=1,
                fat_g=1,
            ),
        )

    assert hidden.status_code == 404
    assert still_hidden.status_code == 404
    assert replaced.status_code == 200
    assert replaced.json()["name"] == "Measured lunch"
    assert replaced.json()["calories_kcal"] == 620
    assert replaced.json()["value_source"] == "user_supplied"


def test_nutrition_input_validation_and_unknown_profile(tmp_path: Path) -> None:
    with make_client(tmp_path / "coachline.sqlite3") as client:
        profile_id = create_profile(client)
        empty_target = client.put(
            f"/profiles/{profile_id}/nutrition-targets/2026-08-25",
            json={},
        )
        naive_time = client.post(
            f"/profiles/{profile_id}/meals",
            json=meal_payload(
                name="No timezone",
                eaten_at="2026-08-25T12:00:00",
                calories_kcal=100,
                protein_g=1,
                carbohydrates_g=1,
                fat_g=1,
            ),
        )
        negative = client.post(
            f"/profiles/{profile_id}/meals",
            json=meal_payload(
                name="Invalid",
                eaten_at="2026-08-25T12:00:00Z",
                calories_kcal=-1,
                protein_g=1,
                carbohydrates_g=1,
                fat_g=1,
            ),
        )
        missing_profile = client.get(
            "/profiles/404/nutrition/daily", params={"on": "2026-08-25"}
        )

    assert empty_target.status_code == 422
    assert naive_time.status_code == 422
    assert negative.status_code == 422
    assert missing_profile.status_code == 404
