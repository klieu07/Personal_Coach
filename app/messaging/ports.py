"""Contracts implemented by messaging providers."""

from typing import Protocol

from app.messaging.models import OutboundMessage, SentMessage


class MessageSender(Protocol):
    def send(self, message: OutboundMessage) -> SentMessage: ...
