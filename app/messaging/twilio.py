"""Twilio implementation of Coachline's messaging boundary."""

from typing import Any

from twilio.request_validator import RequestValidator
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse

from app.messaging.config import TwilioSettings
from app.messaging.models import (
    InboundMessage,
    MessageProvider,
    OutboundMessage,
    SentMessage,
)


class MessagingNotConfiguredError(Exception):
    """Raised when provider credentials required for an operation are absent."""


class InvalidInboundMessageError(Exception):
    """Raised when a provider webhook lacks required message fields."""


class MessageDeliveryError(Exception):
    """Raised when a provider rejects an outbound message request."""


class TwilioAdapter:
    """Validate, normalize, reply to, and send Twilio SMS messages."""

    def __init__(self, settings: TwilioSettings, client: Any | None = None) -> None:
        if not settings.auth_token:
            raise MessagingNotConfiguredError(
                "TWILIO_AUTH_TOKEN is required for webhook validation"
            )
        self.settings = settings
        self.validator = RequestValidator(settings.auth_token)
        self.client = client
        if self.client is None and settings.can_send:
            self.client = Client(settings.account_sid, settings.auth_token)

    def validate_webhook(
        self, url: str, parameters: Any, signature: str
    ) -> bool:
        return self.validator.validate(url, parameters, signature)

    def parse_inbound(self, parameters: Any) -> InboundMessage:
        required = {
            "MessageSid": parameters.get("MessageSid"),
            "From": parameters.get("From"),
            "To": parameters.get("To"),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise InvalidInboundMessageError(
                f"Missing Twilio fields: {', '.join(missing)}"
            )
        return InboundMessage(
            provider=MessageProvider.TWILIO,
            external_id=str(required["MessageSid"]),
            from_address=str(required["From"]),
            to_address=str(required["To"]),
            body=str(parameters.get("Body", "")),
        )

    @staticmethod
    def render_twiml(reply_body: str | None) -> str:
        response = MessagingResponse()
        if reply_body:
            response.message(reply_body)
        return str(response)

    def send(self, message: OutboundMessage) -> SentMessage:
        if not self.settings.can_send or self.client is None:
            raise MessagingNotConfiguredError(
                "TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and "
                "TWILIO_FROM_NUMBER are required to send SMS"
            )
        try:
            result = self.client.messages.create(
                to=message.to_address,
                from_=self.settings.from_address,
                body=message.body,
            )
        except Exception as exc:
            raise MessageDeliveryError("Twilio could not queue the message") from exc
        return SentMessage(
            provider=MessageProvider.TWILIO,
            external_id=str(result.sid),
            from_address=str(self.settings.from_address),
            to_address=message.to_address,
            body=message.body,
            status=str(result.status),
        )
