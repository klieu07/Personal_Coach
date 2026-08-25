import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ai.config import OpenAISettings
from app.ai.models import (
    AIMealEstimate,
    AIIntent,
    AIInterpretation,
    AIInterpretationResult,
)
from app.ai.openai import OpenAIInterpreter
from app.ai.ports import AIInterpretationError
from app.database import Database
from app.main import create_app
from app.messaging.config import TwilioSettings
from app.messaging.twilio import TwilioAdapter


class FakeResponses:
    def __init__(self, output: dict[str, object]) -> None:
        self.output = output
        self.requests: list[dict[str, Any]] = []

    def create(self, **request: Any) -> SimpleNamespace:
        self.requests.append(request)
        return SimpleNamespace(
            id="resp_test_123",
            output_text=json.dumps(self.output),
        )


class FakeOpenAIClient:
    def __init__(self, output: dict[str, object]) -> None:
        self.responses = FakeResponses(output)


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


class FailingInterpreter:
    def interpret(
        self, message: str, context: str, safety_identifier: str
    ) -> AIInterpretationResult:
        raise AIInterpretationError("test failure")


def result(
    intent: AIIntent,
    *,
    session_id: int | None = None,
    summary: str | None = None,
    reply_text: str | None = None,
    meal: AIMealEstimate | None = None,
) -> AIInterpretationResult:
    return AIInterpretationResult(
        interpretation=AIInterpretation(
            intent=intent,
            session_id=session_id,
            summary=summary,
            reply_text=reply_text,
            meal=meal,
        ),
        response_id="resp_fake",
        model="fake-model",
    )


def ai_client(
    database_path: Path, interpreter: Any
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
    )
    return TestClient(app), adapter


def create_profile_session(client: TestClient) -> tuple[int, int]:
    profile = client.post(
        "/profiles",
        json={"name": "Kai", "timezone": "Asia/Shanghai"},
    ).json()
    client.post(
        f"/profiles/{profile['id']}/messaging-contacts",
        json={"provider": "twilio", "address": "+15555550123"},
    )
    program = client.post(
        "/programs",
        json={
            "profile_id": profile["id"],
            "name": "Strength",
            "discipline": "lifting",
        },
    ).json()
    session = client.post(
        "/sessions",
        json={
            "program_id": program["id"],
            "scheduled_for": "2026-08-30",
            "title": "Squat day",
        },
    ).json()
    return profile["id"], session["id"]


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


def test_openai_adapter_requests_strict_non_stored_output() -> None:
    fake_client = FakeOpenAIClient(
        {
            "intent": "skip_session",
            "session_id": 7,
            "summary": None,
            "reply_text": None,
            "meal": None,
        }
    )
    adapter = OpenAIInterpreter(
        OpenAISettings(api_key="test-key", model="gpt-5.6-luna"),
        client=fake_client,
    )

    interpreted = adapter.interpret(
        "I need to miss session 7",
        "Known sessions:\n- id=7; status=planned; title=Squat day",
        "a" * 64,
    )

    assert interpreted.interpretation.intent is AIIntent.SKIP_SESSION
    request = fake_client.responses.requests[0]
    assert request["model"] == "gpt-5.6-luna"
    assert request["reasoning"] == {"effort": "low"}
    assert request["store"] is False
    assert request["safety_identifier"] == "a" * 64
    assert request["text"]["format"]["strict"] is True
    schema = request["text"]["format"]["schema"]
    assert schema["additionalProperties"] is False
    assert "meal" in schema["required"]
    assert schema["$defs"]["AIMealEstimate"]["additionalProperties"] is False


def test_openai_adapter_rejects_invalid_meal_estimate() -> None:
    fake_client = FakeOpenAIClient(
        {
            "intent": "log_meal_estimate",
            "session_id": None,
            "summary": None,
            "reply_text": None,
            "meal": {
                "name": "Lunch",
                "eaten_at": "2026-08-25T12:00:00",
                "calories_kcal": 600,
                "protein_g": 35,
                "carbohydrates_g": 70,
                "fat_g": 20,
                "fiber_g": 8,
            },
        }
    )
    adapter = OpenAIInterpreter(
        OpenAISettings(api_key="test-key"),
        client=fake_client,
    )

    with pytest.raises(AIInterpretationError):
        adapter.interpret("I ate lunch", "Local datetime: now", "c" * 64)


def test_openai_adapter_rejects_malformed_structured_output() -> None:
    fake_client = FakeOpenAIClient(
        {
            "intent": "record_result",
            "session_id": None,
            "summary": None,
            "reply_text": None,
            "meal": None,
        }
    )
    adapter = OpenAIInterpreter(
        OpenAISettings(api_key="test-key"),
        client=fake_client,
    )

    with pytest.raises(AIInterpretationError):
        adapter.interpret("I finished", "Known sessions: none", "b" * 64)


def test_ai_skip_requires_confirmation_and_retry_is_idempotent(
    tmp_path: Path,
) -> None:
    interpreter = FakeInterpreter([result(AIIntent.SKIP_SESSION, session_id=1)])
    database_path = tmp_path / "coachline.sqlite3"
    client, adapter = ai_client(database_path, interpreter)

    with client:
        _, session_id = create_profile_session(client)
        proposed = webhook(
            client, adapter, "1", f"I need to skip session {session_id}"
        )
        assert "Confirm skipping" in proposed.text
        assert client.get(f"/sessions/{session_id}").json()["status"] == "planned"

        confirmed = webhook(client, adapter, "2", "YES")
        retry = webhook(client, adapter, "2", "YES")
        assert "Skipped Squat day" in confirmed.text
        assert retry.text == confirmed.text
        assert client.get(f"/sessions/{session_id}").json()["status"] == "skipped"

    assert len(interpreter.calls) == 1
    assert len(interpreter.calls[0]["safety_identifier"]) == 64
    assert "+15555550123" not in str(interpreter.calls[0])
    with Database(database_path).session() as connection:
        interpretations = connection.execute(
            "SELECT COUNT(*) AS count FROM ai_interpretations"
        ).fetchone()["count"]
        pending = connection.execute(
            "SELECT COUNT(*) AS count FROM pending_actions"
        ).fetchone()["count"]
    assert interpretations == 1
    assert pending == 0


def test_ai_completion_can_be_canceled_without_mutation(tmp_path: Path) -> None:
    interpreter = FakeInterpreter(
        [
            result(
                AIIntent.RECORD_RESULT,
                session_id=1,
                summary="Completed all prescribed work",
            )
        ]
    )
    client, adapter = ai_client(tmp_path / "coachline.sqlite3", interpreter)

    with client:
        _, session_id = create_profile_session(client)
        proposed = webhook(client, adapter, "3", "I finished session 1")
        canceled = webhook(client, adapter, "4", "NO")

        assert "Confirm completing" in proposed.text
        assert "No training data was changed" in canceled.text
        assert client.get(f"/sessions/{session_id}").json()["status"] == "planned"
        assert client.get(f"/sessions/{session_id}/result").status_code == 404


def test_ai_completion_confirmation_records_result(tmp_path: Path) -> None:
    interpreter = FakeInterpreter(
        [
            result(
                AIIntent.RECORD_RESULT,
                session_id=1,
                summary="Completed three sets of five",
            )
        ]
    )
    client, adapter = ai_client(tmp_path / "coachline.sqlite3", interpreter)

    with client:
        _, session_id = create_profile_session(client)
        webhook(client, adapter, "7", "I completed session 1")
        confirmed = webhook(client, adapter, "8", "YES")
        stored = client.get(f"/sessions/{session_id}/result")

    assert "Completed Squat day" in confirmed.text
    assert stored.status_code == 200
    assert stored.json()["summary"] == "Completed three sets of five"


def test_ai_cannot_target_another_profiles_session(tmp_path: Path) -> None:
    interpreter = FakeInterpreter([result(AIIntent.SKIP_SESSION, session_id=2)])
    database_path = tmp_path / "coachline.sqlite3"
    client, adapter = ai_client(database_path, interpreter)

    with client:
        create_profile_session(client)
        second_profile = client.post(
            "/profiles",
            json={"name": "Other", "timezone": "UTC"},
        ).json()
        second_program = client.post(
            "/programs",
            json={
                "profile_id": second_profile["id"],
                "name": "Other plan",
                "discipline": "running",
            },
        ).json()
        other_session = client.post(
            "/sessions",
            json={
                "program_id": second_program["id"],
                "scheduled_for": "2026-08-31",
                "title": "Private run",
            },
        ).json()

        rejected = webhook(client, adapter, "9", "Skip session 2")

        assert "couldn't find that session" in rejected.text
        assert client.get(f"/sessions/{other_session['id']}").json()[
            "status"
        ] == "planned"

    with Database(database_path).session() as connection:
        pending = connection.execute(
            "SELECT COUNT(*) AS count FROM pending_actions"
        ).fetchone()["count"]
    assert pending == 0


def test_ai_failure_has_safe_fallback_and_today_stays_deterministic(
    tmp_path: Path,
) -> None:
    client, adapter = ai_client(
        tmp_path / "coachline.sqlite3", FailingInterpreter()
    )

    with client:
        create_profile_session(client)
        failed = webhook(client, adapter, "5", "Can you understand this?")
        today = webhook(client, adapter, "6", "TODAY")

    assert "couldn't interpret that safely" in failed.text
    assert "planned workouts" in today.text or "workout" in today.text
