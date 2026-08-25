import json
import logging
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.main import create_app


def test_liveness_readiness_and_request_correlation(
    tmp_path: Path,
    caplog: Any,
) -> None:
    application = create_app(tmp_path / "coachline.sqlite3")
    with caplog.at_level(logging.INFO, logger="coachline.requests"):
        with TestClient(application) as client:
            live = client.get(
                "/health/live?ignored=sensitive",
                headers={"X-Request-ID": "deployment-check-1"},
            )
            ready = client.get("/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "ok"}
    assert live.headers["X-Request-ID"] == "deployment-check-1"
    assert ready.json() == {
        "status": "ready",
        "database_backend": "sqlite",
    }
    events = [json.loads(record.message) for record in caplog.records]
    live_event = next(
        event for event in events if event["path"] == "/health/live"
    )
    assert live_event["event"] == "http_request"
    assert live_event["request_id"] == "deployment-check-1"
    assert live_event["status_code"] == 200
    assert "ignored" not in json.dumps(live_event)
    assert "sensitive" not in json.dumps(live_event)


def test_readiness_hides_database_failure_details(tmp_path: Path) -> None:
    application = create_app(tmp_path / "coachline.sqlite3")

    with TestClient(application) as client:
        def fail_ping() -> None:
            raise RuntimeError("database-password-must-not-leak")

        application.state.database.ping = fail_ping
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database is unavailable"}
    assert "password" not in response.text
