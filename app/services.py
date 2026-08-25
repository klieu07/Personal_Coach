"""Application service boundary for Coachline workflows."""

from app.repository import CoachlineRepository
from app.schemas import (
    Profile,
    ProfileCreate,
    Program,
    ProgramCreate,
    SessionCreate,
    SessionStatus,
    TrainingSession,
    WorkoutResult,
    WorkoutResultCreate,
)


class CoachlineService:
    """Coordinate domain workflows independently of HTTP and messaging."""

    def __init__(self, repository: CoachlineRepository) -> None:
        self.repository = repository

    def create_profile(self, payload: ProfileCreate) -> Profile:
        return self.repository.create_profile(payload)

    def get_profile(self, profile_id: int) -> Profile:
        return self.repository.get_profile(profile_id)

    def create_program(self, payload: ProgramCreate) -> Program:
        return self.repository.create_program(payload)

    def list_programs(self, profile_id: int) -> list[Program]:
        return self.repository.list_programs(profile_id)

    def create_session(self, payload: SessionCreate) -> TrainingSession:
        return self.repository.create_session(payload)

    def get_session(self, session_id: int) -> TrainingSession:
        return self.repository.get_session(session_id)

    def list_sessions(
        self, profile_id: int, status: SessionStatus | None = None
    ) -> list[TrainingSession]:
        return self.repository.list_sessions(profile_id, status)

    def update_session_status(
        self, session_id: int, status: SessionStatus
    ) -> TrainingSession:
        return self.repository.update_session_status(session_id, status)

    def record_result(
        self, session_id: int, payload: WorkoutResultCreate
    ) -> WorkoutResult:
        return self.repository.record_result(session_id, payload)
