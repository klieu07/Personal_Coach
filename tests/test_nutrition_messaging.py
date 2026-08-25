from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.ai.models import (
    AIMealEstimate,
    AIIntent,
    AIInterpretation,
    AIInterpretationResult,
)
from app.database import Database
from app.main import create_app
from app.messaging.config import TwilioSettings
from app.messaging.twilio import TwilioAdapter


class FakeInterpreter:
    def __init__(self, results: list[AIInterpretationResult]) -> None:
        self.results = results
        self.calls: list[dict[str, str]] = []

    def interpret(
        self, message: str, context: str, safety_identifier: str
    ) -> AIInterpretationResult:
        self.calls.append(
            {
                "message": message,
                "context": context,
                "safety_identifier": safety_identifier,
            }
        )
        return self.results.pop(0)


def interpretation(
    intent: AIIntent,
    *,
    meal: AIMealEstimate | None = None,
) -> AIInterpretationResult:
    return AIInterpretationResult(
        interpretation=AIInterpretation(
            intent=intent,
            session_id=None,
            summary=None,
            reply_text=None,
            meal=meal,
        ),
        response_id="resp_nutrition_fake",
        model="fake-model",
    )


def configured_client(
    database_path: Path,
    interpreter: Any | None = None,
) -> tuple[TestClient, TwilioAdapter]:
    settings = TwilioSettings(
        account_sid="AC" + "1" * 32,
        auth_token="test-auth-token",
        from_address="+15555550100",
        webhook_url="http://testserver/webhooks/twilio/sms",
    )
    adapter = TwilioAdapter(
        settings,
        client=SimpleNamespace(messages=SimpleNamespace()),
    )
    app = create_app(
        database_path,
        twilio_settings=settings,
        twilio_adapter=adapter,
        ai_interpreter=interpreter,
        admin_token="test-owner-token",
    )
    return (
        TestClient(
            app,
            headers={"Authorization": "Bearer test-owner-token"},
        ),
        adapter,
    )


def create_linked_profile(client: TestClient) -> int:
    profile = client.post(
        "/profiles",
        json={"name": "Nutrition SMS", "timezone": "Asia/Shanghai"},
    ).json()
    linked = client.post(
        f"/profiles/{profile['id']}/messaging-contacts",
        json={"provider": "twilio", "address": "+15555550123"},
    )
    assert linked.status_code == 201
    return profile["id"]


def webhook(
    client: TestClient,
    adapter: TwilioAdapter,
    sid_digit: str,
    body: str,
) -> Any:
    parameters = {
        "MessageSid": "SM" + sid_digit * 32,
        "From": "+15555550123",
        "To": "+15555550100",
        "Body": body,
    }
    signature = adapter.validator.compute_signature(
        str(adapter.settings.webhook_url), parameters
    )
    return client.post(
        "/webhooks/twilio/sms",
        data=parameters,
        headers={"X-Twilio-Signature": signature},
    )


def test_nutrition_command_is_deterministic_without_openai(
    tmp_path: Path,
) -> None:
    client, adapter = configured_client(tmp_path / "coachline.sqlite3")
    local_now = datetime.now(ZoneInfo("Asia/Shanghai"))

    with client:
        profile_id = create_linked_profile(client)
        client.put(
            f"/profiles/{profile_id}/nutrition-targets/{local_now.date()}",
            json={
                "calories_kcal": 2_000,
                "protein_g": 150,
                "carbohydrates_g": 220,
                "fat_g": 65,
                "fiber_g": 30,
            },
        )
        client.post(
            f"/profiles/{profile_id}/meals",
            json={
                "name": "Breakfast",
                "eaten_at": local_now.isoformat(),
                "calories_kcal": 500,
                "protein_g": 35,
                "carbohydrates_g": 60,
                "fat_g": 15,
                "fiber_g": 8,
            },
        )
        response = webhook(client, adapter, "1", "NUTRITION")

    assert response.status_code == 200
    assert "500/2000 kcal" in response.text
    assert "protein 35/150 g" in response.text
    assert "carbs 60/220 g" in response.text


def test_free_form_nutrition_question_uses_typed_read_intent(
    tmp_path: Path,
) -> None:
    fake = FakeInterpreter([interpretation(AIIntent.SHOW_NUTRITION)])
    client, adapter = configured_client(
        tmp_path / "coachline.sqlite3", fake
    )

    with client:
        create_linked_profile(client)
        response = webhook(
            client,
            adapter,
            "7",
            "How am I doing on calories today?",
        )

    assert "Nutrition for" in response.text
    assert "No nutrition target is set" in response.text
    assert len(fake.calls) == 1


def test_ai_meal_estimate_requires_confirmation_and_is_idempotent(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "coachline.sqlite3"
    meal = AIMealEstimate(
        name="Chicken burrito",
        eaten_at=datetime.now(timezone.utc),
        calories_kcal=720,
        protein_g=42,
        carbohydrates_g=82,
        fat_g=24,
        fiber_g=11,
    )
    fake = FakeInterpreter(
        [interpretation(AIIntent.LOG_MEAL_ESTIMATE, meal=meal)]
    )
    client, adapter = configured_client(database_path, fake)

    with client:
        profile_id = create_linked_profile(client)
        proposed = webhook(client, adapter, "2", "I ate a chicken burrito")
        before = client.get(
            f"/profiles/{profile_id}/meals",
            params={"on": meal.eaten_at.astimezone(ZoneInfo("Asia/Shanghai")).date()},
        )
        confirmed = webhook(client, adapter, "3", "YES")
        retried = webhook(client, adapter, "3", "YES")
        after = client.get(
            f"/profiles/{profile_id}/meals",
            params={"on": meal.eaten_at.astimezone(ZoneInfo("Asia/Shanghai")).date()},
        )

    assert "AI estimate" in proposed.text
    assert "Save this estimate" in proposed.text
    assert before.json() == []
    assert "Saved Chicken burrito as an AI estimate" in confirmed.text
    assert retried.text == confirmed.text
    assert len(after.json()) == 1
    assert after.json()[0]["value_source"] == "ai_estimate"
    assert after.json()[0]["calories_kcal"] == 720
    assert len(fake.calls) == 1
    assert "Local datetime:" in fake.calls[0]["context"]
    with Database(database_path).session() as connection:
        meal_count = connection.execute(
            "SELECT COUNT(*) AS count FROM meal_entries"
        ).fetchone()["count"]
    assert meal_count == 1


def test_ai_meal_estimate_can_be_cancelled(tmp_path: Path) -> None:
    meal = AIMealEstimate(
        name="Snack",
        eaten_at=datetime.now(timezone.utc),
        calories_kcal=250,
        protein_g=8,
        carbohydrates_g=35,
        fat_g=9,
        fiber_g=4,
    )
    fake = FakeInterpreter(
        [interpretation(AIIntent.LOG_MEAL_ESTIMATE, meal=meal)]
    )
    client, adapter = configured_client(
        tmp_path / "coachline.sqlite3", fake
    )

    with client:
        profile_id = create_linked_profile(client)
        webhook(client, adapter, "4", "Log my snack")
        cancelled = webhook(client, adapter, "5", "NO")
        meals = client.get(
            f"/profiles/{profile_id}/meals",
            params={"on": meal.eaten_at.astimezone(ZoneInfo("Asia/Shanghai")).date()},
        )

    assert "No nutrition data was changed" in cancelled.text
    assert meals.json() == []


def test_out_of_range_meal_estimate_is_rejected(tmp_path: Path) -> None:
    meal = AIMealEstimate(
        name="Future meal",
        eaten_at=datetime.now(timezone.utc) + timedelta(days=2),
        calories_kcal=400,
        protein_g=20,
        carbohydrates_g=50,
        fat_g=12,
        fiber_g=5,
    )
    fake = FakeInterpreter(
        [interpretation(AIIntent.LOG_MEAL_ESTIMATE, meal=meal)]
    )
    database_path = tmp_path / "coachline.sqlite3"
    client, adapter = configured_client(database_path, fake)

    with client:
        create_linked_profile(client)
        rejected = webhook(client, adapter, "6", "Log a future meal")

    assert "couldn't safely place that meal in time" in rejected.text
    with Database(database_path).session() as connection:
        pending = connection.execute(
            "SELECT COUNT(*) AS count FROM pending_actions"
        ).fetchone()["count"]
    assert pending == 0
