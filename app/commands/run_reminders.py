"""Invoke Coachline's authenticated reminder runner from a private network."""

import json
import os
import re
import sys
from collections.abc import Callable, Mapping
from typing import Any
from urllib.request import Request, urlopen


HOSTPORT_PATTERN = re.compile(r"^[A-Za-z0-9.-]+:[1-9][0-9]{0,4}$")
RESULT_KEYS = {
    "jobs_synced",
    "jobs_cancelled",
    "jobs_recovered",
    "delivered",
    "retrying",
    "failed",
}
MAX_RESPONSE_BYTES = 64 * 1024


def invoke_reminder_runner(
    hostport: str,
    admin_token: str,
    *,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, int]:
    """Run one scheduler batch and validate its non-sensitive result."""

    if not HOSTPORT_PATTERN.fullmatch(hostport):
        raise ValueError("COACHLINE_API_HOSTPORT must be a host and port")
    if not admin_token:
        raise ValueError("COACHLINE_ADMIN_TOKEN is required")

    request = Request(
        f"http://{hostport}/reminders/run-due",
        data=b"",
        headers={
            "Accept": "application/json",
            "X-Coachline-Admin-Token": admin_token,
            "X-Request-ID": "render-reminder-cron",
        },
        method="POST",
    )
    with opener(request, timeout=15) as response:
        if response.status != 200:
            raise RuntimeError(
                f"Coachline reminder runner returned HTTP {response.status}"
            )
        raw = response.read(MAX_RESPONSE_BYTES + 1)

    if len(raw) > MAX_RESPONSE_BYTES:
        raise RuntimeError("Coachline reminder response was too large")
    payload = json.loads(raw)
    if not isinstance(payload, Mapping) or set(payload) != RESULT_KEYS:
        raise RuntimeError("Coachline reminder response had an invalid shape")
    if any(type(value) is not int or value < 0 for value in payload.values()):
        raise RuntimeError("Coachline reminder response had invalid counts")
    return {key: payload[key] for key in sorted(RESULT_KEYS)}


def main() -> int:
    try:
        result = invoke_reminder_runner(
            os.getenv("COACHLINE_API_HOSTPORT", ""),
            os.getenv("COACHLINE_ADMIN_TOKEN", ""),
        )
    except Exception as exc:
        print(f"Reminder scheduler failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
