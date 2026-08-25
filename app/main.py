import os
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from pydantic import BaseModel

from app.ai.config import OpenAISettings
from app.ai.openai import OpenAIInterpreter
from app.ai.ports import AIInterpreter
from app.ai.repository import SQLiteAIRepository
from app.database import Database
from app.messaging.config import TwilioSettings
from app.messaging.models import (
    MessageProvider,
    MessageSendCreate,
    MessagingContact,
    MessagingContactCreate,
    SentMessage,
)
from app.messaging.repository import (
    MessagingConflictError,
    MessagingNotFoundError,
    SQLiteMessagingRepository,
)
from app.messaging.service import MessagingService
from app.messaging.twilio import (
    InvalidInboundMessageError,
    MessageDeliveryError,
    MessagingNotConfiguredError,
    TwilioAdapter,
)
from app.repository import ConflictError, NotFoundError, SQLiteCoachlineRepository
from app.schemas import (
    Prescription,
    Profile,
    ProfileCreate,
    Program,
    ProgramCreate,
    ProgressionCreate,
    SessionCreate,
    SessionPlan,
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


def create_app(
    database_path: str | Path | None = None,
    *,
    twilio_settings: TwilioSettings | None = None,
    twilio_adapter: TwilioAdapter | None = None,
    openai_settings: OpenAISettings | None = None,
    ai_interpreter: AIInterpreter | None = None,
    admin_token: str | None = None,
) -> FastAPI:
    """Create a Coachline application with an isolated persistence layer."""

    path = database_path or os.getenv(
        "COACHLINE_DATABASE_PATH", "data/coachline.sqlite3"
    )
    database = Database(path)
    service = CoachlineService(SQLiteCoachlineRepository(database))
    settings = twilio_settings or TwilioSettings.from_env()
    outbound_admin_token = admin_token or os.getenv("COACHLINE_ADMIN_TOKEN")
    adapter = twilio_adapter
    if adapter is None and settings.can_validate_webhooks:
        adapter = TwilioAdapter(settings)
    ai_settings = openai_settings or OpenAISettings.from_env()
    interpreter = ai_interpreter
    if interpreter is None and ai_settings.enabled:
        interpreter = OpenAIInterpreter(ai_settings)
    messaging = MessagingService(
        service,
        SQLiteMessagingRepository(database),
        sender=adapter,
        interpreter=interpreter,
        ai_repository=SQLiteAIRepository(database),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        database.migrate()
        yield

    application = FastAPI(title="Coachline", version="0.5.0", lifespan=lifespan)

    def get_service() -> CoachlineService:
        return service

    Service = Annotated[CoachlineService, Depends(get_service)]

    def get_messaging() -> MessagingService:
        return messaging

    Messaging = Annotated[MessagingService, Depends(get_messaging)]

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

    @application.get(
        "/sessions/{session_id}/result", response_model=WorkoutResult
    )
    def get_result(session_id: int, coachline: Service) -> WorkoutResult:
        try:
            return coachline.get_result(session_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.put(
        "/sessions/{session_id}/prescription", response_model=Prescription
    )
    def save_prescription(
        session_id: int, payload: Prescription, coachline: Service
    ) -> Prescription:
        try:
            return coachline.save_prescription(session_id, payload)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.get(
        "/sessions/{session_id}/prescription", response_model=Prescription
    )
    def get_prescription(
        session_id: int, coachline: Service
    ) -> Prescription:
        try:
            return coachline.get_prescription(session_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.get(
        "/profiles/{profile_id}/today", response_model=list[SessionPlan]
    )
    def todays_workouts(
        profile_id: int,
        coachline: Service,
        on_date: Annotated[date | None, Query(alias="on")] = None,
    ) -> list[SessionPlan]:
        try:
            return coachline.todays_workouts(profile_id, on_date)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.post(
        "/sessions/{session_id}/progression",
        response_model=SessionPlan,
        status_code=status.HTTP_201_CREATED,
    )
    def progress_session(
        session_id: int, payload: ProgressionCreate, coachline: Service
    ) -> SessionPlan:
        try:
            return coachline.progress_session(session_id, payload)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.post(
        "/profiles/{profile_id}/messaging-contacts",
        response_model=MessagingContact,
        status_code=status.HTTP_201_CREATED,
    )
    def add_messaging_contact(
        profile_id: int,
        payload: MessagingContactCreate,
        messages: Messaging,
    ) -> MessagingContact:
        try:
            return messages.add_contact(profile_id, payload)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except MessagingConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.get(
        "/profiles/{profile_id}/messaging-contacts/{provider}",
        response_model=MessagingContact,
    )
    def get_messaging_contact(
        profile_id: int,
        provider: MessageProvider,
        messages: Messaging,
    ) -> MessagingContact:
        try:
            return messages.get_contact(profile_id, provider)
        except (NotFoundError, MessagingNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.post(
        "/profiles/{profile_id}/messages",
        response_model=SentMessage,
        status_code=status.HTTP_201_CREATED,
    )
    def send_message(
        profile_id: int,
        payload: MessageSendCreate,
        messages: Messaging,
        supplied_admin_token: Annotated[
            str | None, Header(alias="X-Coachline-Admin-Token")
        ] = None,
    ) -> SentMessage:
        if not outbound_admin_token:
            raise HTTPException(
                status_code=503,
                detail="COACHLINE_ADMIN_TOKEN is required for outbound SMS",
            )
        if supplied_admin_token is None or not secrets.compare_digest(
            supplied_admin_token, outbound_admin_token
        ):
            raise HTTPException(status_code=401, detail="Invalid admin token")
        try:
            service.get_profile(profile_id)
            return messages.send_to_profile(profile_id, payload.body)
        except (NotFoundError, MessagingNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (MessagingNotConfiguredError, RuntimeError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except MessageDeliveryError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @application.post("/webhooks/twilio/sms")
    async def receive_twilio_sms(request: Request) -> Response:
        if adapter is None:
            raise HTTPException(
                status_code=503,
                detail="TWILIO_AUTH_TOKEN is required for Twilio webhooks",
            )
        parameters = await request.form()
        signature = request.headers.get("X-Twilio-Signature", "")
        validation_url = settings.webhook_url or str(request.url)
        if not signature or not adapter.validate_webhook(
            validation_url, parameters, signature
        ):
            raise HTTPException(status_code=403, detail="Invalid Twilio signature")
        try:
            inbound = adapter.parse_inbound(parameters)
        except (InvalidInboundMessageError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        outcome = messaging.handle_inbound(inbound)
        return Response(
            content=adapter.render_twiml(outcome.reply_body),
            media_type="application/xml",
        )

    return application


app = create_app()
