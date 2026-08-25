from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.database import Database
from app.main import create_app
from app.messaging.config import TwilioSettings
from app.messaging.twilio import TwilioAdapter


class FakeMessages:
    def __init__(self) -> None:
        self.created: list[dict[str, str]] = []

    def create(self, **payload: str) -> SimpleNamespace:
        self.created.append(payload)
        return SimpleNamespace(
            sid="SM" + "9" * 32,
            status="queued",
        )


class FakeTwilioClient:
    def __init__(self) -> None:
        self.messages = FakeMessages()


def configured_client(
    database_path: Path,
) -> tuple[TestClient, TwilioAdapter, FakeTwilioClient]:
    settings = TwilioSettings(
        account_sid="AC" + "1" * 32,
        auth_token="test-auth-token",
        from_address="+15555550100",
        webhook_url="http://testserver/webhooks/twilio/sms",
    )
    fake_client = FakeTwilioClient()
    adapter = TwilioAdapter(settings, client=fake_client)
    app = create_app(
        database_path,
        twilio_settings=settings,
        twilio_adapter=adapter,
        admin_token="test-admin-token",
    )
    return (
        TestClient(
            app,
            headers={"Authorization": "Bearer test-admin-token"},
        ),
        adapter,
        fake_client,
    )


def create_linked_profile(client: TestClient) -> int:
    profile = client.post(
        "/profiles",
        json={"name": "Kai", "timezone": "Asia/Shanghai"},
    ).json()
    contact = client.post(
        f"/profiles/{profile['id']}/messaging-contacts",
        json={"provider": "twilio", "address": "+15555550123"},
    )
    assert contact.status_code == 201
    return profile["id"]


def sign(adapter: TwilioAdapter, parameters: dict[str, str]) -> str:
    url = str(adapter.settings.webhook_url)
    return adapter.validator.compute_signature(url, parameters)


def test_signed_twilio_webhook_returns_today_and_is_idempotent(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "coachline.sqlite3"
    client, adapter, _ = configured_client(database_path)
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()

    with client:
        profile_id = create_linked_profile(client)
        program = client.post(
            "/programs",
            json={
                "profile_id": profile_id,
                "name": "SMS Running",
                "discipline": "running",
            },
        ).json()
        session = client.post(
            "/sessions",
            json={
                "program_id": program["id"],
                "scheduled_for": today,
                "title": "Easy run",
            },
        ).json()
        client.put(
            f"/sessions/{session['id']}/prescription",
            json={
                "discipline": "running",
                "segments": [{"kind": "steady", "distance_m": 5000}],
            },
        )

        parameters = {
            "MessageSid": "SM" + "2" * 32,
            "AccountSid": "AC" + "1" * 32,
            "From": "+15555550123",
            "To": "+15555550100",
            "Body": "TODAY",
            "NumMedia": "0",
        }
        invalid = client.post(
            "/webhooks/twilio/sms",
            data=parameters,
            headers={"X-Twilio-Signature": "invalid"},
        )
        assert invalid.status_code == 403

        signature = sign(adapter, parameters)
        first = client.post(
            "/webhooks/twilio/sms",
            data=parameters,
            headers={"X-Twilio-Signature": signature},
        )
        retry = client.post(
            "/webhooks/twilio/sms",
            data=parameters,
            headers={"X-Twilio-Signature": signature},
        )

        assert first.status_code == 200
        assert first.headers["content-type"].startswith("application/xml")
        assert "Today's Coachline workout" in first.text
        assert "Easy run: steady 5000 m" in first.text
        assert retry.text == first.text

    database = Database(database_path)
    with database.session() as connection:
        count = connection.execute(
            "SELECT COUNT(*) AS count FROM inbound_messages"
        ).fetchone()["count"]
    assert count == 1


def test_unlinked_number_receives_safe_reply(tmp_path: Path) -> None:
    client, adapter, _ = configured_client(tmp_path / "coachline.sqlite3")
    parameters = {
        "MessageSid": "SM" + "3" * 32,
        "From": "+15555550999",
        "To": "+15555550100",
        "Body": "today",
    }

    with client:
        response = client.post(
            "/webhooks/twilio/sms",
            data=parameters,
            headers={"X-Twilio-Signature": sign(adapter, parameters)},
        )

    assert response.status_code == 200
    assert "not linked to a Coachline profile" in response.text


def test_outbound_message_uses_provider_boundary(tmp_path: Path) -> None:
    client, _, fake_twilio = configured_client(tmp_path / "coachline.sqlite3")

    with client:
        profile_id = create_linked_profile(client)
        unauthorized = client.post(
            f"/profiles/{profile_id}/messages",
            json={"body": "Do not send this."},
            headers={"Authorization": ""},
        )
        sent = client.post(
            f"/profiles/{profile_id}/messages",
            json={"body": "Tomorrow is a rest day."},
            headers={"Authorization": "Bearer test-admin-token"},
        )
        duplicate_contact = client.post(
            f"/profiles/{profile_id}/messaging-contacts",
            json={"provider": "twilio", "address": "+15555550124"},
        )

    assert unauthorized.status_code == 401
    assert sent.status_code == 201
    assert sent.json()["status"] == "queued"
    assert fake_twilio.messages.created == [
        {
            "to": "+15555550123",
            "from_": "+15555550100",
            "body": "Tomorrow is a rest day.",
        }
    ]
    assert duplicate_contact.status_code == 409


def test_twilio_routes_are_unavailable_without_configuration(tmp_path: Path) -> None:
    app = create_app(
        tmp_path / "coachline.sqlite3",
        twilio_settings=TwilioSettings(),
        admin_token="test-admin-token",
    )
    with TestClient(
        app,
        headers={"Authorization": "Bearer test-admin-token"},
    ) as client:
        profile_id = create_linked_profile(client)
        webhook = client.post("/webhooks/twilio/sms")
        outbound = client.post(
            f"/profiles/{profile_id}/messages",
            json={"body": "Hello"},
        )

    assert webhook.status_code == 503
    assert outbound.status_code == 503
