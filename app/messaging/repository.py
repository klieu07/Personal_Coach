"""Portable SQL storage for contacts and message idempotency."""

from typing import Protocol

from app.database import DATABASE_INTEGRITY_ERRORS, Database
from app.messaging.models import (
    InboundMessage,
    MessagingContact,
    MessagingContactCreate,
    SentMessage,
)


class MessagingNotFoundError(Exception):
    """Raised when a messaging contact does not exist."""


class MessagingConflictError(Exception):
    """Raised when a contact or provider message already exists."""


class MessagingRepository(Protocol):
    def add_contact(
        self, profile_id: int, payload: MessagingContactCreate
    ) -> MessagingContact: ...

    def get_contact_for_profile(
        self, profile_id: int, provider: str
    ) -> MessagingContact: ...

    def find_contact(
        self, provider: str, address: str
    ) -> MessagingContact | None: ...

    def get_inbound_reply(
        self, provider: str, external_id: str
    ) -> tuple[bool, str | None]: ...

    def save_inbound(
        self,
        message: InboundMessage,
        contact_id: int | None,
        reply_body: str | None,
    ) -> None: ...

    def save_outbound(self, contact_id: int, message: SentMessage) -> None: ...


class SQLMessagingRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def add_contact(
        self, profile_id: int, payload: MessagingContactCreate
    ) -> MessagingContact:
        try:
            with self.database.session() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO messaging_contacts (profile_id, provider, address)
                    VALUES (?, ?, ?)
                    RETURNING id
                    """,
                    (profile_id, payload.provider.value, payload.address),
                )
                contact_id = int(cursor.fetchone()["id"])
        except DATABASE_INTEGRITY_ERRORS as exc:
            raise MessagingConflictError(
                "That messaging address or profile provider is already linked"
            ) from exc
        return MessagingContact(
            id=contact_id, profile_id=profile_id, **payload.model_dump()
        )

    def get_contact_for_profile(
        self, profile_id: int, provider: str
    ) -> MessagingContact:
        with self.database.session() as connection:
            row = connection.execute(
                """
                SELECT id, profile_id, provider, address
                FROM messaging_contacts
                WHERE profile_id = ? AND provider = ?
                """,
                (profile_id, provider),
            ).fetchone()
        if row is None:
            raise MessagingNotFoundError(
                f"Profile {profile_id} has no {provider} contact"
            )
        return MessagingContact(**dict(row))

    def find_contact(
        self, provider: str, address: str
    ) -> MessagingContact | None:
        with self.database.session() as connection:
            row = connection.execute(
                """
                SELECT id, profile_id, provider, address
                FROM messaging_contacts
                WHERE provider = ? AND address = ?
                """,
                (provider, address),
            ).fetchone()
        return MessagingContact(**dict(row)) if row is not None else None

    def get_inbound_reply(
        self, provider: str, external_id: str
    ) -> tuple[bool, str | None]:
        with self.database.session() as connection:
            row = connection.execute(
                """
                SELECT reply_body FROM inbound_messages
                WHERE provider = ? AND external_id = ?
                """,
                (provider, external_id),
            ).fetchone()
        if row is None:
            return False, None
        return True, row["reply_body"]

    def save_inbound(
        self,
        message: InboundMessage,
        contact_id: int | None,
        reply_body: str | None,
    ) -> None:
        try:
            with self.database.session() as connection:
                connection.execute(
                    """
                    INSERT INTO inbound_messages
                        (provider, external_id, contact_id, from_address,
                         to_address, body, reply_body)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        message.provider.value,
                        message.external_id,
                        contact_id,
                        message.from_address,
                        message.to_address,
                        message.body,
                        reply_body,
                    ),
                )
        except DATABASE_INTEGRITY_ERRORS as exc:
            raise MessagingConflictError("Inbound message already exists") from exc

    def save_outbound(self, contact_id: int, message: SentMessage) -> None:
        with self.database.session() as connection:
            connection.execute(
                """
                INSERT INTO outbound_messages
                    (provider, external_id, contact_id, from_address,
                     to_address, body, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.provider.value,
                    message.external_id,
                    contact_id,
                    message.from_address,
                    message.to_address,
                    message.body,
                    message.status,
                ),
            )
