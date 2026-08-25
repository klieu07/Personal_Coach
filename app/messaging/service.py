"""Provider-neutral messaging application workflows."""

import hashlib
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.ai.models import AIIntent, AIInterpretation, PendingAction
from app.ai.ports import AIInterpretationError, AIInterpreter
from app.ai.repository import AIRepository
from app.messaging.models import (
    InboundMessage,
    InboundOutcome,
    MessageProvider,
    MessagingContact,
    MessagingContactCreate,
    OutboundMessage,
    SentMessage,
)
from app.messaging.ports import MessageSender
from app.messaging.repository import (
    MessagingConflictError,
    MessagingRepository,
)
from app.repository import ConflictError, NotFoundError
from app.schemas import (
    LiftingPrescription,
    SessionPlan,
    SessionStatus,
    WorkoutResultCreate,
)
from app.services import CoachlineService


class MessagingService:
    """Route normalized messages without depending on a provider webhook."""

    def __init__(
        self,
        coachline: CoachlineService,
        repository: MessagingRepository,
        sender: MessageSender | None = None,
        interpreter: AIInterpreter | None = None,
        ai_repository: AIRepository | None = None,
    ) -> None:
        self.coachline = coachline
        self.repository = repository
        self.sender = sender
        self.interpreter = interpreter
        self.ai_repository = ai_repository

    def add_contact(
        self, profile_id: int, payload: MessagingContactCreate
    ) -> MessagingContact:
        self.coachline.get_profile(profile_id)
        return self.repository.add_contact(profile_id, payload)

    def get_contact(
        self, profile_id: int, provider: MessageProvider
    ) -> MessagingContact:
        self.coachline.get_profile(profile_id)
        return self.repository.get_contact_for_profile(profile_id, provider.value)

    def handle_inbound(self, message: InboundMessage) -> InboundOutcome:
        exists, stored_reply = self.repository.get_inbound_reply(
            message.provider.value, message.external_id
        )
        if exists:
            return InboundOutcome(reply_body=stored_reply, duplicate=True)

        contact = self.repository.find_contact(
            message.provider.value, message.from_address
        )
        if contact is None:
            reply = (
                "This number is not linked to a Coachline profile. "
                "Link it before using SMS commands."
            )
        else:
            reply = self._route_command(contact, message)

        try:
            self.repository.save_inbound(
                message, contact.id if contact else None, reply
            )
        except MessagingConflictError:
            _, reply = self.repository.get_inbound_reply(
                message.provider.value, message.external_id
            )
            return InboundOutcome(reply_body=reply, duplicate=True)
        return InboundOutcome(reply_body=reply)

    def send_to_profile(self, profile_id: int, body: str) -> SentMessage:
        if self.sender is None:
            raise RuntimeError("No outbound messaging provider is configured")
        contact = self.repository.get_contact_for_profile(
            profile_id, MessageProvider.TWILIO.value
        )
        sent = self.sender.send(
            OutboundMessage(to_address=contact.address, body=body)
        )
        self.repository.save_outbound(contact.id, sent)
        return sent

    def _route_command(
        self, contact: MessagingContact, message: InboundMessage
    ) -> str:
        profile_id = contact.profile_id
        command = " ".join(message.body.casefold().split())
        if command in {"today", "workout", "today's workout", "todays workout"}:
            plans = self.coachline.todays_workouts(profile_id)
            return self._format_today(plans)

        pending = (
            self.ai_repository.get_pending(contact.id)
            if self.ai_repository is not None
            else None
        )
        if command in {"yes", "y", "confirm"}:
            if pending is None:
                return "There is no pending Coachline action to confirm."
            return self._execute_pending(profile_id, pending)
        if command in {"no", "n", "cancel"}:
            if pending is None:
                return "There is no pending Coachline action to cancel."
            self.ai_repository.clear_pending(contact.id)
            return "Canceled. No training data was changed."
        if pending is not None:
            return pending.confirmation_prompt + " Reply YES or NO."

        if self.interpreter is None or self.ai_repository is None:
            return (
                "Coachline received your message. Reply TODAY to see your planned "
                "workouts. AI interpretation is not configured."
            )

        safety_identifier = hashlib.sha256(
            f"coachline-profile:{profile_id}".encode()
        ).hexdigest()
        try:
            result = self.interpreter.interpret(
                message.body,
                self._build_context(profile_id),
                safety_identifier,
            )
        except AIInterpretationError:
            return (
                "I couldn't interpret that safely right now. Reply TODAY for "
                "your workout or try again later."
            )
        self.ai_repository.save_interpretation(
            message.provider.value,
            message.external_id,
            profile_id,
            result,
        )
        return self._handle_interpretation(contact, result.interpretation)

    def _handle_interpretation(
        self,
        contact: MessagingContact,
        interpretation: AIInterpretation,
    ) -> str:
        if interpretation.intent is AIIntent.SHOW_TODAY:
            return self._format_today(
                self.coachline.todays_workouts(contact.profile_id)
            )
        if interpretation.intent in {AIIntent.CLARIFY, AIIntent.REPLY}:
            return str(interpretation.reply_text)

        session_id = int(interpretation.session_id)
        try:
            session = self.coachline.get_session_for_profile(
                contact.profile_id, session_id
            )
        except NotFoundError:
            return "I couldn't find that session in your Coachline profile."

        if interpretation.intent is AIIntent.SKIP_SESSION:
            if session.status is SessionStatus.COMPLETED:
                return "That session is already completed and cannot be skipped."
            if session.status is SessionStatus.SKIPPED:
                return "That session is already marked skipped."
            prompt = (
                f"Confirm skipping session {session.id}, {session.title}, "
                f"scheduled for {session.scheduled_for}?"
            )
        else:
            if session.status is SessionStatus.COMPLETED:
                return "That session is already completed."
            if session.status is SessionStatus.SKIPPED:
                return "Replan that skipped session before recording a result."
            summary = str(interpretation.summary)
            prompt = (
                f"Confirm completing session {session.id}, {session.title}, "
                f"with result: {summary[:300]}?"
            )

        self.ai_repository.replace_pending(
            PendingAction(
                contact_id=contact.id,
                interpretation=interpretation,
                confirmation_prompt=prompt,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            )
        )
        return prompt + " Reply YES or NO."

    def _execute_pending(
        self, profile_id: int, pending: PendingAction
    ) -> str:
        action = pending.interpretation
        session_id = int(action.session_id)
        try:
            session = self.coachline.get_session_for_profile(
                profile_id, session_id
            )
            if action.intent is AIIntent.SKIP_SESSION:
                self.coachline.update_session_status(
                    session_id, SessionStatus.SKIPPED
                )
                reply = f"Skipped {session.title} on {session.scheduled_for}."
            else:
                self.coachline.record_result(
                    session_id,
                    WorkoutResultCreate(summary=str(action.summary)),
                )
                reply = f"Completed {session.title} on {session.scheduled_for}."
        except (NotFoundError, ConflictError) as exc:
            reply = f"That action could not be completed: {exc}"
        self.ai_repository.clear_pending(pending.contact_id)
        return reply

    def _build_context(self, profile_id: int) -> str:
        profile = self.coachline.get_profile(profile_id)
        local_date = datetime.now(ZoneInfo(profile.timezone)).date()
        sessions = self.coachline.list_sessions(profile_id)[-20:]
        lines = [f"Local date: {local_date}", "Known sessions:"]
        for session in sessions:
            lines.append(
                f"- id={session.id}; date={session.scheduled_for}; "
                f"status={session.status.value}; title={session.title}"
            )
        return "\n".join(lines)

    @classmethod
    def _format_today(cls, plans: list[SessionPlan]) -> str:
        if not plans:
            return "You have no planned workouts today."
        lines = ["Today's Coachline workout:"]
        for plan in plans:
            detail = cls._format_prescription(plan)
            lines.append(f"- {plan.session.title}{detail}")
        return "\n".join(lines)[:1600]

    @staticmethod
    def _format_prescription(plan: SessionPlan) -> str:
        prescription = plan.prescription
        if prescription is None:
            return ""
        if isinstance(prescription, LiftingPrescription):
            items = []
            for exercise in prescription.exercises:
                weight = (
                    f" @ {exercise.target_weight_kg:g} kg"
                    if exercise.target_weight_kg is not None
                    else ""
                )
                items.append(
                    f"{exercise.name} {exercise.sets}x{exercise.reps}{weight}"
                )
        else:
            items = []
            for segment in prescription.segments:
                if segment.distance_m is not None:
                    amount = f"{segment.distance_m} m"
                elif segment.duration_seconds is not None:
                    amount = (
                        f"{segment.duration_seconds // 60} min"
                        if segment.duration_seconds % 60 == 0
                        else f"{segment.duration_seconds} sec"
                    )
                else:
                    amount = ""
                pace = ""
                if segment.target_pace_seconds_per_km is not None:
                    minutes, seconds = divmod(
                        segment.target_pace_seconds_per_km, 60
                    )
                    pace = f" @ {minutes}:{seconds:02d}/km"
                items.append(f"{segment.kind.value} {amount}{pace}".strip())
        return ": " + "; ".join(items)
