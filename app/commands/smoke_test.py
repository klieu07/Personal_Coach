"""Read-only smoke test for a deployed Coachline service."""

import argparse
import json
import re
import sys
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
MAX_RESPONSE_BYTES = 64 * 1024


def normalize_base_url(value: str) -> str:
    parsed = urlsplit(value)
    is_local_http = parsed.scheme == "http" and parsed.hostname in {
        "127.0.0.1",
        "localhost",
    }
    if parsed.scheme != "https" and not is_local_http:
        raise ValueError("deployment URL must use HTTPS")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("deployment URL must contain a safe hostname")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("deployment URL must not include a path or query")
    return value.rstrip("/")


def read_json(
    url: str,
    *,
    opener: Callable[..., Any] = urlopen,
) -> tuple[Mapping[str, Any], str]:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "X-Request-ID": "coachline-deployment-smoke",
        },
    )
    with opener(request, timeout=15) as response:
        if response.status != 200:
            raise RuntimeError(f"{url} returned HTTP {response.status}")
        request_id = response.headers.get("X-Request-ID", "")
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise RuntimeError(f"{url} returned too much data")
    payload = json.loads(raw)
    if not isinstance(payload, Mapping):
        raise RuntimeError(f"{url} did not return a JSON object")
    if not REQUEST_ID_PATTERN.fullmatch(request_id):
        raise RuntimeError(f"{url} did not return a safe request ID")
    return payload, request_id


def run_smoke_test(
    base_url: str,
    *,
    expected_backend: str = "postgresql",
    opener: Callable[..., Any] = urlopen,
) -> dict[str, str]:
    """Verify public health contracts without reading or changing user data."""

    base = normalize_base_url(base_url)
    health, _ = read_json(f"{base}/health", opener=opener)
    live, _ = read_json(f"{base}/health/live", opener=opener)
    ready, request_id = read_json(f"{base}/health/ready", opener=opener)
    if dict(health) != {"status": "ok"}:
        raise RuntimeError("legacy health contract failed")
    if dict(live) != {"status": "ok"}:
        raise RuntimeError("liveness contract failed")
    expected_ready = {
        "status": "ready",
        "database_backend": expected_backend,
    }
    if dict(ready) != expected_ready:
        raise RuntimeError("readiness contract failed")
    return {
        "base_url": base,
        "database_backend": expected_backend,
        "request_id": request_id,
        "status": "ready",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Coachline's read-only deployment smoke test."
    )
    parser.add_argument("base_url", help="Deployed HTTPS service URL")
    parser.add_argument(
        "--database-backend",
        choices=("postgresql", "sqlite"),
        default="postgresql",
    )
    arguments = parser.parse_args()
    try:
        result = run_smoke_test(
            arguments.base_url,
            expected_backend=arguments.database_backend,
        )
    except Exception as exc:
        print(f"Deployment smoke test failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
