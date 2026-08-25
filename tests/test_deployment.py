import json
from pathlib import Path
from typing import Any
from urllib.request import Request

import pytest

from app.commands.run_reminders import invoke_reminder_runner
from app.commands.smoke_test import normalize_base_url, run_smoke_test


class FakeResponse:
    def __init__(
        self,
        payload: dict[str, Any],
        *,
        status: int = 200,
        request_id: str = "deployment-test-request",
    ) -> None:
        self.payload = json.dumps(payload).encode()
        self.status = status
        self.headers = {"X-Request-ID": request_id}

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, _: int) -> bytes:
        return self.payload


def test_render_scheduler_uses_private_authenticated_post() -> None:
    captured: dict[str, Any] = {}
    payload = {
        "jobs_synced": 2,
        "jobs_cancelled": 1,
        "jobs_recovered": 0,
        "delivered": 1,
        "retrying": 0,
        "failed": 0,
    }

    def opener(request: Request, *, timeout: int) -> FakeResponse:
        captured.update(
            url=request.full_url,
            method=request.method,
            headers=dict(request.header_items()),
            timeout=timeout,
        )
        return FakeResponse(payload)

    result = invoke_reminder_runner(
        "coachline-api.internal:8000",
        "private-admin-token",
        opener=opener,
    )

    assert result == payload
    assert captured == {
        "url": "http://coachline-api.internal:8000/reminders/run-due",
        "method": "POST",
        "headers": {
            "Accept": "application/json",
            "X-coachline-admin-token": "private-admin-token",
            "X-request-id": "render-reminder-cron",
        },
        "timeout": 15,
    }


@pytest.mark.parametrize(
    "hostport",
    [
        "https://public.example.com",
        "public.example.com/path:8000",
        "public.example.com",
        "public.example.com:0",
    ],
)
def test_render_scheduler_rejects_invalid_hostport_shapes(
    hostport: str,
) -> None:
    with pytest.raises(ValueError, match="host and port"):
        invoke_reminder_runner(hostport, "test-token")


def test_deployment_smoke_test_checks_all_health_contracts() -> None:
    requested: list[str] = []
    responses = {
        "https://coachline.example/health": {"status": "ok"},
        "https://coachline.example/health/live": {"status": "ok"},
        "https://coachline.example/health/ready": {
            "status": "ready",
            "database_backend": "postgresql",
        },
    }

    def opener(request: Request, *, timeout: int) -> FakeResponse:
        assert timeout == 15
        requested.append(request.full_url)
        return FakeResponse(responses[request.full_url])

    result = run_smoke_test(
        "https://coachline.example/",
        opener=opener,
    )

    assert requested == list(responses)
    assert result == {
        "base_url": "https://coachline.example",
        "database_backend": "postgresql",
        "request_id": "deployment-test-request",
        "status": "ready",
    }


@pytest.mark.parametrize(
    "url",
    [
        "http://coachline.example",
        "https://user:password@coachline.example",
        "https://coachline.example/health",
        "https://coachline.example?secret=value",
    ],
)
def test_deployment_smoke_test_rejects_unsafe_base_urls(url: str) -> None:
    with pytest.raises(ValueError):
        normalize_base_url(url)


def test_render_blueprint_has_private_database_and_no_secrets() -> None:
    blueprint = Path("render.yaml").read_text(encoding="utf-8")

    assert "healthCheckPath: /health/ready" in blueprint
    assert blueprint.count("autoDeployTrigger: checksPass") == 2
    assert "schedule: \"*/5 * * * *\"" in blueprint
    assert "property: hostport" in blueprint
    assert "property: connectionString" in blueprint
    assert "ipAllowList: []" in blueprint
    assert "generateValue: true" in blueprint
    assert "private-admin-token" not in blueprint
    assert "+1626" not in blueprint.replace(" ", "")
