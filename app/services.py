"""Application service boundary for Coachline workflows."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.repository import (
    CoachlineRepository,
    ConflictError,
    NotFoundError,
)
from app.schemas import (
    Discipline,
    LiftingPrescription,
    Prescription,
    Profile,
    ProfileCreate,
    Program,
    ProgramCreate,
    ProgressionCreate,
    RunningPrescription,
    RunningSegmentKind,
    SessionCreate,
    SessionPlan,
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

    def get_session_for_profile(
        self, profile_id: int, session_id: int
    ) -> TrainingSession:
        session = self.repository.get_session(session_id)
        program = self.repository.get_program(session.program_id)
        if program.profile_id != profile_id:
            raise NotFoundError(f"Session {session_id} was not found")
        return session

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
        session = self.repository.get_session(session_id)
        program = self.repository.get_program(session.program_id)
        if (
            program.discipline is Discipline.LIFTING
            and payload.running_metrics is not None
        ):
            raise ConflictError("A lifting session cannot store running metrics")
        if program.discipline is Discipline.RUNNING and payload.lifting_sets:
            raise ConflictError("A running session cannot store lifting sets")
        if payload.lifting_sets:
            try:
                prescription = self.repository.get_prescription(session_id)
            except NotFoundError as exc:
                raise ConflictError(
                    "Structured lifting sets require a lifting prescription"
                ) from exc
            if not isinstance(prescription, LiftingPrescription):
                raise ConflictError(
                    "Structured lifting sets require a lifting prescription"
                )
            prescribed_sets = {
                exercise.name: exercise.sets
                for exercise in prescription.exercises
            }
            for completed_set in payload.lifting_sets:
                maximum = prescribed_sets.get(completed_set.exercise_name)
                if maximum is None:
                    raise ConflictError(
                        f"{completed_set.exercise_name} is not in the prescription"
                    )
                if completed_set.set_number > maximum:
                    raise ConflictError(
                        f"{completed_set.exercise_name} has only "
                        f"{maximum} prescribed sets"
                    )
        return self.repository.record_result(session_id, payload)

    def get_result(self, session_id: int) -> WorkoutResult:
        return self.repository.get_result(session_id)

    def save_prescription(
        self, session_id: int, payload: Prescription
    ) -> Prescription:
        session = self.repository.get_session(session_id)
        if session.status is not SessionStatus.PLANNED:
            raise ConflictError("Only a planned session can change its prescription")
        return self.repository.save_prescription(session_id, payload)

    def get_prescription(self, session_id: int) -> Prescription:
        return self.repository.get_prescription(session_id)

    def todays_workouts(
        self, profile_id: int, on_date: date | None = None
    ) -> list[SessionPlan]:
        profile = self.repository.get_profile(profile_id)
        target_date = on_date or datetime.now(ZoneInfo(profile.timezone)).date()
        sessions = self.repository.list_sessions(profile_id, SessionStatus.PLANNED)
        plans: list[SessionPlan] = []
        for session in sessions:
            if session.scheduled_for != target_date:
                continue
            try:
                prescription = self.repository.get_prescription(session.id)
            except NotFoundError:
                prescription = None
            plans.append(SessionPlan(session=session, prescription=prescription))
        return plans

    def progress_session(
        self, session_id: int, payload: ProgressionCreate
    ) -> SessionPlan:
        source = self.repository.get_session(session_id)
        if source.status is not SessionStatus.COMPLETED:
            raise ConflictError("Only a completed session can be progressed")

        prescription = self.repository.get_prescription(session_id)
        if isinstance(prescription, LiftingPrescription):
            exercises = []
            for exercise in prescription.exercises:
                weight = exercise.target_weight_kg
                exercises.append(
                    exercise.model_copy(
                        update={
                            "target_weight_kg": (
                                round(weight + payload.lifting_weight_increment_kg, 3)
                                if weight is not None
                                else None
                            )
                        }
                    )
                )
            next_prescription: Prescription = LiftingPrescription(
                exercises=exercises
            )
        else:
            multiplier = 1 + payload.running_increase_percent / 100
            segments = []
            for segment in prescription.segments:
                updates: dict[str, int] = {}
                if segment.kind in {
                    RunningSegmentKind.WORK,
                    RunningSegmentKind.STEADY,
                }:
                    if segment.distance_m is not None:
                        updates["distance_m"] = round(segment.distance_m * multiplier)
                    elif segment.duration_seconds is not None:
                        updates["duration_seconds"] = round(
                            segment.duration_seconds * multiplier
                        )
                segments.append(segment.model_copy(update=updates))
            next_prescription = RunningPrescription(segments=segments)

        next_session = SessionCreate(
            program_id=source.program_id,
            scheduled_for=payload.scheduled_for,
            title=source.title,
            notes=source.notes,
        )
        return self.repository.create_session_with_prescription(
            next_session, next_prescription
        )
