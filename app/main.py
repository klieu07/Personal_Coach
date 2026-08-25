import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel

from app.database import Database
from app.repository import ConflictError, NotFoundError, SQLiteCoachlineRepository
from app.schemas import (
    Profile,
    ProfileCreate,
    Program,
    ProgramCreate,
    SessionCreate,
    SessionStatus,
    SessionStatusUpdate,
    TrainingSession,
    WorkoutResult,
    WorkoutResultCreate,
)
from app.services import CoachlineService


class HealthResponse(BaseModel):
    """Response returned when the service is healthy."""

    status: Literal["ok"]


def create_app(database_path: str | Path | None = None) -> FastAPI:
    """Create a Coachline application with an isolated persistence layer."""

    path = database_path or os.getenv(
        "COACHLINE_DATABASE_PATH", "data/coachline.sqlite3"
    )
    database = Database(path)
    service = CoachlineService(SQLiteCoachlineRepository(database))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        database.migrate()
        yield

    application = FastAPI(title="Coachline", version="0.2.0", lifespan=lifespan)

    def get_service() -> CoachlineService:
        return service

    Service = Annotated[CoachlineService, Depends(get_service)]

    @application.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        """Report that the Coachline API process is available."""

        return HealthResponse(status="ok")

    @application.post(
        "/profiles", response_model=Profile, status_code=status.HTTP_201_CREATED
    )
    def create_profile(payload: ProfileCreate, coachline: Service) -> Profile:
        return coachline.create_profile(payload)

    @application.get("/profiles/{profile_id}", response_model=Profile)
    def get_profile(profile_id: int, coachline: Service) -> Profile:
        try:
            return coachline.get_profile(profile_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.post(
        "/programs", response_model=Program, status_code=status.HTTP_201_CREATED
    )
    def create_program(payload: ProgramCreate, coachline: Service) -> Program:
        try:
            return coachline.create_program(payload)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.get("/profiles/{profile_id}/programs", response_model=list[Program])
    def list_programs(profile_id: int, coachline: Service) -> list[Program]:
        try:
            return coachline.list_programs(profile_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.post(
        "/sessions",
        response_model=TrainingSession,
        status_code=status.HTTP_201_CREATED,
    )
    def create_session(
        payload: SessionCreate, coachline: Service
    ) -> TrainingSession:
        try:
            return coachline.create_session(payload)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.get("/sessions/{session_id}", response_model=TrainingSession)
    def get_session(session_id: int, coachline: Service) -> TrainingSession:
        try:
            return coachline.get_session(session_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.get(
        "/profiles/{profile_id}/sessions", response_model=list[TrainingSession]
    )
    def list_sessions(
        profile_id: int,
        coachline: Service,
        session_status: Annotated[SessionStatus | None, Query(alias="status")] = None,
    ) -> list[TrainingSession]:
        try:
            return coachline.list_sessions(profile_id, session_status)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.patch(
        "/sessions/{session_id}/status", response_model=TrainingSession
    )
    def update_session_status(
        session_id: int, payload: SessionStatusUpdate, coachline: Service
    ) -> TrainingSession:
        try:
            return coachline.update_session_status(session_id, payload.status)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.post(
        "/sessions/{session_id}/result",
        response_model=WorkoutResult,
        status_code=status.HTTP_201_CREATED,
    )
    def record_result(
        session_id: int, payload: WorkoutResultCreate, coachline: Service
    ) -> WorkoutResult:
        try:
            return coachline.record_result(session_id, payload)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return application


app = create_app()
