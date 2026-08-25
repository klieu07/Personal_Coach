"""Timezone-aware reminder planning and provider-neutral delivery."""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.messaging.repository import MessagingNotFoundError
from app.messaging.service import MessagingService
from app.messaging.twilio import MessageDeliveryError, MessagingNotConfiguredError
from app.reminders.models import (
    ReminderCandidate,
    ReminderRunResult,
    ReminderSettings,
    ReminderSettingsUpdate,
)
from app.reminders.repository import ReminderRepository
from app.repository import NotFoundError
from app.schemas import SessionStatus
from app.services import CoachlineService


class ReminderService:
    """Synchronize durable jobs and deliver each eligible reminder once."""

    def __init__(
        self,
        coachline: CoachlineService,
        messaging: MessagingService,
        repository: ReminderRepository,
        *,
        max_attempts: int = 3,
        batch_size: int = 100,
    ) -> None:
        self.coachline = coachline
        self.messaging = messaging
        self.repository = repository
        self.max_attempts = max_attempts
        self.batch_size = batch_size

    def get_settings(self, profile_id: int) -> ReminderSettings:
        self.coachline.get_profile(profile_id)
        return self.repository.get_settings(profile_id)

    def save_settings(
        self, profile_id: int, payload: ReminderSettingsUpdate
    ) -> ReminderSettings:
        self.coachline.get_profile(profile_id)
        return self.repository.save_settings(profile_id, payload)

    def run_due(self, now: datetime | None = None) -> ReminderRunResult:
        current = self._as_utc(now or datetime.now(timezone.utc))
        result = ReminderRunResult()
        result.jobs_cancelled += self.repository.cancel_ineligible_jobs(current)

        for candidate in self.repository.list_candidates():
            local_today = current.astimezone(ZoneInfo(candidate.timezone)).date()
            if candidate.scheduled_for < local_today:
                result.jobs_cancelled += self.repository.cancel_session_job(
                    candidate.session_id, current
                )
                continue
            scheduled_at = self._scheduled_at(candidate)
            self.repository.sync_job(candidate, scheduled_at)
            result.jobs_synced += 1

        result.jobs_recovered = self.repository.recover_abandoned_jobs(
            current - timedelta(minutes=15), current
        )
        for _ in range(self.batch_size):
            job = self.repository.claim_due_job(current)
            if job is None:
                break
            try:
                session = self.coachline.get_session_for_profile(
                    job.profile_id, job.session_id
                )
                if session.status is not SessionStatus.PLANNED:
                    self.repository.mark_cancelled(job.id, current)
                    result.jobs_cancelled += 1
                    continue
                sent = self.messaging.send_to_profile(
                    job.profile_id,
                    self._message_body(
                        session.title, session.scheduled_for.isoformat()
                    ),
                )
            except (NotFoundError, MessagingNotFoundError):
                self.repository.mark_cancelled(job.id, current)
                result.jobs_cancelled += 1
            except (
                MessageDeliveryError,
                MessagingNotConfiguredError,
                RuntimeError,
            ) as exc:
                if job.attempt_count < self.max_attempts:
                    retry_at = current + timedelta(
                        minutes=5 * (2 ** (job.attempt_count - 1))
                    )
                    result.retrying += 1
                else:
                    retry_at = None
                    result.failed += 1
                self.repository.mark_delivery_failure(
                    job.id,
                    retry_at=retry_at,
                    error=str(exc),
                    now=current,
                )
            else:
                self.repository.mark_sent(job.id, sent.external_id, current)
                result.delivered += 1
        return result

    @classmethod
    def _scheduled_at(cls, candidate: ReminderCandidate) -> datetime:
        local_time = candidate.reminder_time
        local_date = candidate.scheduled_for
        if cls._is_quiet(
            local_time,
            candidate.quiet_hours_start,
            candidate.quiet_hours_end,
        ):
            if (
                candidate.quiet_hours_start > candidate.quiet_hours_end
                and local_time >= candidate.quiet_hours_start
            ):
                local_date += timedelta(days=1)
            local_time = candidate.quiet_hours_end
        local = datetime.combine(
            local_date, local_time, tzinfo=ZoneInfo(candidate.timezone)
        )
        return local.astimezone(timezone.utc)

    @staticmethod
    def _is_quiet(value: time, start: time, end: time) -> bool:
        if start == end:
            return False
        if start < end:
            return start <= value < end
        return value >= start or value < end

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("scheduler time must include a timezone")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _message_body(title: str, scheduled_for: str) -> str:
        return (
            f"Coachline reminder: {title} is planned for {scheduled_for}. "
            "Reply TODAY for the workout details."
        )
