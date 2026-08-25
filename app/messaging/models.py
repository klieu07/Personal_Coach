"""Provider-neutral message and contact models."""

from enum import StrEnum

from pydantic import BaseModel, Field


E164_PATTERN = r"^\+[1-9][0-9]{7,14}$"


class MessageProvider(StrEnum):
    TWILIO = "twilio"


class MessagingContactCreate(BaseModel):
    provider: MessageProvider
    address: str = Field(pattern=E164_PATTERN)


class MessagingContact(MessagingContactCreate):
    id: int
    profile_id: int


class InboundMessage(BaseModel):
    provider: MessageProvider
    external_id: str = Field(min_length=1, max_length=100)
    from_address: str = Field(pattern=E164_PATTERN)
    to_address: str = Field(pattern=E164_PATTERN)
    body: str = Field(max_length=1600)


class InboundOutcome(BaseModel):
    reply_body: str | None
    duplicate: bool = False


class OutboundMessage(BaseModel):
    to_address: str = Field(pattern=E164_PATTERN)
    body: str = Field(min_length=1, max_length=1600)


class MessageSendCreate(BaseModel):
    body: str = Field(min_length=1, max_length=1600)


class SentMessage(BaseModel):
    provider: MessageProvider
    external_id: str
    from_address: str
    to_address: str
    body: str
    status: str
