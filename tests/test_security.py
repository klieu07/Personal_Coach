import json
import logging
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ai.config import OpenAISettings
from app.main import create_app
from app.messaging.config import TwilioSettings
from app.messaging.twilio import TwilioAdapter


OWNER_TOKEN = "test-owner-token"
OWNER_HEADER = {"Authorization": f"Bearer {OWNER_TOKEN}"}
PUBLIC_OPENAPI_PATHS = {
    "/health",
    "/health/live",
    "/health/ready",
    "/webhooks/twilio/sms",
}


def resolve_test_path(path: str) -> str:
    replacements = {
        "{effective_from}": "2026-08-25",
        "{meal_id}": "1",
        "{profile_id}": "1",
        "{provider}": "twilio",
        "{session_id}": "1",
    }
    for placeholder, value in replacements.items():
        path = path.replace(placeholder, value)
    return path


def database_counts(application: Any) -> dict[str, int]:
    with application.state.database.session() as connection:
        tables = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
        return {
            row["name"]: connection.execute(
                f'SELECT COUNT(*) AS count FROM "{row["name"]}"'
            ).fetchone()["count"]
            for row in tables
        }


def test_every_private_operation_rejects_missing_and_wrong_bearer_without_writes(
    tmp_path: Path,
) -> None:
    application = create_app(
        tmp_path / "coachline.sqlite3", admin_token=OWNER_TOKEN
    )

    with TestClient(application) as client:
        schema = client.get("/openapi.json").json()
        before = database_counts(application)
        checked: set[tuple[str, str]] = set()

        for path, path_item in schema["paths"].items():
            for method, operation in path_item.items():
                if not isinstance(operation, dict) or not operation.get("security"):
                    continue
                url = resolve_test_path(path)
                missing = client.request(method.upper(), url, json={})
                wrong = client.request(
                    method.upper(),
                    url,
                    json={},
                    headers={"Authorization": "Bearer wrong-owner-token"},
                )
                checked.add((method.upper(), path))
                for response in (missing, wrong):
                    assert response.status_code == 401
                    assert response.headers["www-authenticate"] == "Bearer"
                    assert response.headers["cache-control"] == "no-store"
                    assert OWNER_TOKEN not in response.text

        assert checked
        assert database_counts(application) == before


@pytest.mark.parametrize(
    "authorization",
    [None, "", "Basic abc123", "Bearer", "Bearer wrong-owner-token"],
)
def test_private_authentication_rejects_missing_malformed_and_wrong_credentials(
    tmp_path: Path,
    authorization: str | None,
) -> None:
    application = create_app(
        tmp_path / "coachline.sqlite3", admin_token=OWNER_TOKEN
    )
    headers = {} if authorization is None else {"Authorization": authorization}

    with TestClient(application) as client:
        response = client.post(
            "/profiles",
            json={"name": "Must Not Exist", "timezone": "UTC"},
            headers=headers,
        )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.headers["cache-control"] == "no-store"


def test_unconfigured_owner_authentication_fails_closed(tmp_path: Path) -> None:
    application = create_app(
        tmp_path / "coachline.sqlite3", admin_token=""
    )

    with TestClient(application) as client:
        response = client.get("/profiles/1", headers=OWNER_HEADER)

    assert response.status_code == 503
    assert response.json() == {"detail": "Owner authentication is not configured"}
    assert response.headers["cache-control"] == "no-store"


def test_correct_bearer_preserves_api_behavior_and_disables_caching(
    tmp_path: Path,
) -> None:
    application = create_app(
        tmp_path / "coachline.sqlite3", admin_token=OWNER_TOKEN
    )

    with TestClient(application) as client:
        created = client.post(
            "/profiles",
            json={"name": "Coachline Test", "timezone": "UTC"},
            headers=OWNER_HEADER,
        )
        fetched = client.get(
            f"/profiles/{created.json()['id']}", headers=OWNER_HEADER
        )

    assert created.status_code == 201
    assert fetched.json() == created.json()
    assert created.headers["cache-control"] == "no-store"
    assert fetched.headers["cache-control"] == "no-store"


def test_public_routes_and_openapi_security_boundaries(tmp_path: Path) -> None:
    application = create_app(
        tmp_path / "coachline.sqlite3", admin_token=OWNER_TOKEN
    )

    with TestClient(application) as client:
        for path in (
            "/health",
            "/health/live",
            "/health/ready",
            "/privacy",
            "/terms",
            "/sms-consent",
            "/docs",
            "/openapi.json",
        ):
            assert client.get(path).status_code == 200

        schema = client.get("/openapi.json").json()

    assert schema["components"]["securitySchemes"] == {
        "OwnerBearer": {
            "type": "http",
            "description": "Owner credential from COACHLINE_ADMIN_TOKEN",
            "scheme": "bearer",
        }
    }
    for path, path_item in schema["paths"].items():
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            if path in PUBLIC_OPENAPI_PATHS:
                assert "security" not in operation
            else:
                assert operation["security"] == [{"OwnerBearer": []}]


def test_twilio_webhook_uses_signature_without_bearer(tmp_path: Path) -> None:
    settings = TwilioSettings(
        account_sid="AC" + "1" * 32,
        auth_token="test-twilio-auth-token",
        from_address="+15555550100",
        webhook_url="http://testserver/webhooks/twilio/sms",
    )
    adapter = TwilioAdapter(
        settings,
        client=SimpleNamespace(messages=SimpleNamespace()),
    )
    application = create_app(
        tmp_path / "coachline.sqlite3",
        twilio_settings=settings,
        twilio_adapter=adapter,
        admin_token=OWNER_TOKEN,
    )
    parameters = {
        "MessageSid": "SM" + "2" * 32,
        "From": "+15555550123",
        "To": "+15555550100",
        "Body": "TODAY",
    }
    signature = adapter.validator.compute_signature(
        str(settings.webhook_url), parameters
    )

    with TestClient(application) as client:
        invalid = client.post(
            "/webhooks/twilio/sms",
            data=parameters,
            headers={"X-Twilio-Signature": "invalid"},
        )
        valid = client.post(
            "/webhooks/twilio/sms",
            data=parameters,
            headers={"X-Twilio-Signature": signature},
        )

    assert invalid.status_code == 403
    assert valid.status_code == 200
    assert valid.headers["content-type"].startswith("application/xml")


def test_credentials_and_private_request_data_are_absent_from_repr_logs_and_errors(
    tmp_path: Path,
    caplog: Any,
) -> None:
    openai_key = "unit-openai-secret-value"
    twilio_sid = "unit-twilio-account-value"
    twilio_token = "unit-twilio-secret-value"
    twilio_number = "+15555550987"
    settings_text = repr(OpenAISettings(api_key=openai_key)) + repr(
        TwilioSettings(
            account_sid=twilio_sid,
            auth_token=twilio_token,
            from_address=twilio_number,
            webhook_url="https://example.test/webhooks/twilio/sms",
        )
    )
    for private_value in (openai_key, twilio_sid, twilio_token, twilio_number):
        assert private_value not in settings_text

    application = create_app(
        tmp_path / "coachline.sqlite3", admin_token=OWNER_TOKEN
    )
    message_body = "private nutrition and workout message"
    with caplog.at_level(logging.INFO, logger="coachline.requests"):
        with TestClient(application) as client:
            response = client.post(
                "/profiles?private_query=do-not-log",
                json={"name": message_body, "timezone": "UTC"},
                headers={
                    "Authorization": "Bearer wrong-secret-token",
                    "X-Request-ID": "private-security-test",
                },
            )

    combined_logs = "\n".join(record.message for record in caplog.records)
    combined_output = combined_logs + response.text
    for private_value in (
        message_body,
        "do-not-log",
        "wrong-secret-token",
        OWNER_TOKEN,
        twilio_number,
    ):
        assert private_value not in combined_output
    event = next(
        json.loads(record.message)
        for record in caplog.records
        if "private-security-test" in record.message
    )
    assert set(event) == {
        "duration_ms",
        "event",
        "method",
        "path",
        "request_id",
        "status_code",
    }


def test_tracked_repository_has_no_local_databases_or_recognizable_live_secrets() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        check=True,
        capture_output=True,
    ).stdout.decode().split("\0")
    tracked = [name for name in tracked if name]

    forbidden_files = [
        name
        for name in tracked
        if Path(name).name == ".env"
        or Path(name).suffix.casefold() in {".db", ".sqlite", ".sqlite3"}
    ]
    assert forbidden_files == []

    token_patterns = {
        "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
        "GitHub token": re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
        "Google API key": re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
        "OpenAI key": re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
        "private key": re.compile(r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"),
    }
    findings: list[str] = []
    for name in tracked:
        try:
            content = Path(name).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in token_patterns.items():
            if pattern.search(content):
                findings.append(f"{name}: {label}")
        for number in re.findall(r"\+[1-9][0-9]{7,14}", content):
            if not number.startswith("+1555"):
                findings.append(f"{name}: non-test phone number")
    assert findings == []
