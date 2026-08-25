"""Local audit and pending-confirmation persistence for AI actions."""

import json
from datetime import datetime, timezone
from typing import Protocol

from app.ai.models import AIInterpretationResult, PendingAction
from app.database import Database


class AIRepository(Protocol):
    def save_interpretation(
        self,
        provider: str,
        external_message_id: str,
        profile_id: int,
        result: AIInterpretationResult,
    ) -> None: ...

    def replace_pending(self, action: PendingAction) -> None: ...

    def get_pending(self, contact_id: int) -> PendingAction | None: ...

    def clear_pending(self, contact_id: int) -> None: ...


class SQLiteAIRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save_interpretation(
        self,
        provider: str,
        external_message_id: str,
        profile_id: int,
        result: AIInterpretationResult,
    ) -> None:
        with self.database.session() as connection:
            connection.execute(
                """
                INSERT INTO ai_interpretations
                    (provider, external_message_id, profile_id, model,
                     response_id, intent, interpretation_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    provider,
                    external_message_id,
                    profile_id,
                    result.model,
                    result.response_id,
                    result.interpretation.intent.value,
                    result.interpretation.model_dump_json(),
                ),
            )

    def replace_pending(self, action: PendingAction) -> None:
        with self.database.session() as connection:
            connection.execute(
                "DELETE FROM pending_actions WHERE contact_id = ?",
                (action.contact_id,),
            )
            connection.execute(
                """
                INSERT INTO pending_actions
                    (contact_id, action_json, confirmation_prompt, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    action.contact_id,
                    action.interpretation.model_dump_json(),
                    action.confirmation_prompt,
                    action.expires_at.isoformat(),
                ),
            )

    def get_pending(self, contact_id: int) -> PendingAction | None:
        with self.database.session() as connection:
            row = connection.execute(
                """
                SELECT action_json, confirmation_prompt, expires_at
                FROM pending_actions WHERE contact_id = ?
                """,
                (contact_id,),
            ).fetchone()
            if row is None:
                return None
            expires_at = datetime.fromisoformat(row["expires_at"])
            if expires_at <= datetime.now(timezone.utc):
                connection.execute(
                    "DELETE FROM pending_actions WHERE contact_id = ?",
                    (contact_id,),
                )
                return None
        return PendingAction(
            contact_id=contact_id,
            interpretation=json.loads(row["action_json"]),
            confirmation_prompt=row["confirmation_prompt"],
            expires_at=expires_at,
        )

    def clear_pending(self, contact_id: int) -> None:
        with self.database.session() as connection:
            connection.execute(
                "DELETE FROM pending_actions WHERE contact_id = ?",
                (contact_id,),
            )
