from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.database import Database
from app.main import create_app
from app.messaging.config import TwilioSettings
from app.messaging.twilio import TwilioAdapter


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


class FakeMessages:
    def __init__(self, failures: int = 0) -> None:
        self.created: list[dict[str, str]] = []
        self.failures = failures

    def create(self, **payload: str) -> SimpleNamespace:
        self.created.append(payload)
        if self.failures:
            self.failures -= 1
            raise RuntimeError("fake provider outage")
        return SimpleNamespace(
            sid="SM" + str(len(self.created)).zfill(32),
            status="queued",
        )


class FakeTwilioClient:
    def __init__(self, failures: int = 0) -> None:
        self.messages = FakeMessages(failures)


def reminder_client(
    database_path: Path,
    clock: MutableClock,
    *,
    failures: int = 0,
) -> tuple[TestClient, FakeTwilioClient]:
    settings = TwilioSettings(
        account_sid="AC" + "1" * 32,
        auth_token="test-auth-token",
        from_address="+15555550100",
    )
    fake_twilio = FakeTwilioClient(failures)
    adapter = TwilioAdapter(settings, client=fake_twilio)
    app = create_app(
        database_path,
        twilio_settings=settings,
        twilio_adapter=adapter,
        admin_token="test-admin-token",
        now_provider=clock,
    )
    return TestClient(app), fake_twilio


def create_plan(
    client: TestClient,
    *,
    scheduled_for: str = "2026-08-26",
) -> tuple[int, int]:
    profile = client.post(
        "/profiles",
        json={"name": "Reminder Test", "timezone": "Asia/Shanghai"},
    ).json()
    profile_id = profile["id"]
    program = client.post(
        "/programs",
        json={
            "profile_id": profile_id,
            "name": "Reminder Running",
            "discipline": "running",
        },
    ).json()
    session = client.post(
        "/sessions",
        json={
            "program_id": program["id"],
            "scheduled_for": scheduled_for,
            "title": "Easy run",
        },
    ).json()
    contact = client.post(
        f"/profiles/{profile_id}/messaging-contacts",
        json={"provider": "twilio", "address": "+15555550123"},
    )
    assert contact.status_code == 201
    return profile_id, session["id"]


def enable_reminders(
    client: TestClient,
    profile_id: int,
    *,
    reminder_time: str = "08:00",
    quiet_start: str = "21:00",
    quiet_end: str = "07:00",
) -> None:
    response = client.put(
        f"/profiles/{profile_id}/reminder-settings",
        json={
            "enabled": True,
            "reminder_time": reminder_time,
            "quiet_hours_start": quiet_start,
            "quiet_hours_end": quiet_end,
        },
    )
    assert response.status_code == 200


def run_due(client: TestClient) -> object:
    return client.post(
        "/reminders/run-due",
        headers={"X-Coachline-Admin-Token": "test-admin-token"},
    )


def test_reminders_are_opt_in_and_settings_are_validated(tmp_path: Path) -> None:
    clock = MutableClock(datetime(2026, 8, 25, 0, tzinfo=timezone.utc))
    client, _ = reminder_client(tmp_path / "coachline.sqlite3", clock)

    with client:
        profile_id, _ = create_plan(client)
        defaults = client.get(
            f"/profiles/{profile_id}/reminder-settings"
        )
        invalid = client.put(
            f"/profiles/{profile_id}/reminder-settings",
            json={
                "enabled": True,
                "reminder_time": "08:00:30",
                "quiet_hours_start": "21:00",
                "quiet_hours_end": "07:00",
            },
        )
        unauthorized = client.post("/reminders/run-due")

    assert defaults.json() == {
        "enabled": False,
        "reminder_time": "08:00:00",
        "quiet_hours_start": "21:00:00",
        "quiet_hours_end": "07:00:00",
        "profile_id": profile_id,
    }
    assert invalid.status_code == 422
    assert unauthorized.status_code == 401


def test_quiet_hours_defer_delivery_and_runs_are_idempotent(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "coachline.sqlite3"
    clock = MutableClock(datetime(2026, 8, 25, 22, 30, tzinfo=timezone.utc))
    client, fake_twilio = reminder_client(database_path, clock)

    with client:
        profile_id, _ = create_plan(client)
        enable_reminders(client, profile_id, reminder_time="06:00")

        before_quiet_hours_end = run_due(client)
        assert before_quiet_hours_end.status_code == 200
        assert before_quiet_hours_end.json()["jobs_synced"] == 1
        assert before_quiet_hours_end.json()["delivered"] == 0

        clock.value = datetime(2026, 8, 25, 23, 1, tzinfo=timezone.utc)
        delivered = run_due(client)
        repeated = run_due(client)

    assert delivered.json()["delivered"] == 1
    assert repeated.json()["delivered"] == 0
    assert fake_twilio.messages.created == [
        {
            "to": "+15555550123",
            "from_": "+15555550100",
            "body": (
                "Coachline reminder: Easy run is planned for 2026-08-26. "
                "Reply TODAY for the workout details."
            ),
        }
    ]
    with Database(database_path).session() as connection:
        job = connection.execute(
            """
            SELECT scheduled_at, status, attempt_count
            FROM reminder_jobs
            """
        ).fetchone()
    assert dict(job) == {
        "scheduled_at": "2026-08-25T23:00:00+00:00",
        "status": "sent",
        "attempt_count": 1,
    }


def test_session_state_change_cancels_a_pending_reminder(tmp_path: Path) -> None:
    database_path = tmp_path / "coachline.sqlite3"
    clock = MutableClock(datetime(2026, 8, 25, 0, tzinfo=timezone.utc))
    client, fake_twilio = reminder_client(database_path, clock)

    with client:
        profile_id, session_id = create_plan(client, scheduled_for="2026-08-27")
        enable_reminders(client, profile_id)
        synced = run_due(client)
        assert synced.json()["jobs_synced"] == 1

        skipped = client.patch(
            f"/sessions/{session_id}/status", json={"status": "skipped"}
        )
        cancelled = run_due(client)

    assert skipped.status_code == 200
    assert cancelled.json()["jobs_cancelled"] == 1
    assert fake_twilio.messages.created == []
    with Database(database_path).session() as connection:
        status = connection.execute(
            "SELECT status FROM reminder_jobs WHERE session_id = ?",
            (session_id,),
        ).fetchone()["status"]
    assert status == "cancelled"


def test_failed_delivery_retries_after_backoff(tmp_path: Path) -> None:
    database_path = tmp_path / "coachline.sqlite3"
    clock = MutableClock(datetime(2026, 8, 26, 0, 1, tzinfo=timezone.utc))
    client, fake_twilio = reminder_client(database_path, clock, failures=1)

    with client:
        profile_id, _ = create_plan(client)
        enable_reminders(
            client,
            profile_id,
            reminder_time="08:00",
            quiet_start="22:00",
            quiet_end="06:00",
        )
        failed_once = run_due(client)
        too_soon = run_due(client)
        clock.value = datetime(2026, 8, 26, 0, 6, tzinfo=timezone.utc)
        retried = run_due(client)

    assert failed_once.json()["retrying"] == 1
    assert too_soon.json()["delivered"] == 0
    assert retried.json()["delivered"] == 1
    assert len(fake_twilio.messages.created) == 2
    with Database(database_path).session() as connection:
        job = connection.execute(
            "SELECT status, attempt_count FROM reminder_jobs"
        ).fetchone()
    assert dict(job) == {"status": "sent", "attempt_count": 2}
