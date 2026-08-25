"""Provider-neutral messaging application workflows."""

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
from app.schemas import LiftingPrescription, SessionPlan
from app.services import CoachlineService


class MessagingService:
    """Route normalized messages without depending on a provider webhook."""

    def __init__(
        self,
        coachline: CoachlineService,
        repository: MessagingRepository,
        sender: MessageSender | None = None,
    ) -> None:
        self.coachline = coachline
        self.repository = repository
        self.sender = sender

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
            reply = self._route_command(contact.profile_id, message.body)

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

    def _route_command(self, profile_id: int, body: str) -> str:
        command = " ".join(body.casefold().split())
        if command in {"today", "workout", "today's workout", "todays workout"}:
            plans = self.coachline.todays_workouts(profile_id)
            return self._format_today(plans)
        return (
            "Coachline received your message. Reply TODAY to see your planned "
            "workouts. Free-form AI coaching is not enabled yet."
        )

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
