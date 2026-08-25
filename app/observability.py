"""Privacy-safe request correlation and structured access logging."""

import json
import logging
import os
import re
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response


REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
request_logger = logging.getLogger("coachline.requests")


def install_request_observability(application: FastAPI) -> None:
    """Add request IDs and JSON logs without bodies, queries, or addresses."""

    level_name = os.getenv("COACHLINE_LOG_LEVEL", "INFO").upper()
    request_logger.setLevel(getattr(logging, level_name, logging.INFO))

    @application.middleware("http")
    async def observe_request(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        supplied = request.headers.get("X-Request-ID", "")
        request_id = (
            supplied
            if REQUEST_ID_PATTERN.fullmatch(supplied)
            else uuid.uuid4().hex
        )
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            request_logger.info(
                json.dumps(
                    {
                        "duration_ms": duration_ms,
                        "event": "http_request",
                        "method": request.method,
                        "path": request.url.path,
                        "request_id": request_id,
                        "status_code": status_code,
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
