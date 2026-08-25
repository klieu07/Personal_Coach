"""SQLite persistence for reminder settings and idempotent jobs."""

from datetime import datetime
from typing import Protocol

from app.database import Database
from app.reminders.models import (
    ReminderCandidate,
    ReminderJob,
    ReminderJobStatus,
    ReminderSettings,
    ReminderSettingsUpdate,
)


class ReminderRepository(Protocol):
    def get_settings(self, profile_id: int) -> ReminderSettings: ...

    def save_settings(
        self, profile_id: int, payload: ReminderSettingsUpdate
    ) -> ReminderSettings: ...

    def list_candidates(self) -> list[ReminderCandidate]: ...

    def sync_job(
        self, candidate: ReminderCandidate, scheduled_at: datetime
    ) -> None: ...

    def cancel_ineligible_jobs(self, now: datetime) -> int: ...

    def cancel_session_job(self, session_id: int, now: datetime) -> int: ...

    def recover_abandoned_jobs(
        self, stale_before: datetime, now: datetime
    ) -> int: ...

    def claim_due_job(self, now: datetime) -> ReminderJob | None: ...

    def mark_sent(
        self, job_id: int, external_id: str, now: datetime
    ) -> None: ...

    def mark_cancelled(self, job_id: int, now: datetime) -> None: ...

    def mark_delivery_failure(
        self,
        job_id: int,
        *,
        retry_at: datetime | None,
        error: str,
        now: datetime,
    ) -> None: ...


class SQLiteReminderRepository:
    """Persist scheduler state so repeated runs do not duplicate reminders."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def get_settings(self, profile_id: int) -> ReminderSettings:
        with self.database.session() as connection:
            row = connection.execute(
                """
                SELECT profile_id, enabled, reminder_time,
                       quiet_hours_start, quiet_hours_end
                FROM reminder_settings
                WHERE profile_id = ?
                """,
                (profile_id,),
            ).fetchone()
        if row is None:
            return ReminderSettings(profile_id=profile_id)
        return ReminderSettings(**dict(row))

    def save_settings(
        self, profile_id: int, payload: ReminderSettingsUpdate
    ) -> ReminderSettings:
        values = payload.model_dump(mode="json")
        with self.database.session() as connection:
            connection.execute(
                """
                INSERT INTO reminder_settings
                    (profile_id, enabled, reminder_time,
                     quiet_hours_start, quiet_hours_end, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(profile_id) DO UPDATE SET
                    enabled = excluded.enabled,
                    reminder_time = excluded.reminder_time,
                    quiet_hours_start = excluded.quiet_hours_start,
                    quiet_hours_end = excluded.quiet_hours_end,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    profile_id,
                    values["enabled"],
                    values["reminder_time"],
                    values["quiet_hours_start"],
                    values["quiet_hours_end"],
                ),
            )
        return ReminderSettings(profile_id=profile_id, **payload.model_dump())

    def list_candidates(self) -> list[ReminderCandidate]:
        with self.database.session() as connection:
            rows = connection.execute(
                """
                SELECT p.id AS profile_id, s.id AS session_id,
                       s.scheduled_for, s.title, p.timezone,
                       r.reminder_time, r.quiet_hours_start,
                       r.quiet_hours_end
                FROM training_sessions AS s
                JOIN programs AS program ON program.id = s.program_id
                JOIN profiles AS p ON p.id = program.profile_id
                JOIN reminder_settings AS r ON r.profile_id = p.id
                WHERE s.status = 'planned'
                  AND r.enabled = 1
                  AND EXISTS (
                      SELECT 1
                      FROM messaging_contacts AS contact
                      WHERE contact.profile_id = p.id
                        AND contact.provider = 'twilio'
                  )
                ORDER BY s.scheduled_for, s.id
                """
            ).fetchall()
        return [ReminderCandidate(**dict(row)) for row in rows]

    def sync_job(
        self, candidate: ReminderCandidate, scheduled_at: datetime
    ) -> None:
        with self.database.session() as connection:
            connection.execute(
                """
                INSERT INTO reminder_jobs
                    (profile_id, session_id, scheduled_at, status, updated_at)
                VALUES (?, ?, ?, 'pending', CURRENT_TIMESTAMP)
                ON CONFLICT(session_id) DO UPDATE SET
                    profile_id = excluded.profile_id,
                    scheduled_at = excluded.scheduled_at,
                    status = CASE
                        WHEN reminder_jobs.status = 'cancelled' THEN 'pending'
                        ELSE reminder_jobs.status
                    END,
                    next_attempt_at = CASE
                        WHEN reminder_jobs.status = 'cancelled' THEN NULL
                        ELSE reminder_jobs.next_attempt_at
                    END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE reminder_jobs.status IN ('pending', 'cancelled')
                """,
                (
                    candidate.profile_id,
                    candidate.session_id,
                    scheduled_at.isoformat(),
                ),
            )

    def cancel_ineligible_jobs(self, now: datetime) -> int:
        with self.database.session() as connection:
            cursor = connection.execute(
                """
                UPDATE reminder_jobs
                SET status = 'cancelled', updated_at = ?
                WHERE status = 'pending'
                  AND (
                    NOT EXISTS (
                        SELECT 1
                        FROM training_sessions AS session
                        WHERE session.id = reminder_jobs.session_id
                          AND session.status = 'planned'
                    )
                    OR NOT EXISTS (
                        SELECT 1
                        FROM reminder_settings AS settings
                        WHERE settings.profile_id = reminder_jobs.profile_id
                          AND settings.enabled = 1
                    )
                    OR NOT EXISTS (
                        SELECT 1
                        FROM messaging_contacts AS contact
                        WHERE contact.profile_id = reminder_jobs.profile_id
                          AND contact.provider = 'twilio'
                    )
                  )
                """,
                (now.isoformat(),),
            )
        return cursor.rowcount

    def cancel_session_job(self, session_id: int, now: datetime) -> int:
        with self.database.session() as connection:
            cursor = connection.execute(
                """
                UPDATE reminder_jobs
                SET status = 'cancelled', updated_at = ?
                WHERE session_id = ? AND status = 'pending'
                """,
                (now.isoformat(), session_id),
            )
        return cursor.rowcount

    def recover_abandoned_jobs(
        self, stale_before: datetime, now: datetime
    ) -> int:
        with self.database.session() as connection:
            cursor = connection.execute(
                """
                UPDATE reminder_jobs
                SET status = 'pending', next_attempt_at = ?, updated_at = ?
                WHERE status = 'processing' AND updated_at < ?
                """,
                (now.isoformat(), now.isoformat(), stale_before.isoformat()),
            )
        return cursor.rowcount

    def claim_due_job(self, now: datetime) -> ReminderJob | None:
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT id, profile_id, session_id, scheduled_at,
                       status, attempt_count
                FROM reminder_jobs
                WHERE status = 'pending'
                  AND COALESCE(next_attempt_at, scheduled_at) <= ?
                ORDER BY COALESCE(next_attempt_at, scheduled_at), id
                LIMIT 1
                """,
                (now.isoformat(),),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                """
                UPDATE reminder_jobs
                SET status = 'processing', attempt_count = attempt_count + 1,
                    updated_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                (now.isoformat(), row["id"]),
            )
        values = dict(row)
        values.update(
            status=ReminderJobStatus.PROCESSING,
            attempt_count=row["attempt_count"] + 1,
        )
        return ReminderJob(**values)

    def mark_sent(
        self, job_id: int, external_id: str, now: datetime
    ) -> None:
        with self.database.session() as connection:
            connection.execute(
                """
                UPDATE reminder_jobs
                SET status = 'sent', sent_external_id = ?, last_error = NULL,
                    next_attempt_at = NULL, updated_at = ?
                WHERE id = ? AND status = 'processing'
                """,
                (external_id, now.isoformat(), job_id),
            )

    def mark_cancelled(self, job_id: int, now: datetime) -> None:
        with self.database.session() as connection:
            connection.execute(
                """
                UPDATE reminder_jobs
                SET status = 'cancelled', next_attempt_at = NULL, updated_at = ?
                WHERE id = ? AND status = 'processing'
                """,
                (now.isoformat(), job_id),
            )

    def mark_delivery_failure(
        self,
        job_id: int,
        *,
        retry_at: datetime | None,
        error: str,
        now: datetime,
    ) -> None:
        status = "pending" if retry_at is not None else "failed"
        with self.database.session() as connection:
            connection.execute(
                """
                UPDATE reminder_jobs
                SET status = ?, next_attempt_at = ?, last_error = ?,
                    updated_at = ?
                WHERE id = ? AND status = 'processing'
                """,
                (
                    status,
                    retry_at.isoformat() if retry_at else None,
                    error[:500],
                    now.isoformat(),
                    job_id,
                ),
            )
