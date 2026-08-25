from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response returned when the service is healthy."""

    status: Literal["ok"]


app = FastAPI(title="Coachline")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report that the Coachline API process is available."""

    return HealthResponse(status="ok")
