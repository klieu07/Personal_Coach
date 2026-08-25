"""Persistence boundary for Coachline's training domain."""

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Protocol

from app.database import (
    DATABASE_INTEGRITY_ERRORS,
    Database,
    DatabaseConnection,
)
from app.schemas import (
    Discipline,
    LiftingExercise,
    LiftingPrescription,
    LiftingSetResult,
    Prescription,
    Profile,
    ProfileCreate,
    Program,
    ProgramCreate,
    RunningPrescription,
    RunningResultMetrics,
    RunningSegment,
    SessionCreate,
    SessionPlan,
    SessionStatus,
    TrainingSession,
    WorkoutResult,
    WorkoutResultCreate,
)


class NotFoundError(Exception):
    """Raised when a requested domain object does not exist."""


class ConflictError(Exception):
    """Raised when a requested state transition is invalid."""


class CoachlineRepository(Protocol):
    """Portable storage contract for the training domain."""

    def create_profile(self, payload: ProfileCreate) -> Profile: ...

    def get_profile(self, profile_id: int) -> Profile: ...

    def create_program(self, payload: ProgramCreate) -> Program: ...

    def get_program(self, program_id: int) -> Program: ...

    def list_programs(self, profile_id: int) -> list[Program]: ...

    def create_session(self, payload: SessionCreate) -> TrainingSession: ...

    def get_session(self, session_id: int) -> TrainingSession: ...

    def list_sessions(
        self, profile_id: int, status: SessionStatus | None = None
    ) -> list[TrainingSession]: ...

    def update_session_status(
        self, session_id: int, status: SessionStatus
    ) -> TrainingSession: ...

    def record_result(
        self, session_id: int, payload: WorkoutResultCreate
    ) -> WorkoutResult: ...

    def get_result(self, session_id: int) -> WorkoutResult: ...

    def save_prescription(
        self, session_id: int, payload: Prescription
    ) -> Prescription: ...

    def get_prescription(self, session_id: int) -> Prescription: ...

    def create_session_with_prescription(
        self, payload: SessionCreate, prescription: Prescription
    ) -> SessionPlan: ...


class SQLCoachlineRepository:
    """Store the training domain through the portable SQL boundary."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def create_profile(self, payload: ProfileCreate) -> Profile:
        with self.database.session() as connection:
            cursor = connection.execute(
                """
                INSERT INTO profiles (name, timezone) VALUES (?, ?)
                RETURNING id
                """,
                (payload.name, payload.timezone),
            )
            profile_id = int(cursor.fetchone()["id"])
            return Profile(id=profile_id, **payload.model_dump())

    def get_profile(self, profile_id: int) -> Profile:
        with self.database.session() as connection:
            row = connection.execute(
                "SELECT id, name, timezone FROM profiles WHERE id = ?",
                (profile_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(f"Profile {profile_id} was not found")
        return Profile(**dict(row))

    def create_program(self, payload: ProgramCreate) -> Program:
        self.get_profile(payload.profile_id)
        with self.database.session() as connection:
            cursor = connection.execute(
                """
                INSERT INTO programs (profile_id, name, discipline)
                VALUES (?, ?, ?)
                RETURNING id
                """,
                (payload.profile_id, payload.name, payload.discipline.value),
            )
            program_id = int(cursor.fetchone()["id"])
            return Program(id=program_id, active=True, **payload.model_dump())

    def list_programs(self, profile_id: int) -> list[Program]:
        self.get_profile(profile_id)
        with self.database.session() as connection:
            rows = connection.execute(
                """
                SELECT id, profile_id, name, discipline, active
                FROM programs
                WHERE profile_id = ?
                ORDER BY id
                """,
                (profile_id,),
            ).fetchall()
        return [self._program_from_row(row) for row in rows]

    def get_program(self, program_id: int) -> Program:
        with self.database.session() as connection:
            row = connection.execute(
                """
                SELECT id, profile_id, name, discipline, active
                FROM programs
                WHERE id = ?
                """,
                (program_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(f"Program {program_id} was not found")
        return self._program_from_row(row)

    def create_session(self, payload: SessionCreate) -> TrainingSession:
        self.get_program(payload.program_id)
        with self.database.session() as connection:
            cursor = connection.execute(
                """
                INSERT INTO training_sessions
                    (program_id, scheduled_for, title, notes)
                VALUES (?, ?, ?, ?)
                RETURNING id
                """,
                (
                    payload.program_id,
                    payload.scheduled_for.isoformat(),
                    payload.title,
                    payload.notes,
                ),
            )
            session_id = int(cursor.fetchone()["id"])
            return TrainingSession(
                id=session_id,
                status=SessionStatus.PLANNED,
                **payload.model_dump(),
            )

    def get_session(self, session_id: int) -> TrainingSession:
        with self.database.session() as connection:
            row = connection.execute(
                """
                SELECT id, program_id, scheduled_for, title, status, notes
                FROM training_sessions
                WHERE id = ?
                """,
                (session_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(f"Session {session_id} was not found")
        return TrainingSession(**dict(row))

    def save_prescription(
        self, session_id: int, payload: Prescription
    ) -> Prescription:
        session = self.get_session(session_id)
        program = self.get_program(session.program_id)
        self._ensure_discipline_matches(program, payload)

        with self.database.session() as connection:
            connection.execute(
                "DELETE FROM lifting_exercises WHERE session_id = ?", (session_id,)
            )
            connection.execute(
                "DELETE FROM running_segments WHERE session_id = ?", (session_id,)
            )
            self._insert_prescription(connection, session_id, payload)
        return payload

    def get_prescription(self, session_id: int) -> Prescription:
        session = self.get_session(session_id)
        program = self.get_program(session.program_id)

        with self.database.session() as connection:
            if program.discipline is Discipline.LIFTING:
                rows = connection.execute(
                    """
                    SELECT name, sets, reps, target_weight_kg, rest_seconds
                    FROM lifting_exercises
                    WHERE session_id = ?
                    ORDER BY position
                    """,
                    (session_id,),
                ).fetchall()
                if rows:
                    return LiftingPrescription(
                        exercises=[LiftingExercise(**dict(row)) for row in rows]
                    )
            else:
                rows = connection.execute(
                    """
                    SELECT kind, distance_m, duration_seconds,
                           target_pace_seconds_per_km
                    FROM running_segments
                    WHERE session_id = ?
                    ORDER BY position
                    """,
                    (session_id,),
                ).fetchall()
                if rows:
                    return RunningPrescription(
                        segments=[RunningSegment(**dict(row)) for row in rows]
                    )

        raise NotFoundError(f"Session {session_id} has no prescription")

    def create_session_with_prescription(
        self, payload: SessionCreate, prescription: Prescription
    ) -> SessionPlan:
        program = self.get_program(payload.program_id)
        self._ensure_discipline_matches(program, prescription)

        with self.database.session() as connection:
            cursor = connection.execute(
                """
                INSERT INTO training_sessions
                    (program_id, scheduled_for, title, notes)
                VALUES (?, ?, ?, ?)
                RETURNING id
                """,
                (
                    payload.program_id,
                    payload.scheduled_for.isoformat(),
                    payload.title,
                    payload.notes,
                ),
            )
            session_id = int(cursor.fetchone()["id"])
            session = TrainingSession(
                id=session_id,
                status=SessionStatus.PLANNED,
                **payload.model_dump(),
            )
            self._insert_prescription(connection, session.id, prescription)

        return SessionPlan(session=session, prescription=prescription)

    def list_sessions(
        self, profile_id: int, status: SessionStatus | None = None
    ) -> list[TrainingSession]:
        self.get_profile(profile_id)
        query = """
            SELECT s.id, s.program_id, s.scheduled_for, s.title, s.status, s.notes
            FROM training_sessions AS s
            JOIN programs AS p ON p.id = s.program_id
            WHERE p.profile_id = ?
        """
        parameters: list[object] = [profile_id]
        if status is not None:
            query += " AND s.status = ?"
            parameters.append(status.value)
        query += " ORDER BY s.scheduled_for, s.id"

        with self.database.session() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [TrainingSession(**dict(row)) for row in rows]

    def update_session_status(
        self, session_id: int, status: SessionStatus
    ) -> TrainingSession:
        session = self.get_session(session_id)
        if session.status is SessionStatus.COMPLETED and status is not session.status:
            raise ConflictError("A completed session cannot be reopened or skipped")

        with self.database.session() as connection:
            connection.execute(
                "UPDATE training_sessions SET status = ? WHERE id = ?",
                (status.value, session_id),
            )
        return session.model_copy(update={"status": status})

    def record_result(
        self, session_id: int, payload: WorkoutResultCreate
    ) -> WorkoutResult:
        session = self.get_session(session_id)
        if session.status is SessionStatus.SKIPPED:
            raise ConflictError("A skipped session must be replanned before completion")

        completed_at = payload.completed_at or datetime.now(timezone.utc)
        try:
            with self.database.session() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO workout_results (session_id, summary, completed_at)
                    VALUES (?, ?, ?)
                    RETURNING id
                    """,
                    (session_id, payload.summary, completed_at.isoformat()),
                )
                result_id = int(cursor.fetchone()["id"])
                connection.execute(
                    """
                    UPDATE training_sessions SET status = 'completed'
                    WHERE id = ?
                    """,
                    (session_id,),
                )
                for position, result in enumerate(payload.lifting_sets, start=1):
                    connection.execute(
                        """
                        INSERT INTO lifting_set_results
                            (result_id, position, exercise_name, set_number,
                             reps, weight_kg)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            result_id,
                            position,
                            result.exercise_name,
                            result.set_number,
                            result.reps,
                            result.weight_kg,
                        ),
                    )
                if payload.running_metrics is not None:
                    metrics = payload.running_metrics
                    connection.execute(
                        """
                        INSERT INTO running_result_metrics
                            (result_id, distance_m, duration_seconds,
                             average_heart_rate)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            result_id,
                            metrics.distance_m,
                            metrics.duration_seconds,
                            metrics.average_heart_rate,
                        ),
                    )
        except DATABASE_INTEGRITY_ERRORS as exc:
            raise ConflictError(f"Session {session_id} already has a result") from exc

        return WorkoutResult(
            id=result_id,
            session_id=session_id,
            summary=payload.summary,
            completed_at=completed_at,
            lifting_sets=payload.lifting_sets,
            running_metrics=payload.running_metrics,
        )

    def get_result(self, session_id: int) -> WorkoutResult:
        self.get_session(session_id)
        with self.database.session() as connection:
            row = connection.execute(
                """
                SELECT id, session_id, summary, completed_at
                FROM workout_results
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError(f"Session {session_id} has no result")

            set_rows = connection.execute(
                """
                SELECT exercise_name, set_number, reps, weight_kg
                FROM lifting_set_results
                WHERE result_id = ?
                ORDER BY position
                """,
                (row["id"],),
            ).fetchall()
            metrics_row = connection.execute(
                """
                SELECT distance_m, duration_seconds, average_heart_rate
                FROM running_result_metrics
                WHERE result_id = ?
                """,
                (row["id"],),
            ).fetchone()

        return WorkoutResult(
            **dict(row),
            lifting_sets=[LiftingSetResult(**dict(item)) for item in set_rows],
            running_metrics=(
                RunningResultMetrics(**dict(metrics_row))
                if metrics_row is not None
                else None
            ),
        )

    @staticmethod
    def _ensure_discipline_matches(
        program: Program, prescription: Prescription
    ) -> None:
        if program.discipline is not prescription.discipline:
            raise ConflictError(
                f"A {program.discipline.value} program requires a "
                f"{program.discipline.value} prescription"
            )

    @staticmethod
    def _insert_prescription(
        connection: DatabaseConnection,
        session_id: int,
        prescription: Prescription,
    ) -> None:
        if isinstance(prescription, LiftingPrescription):
            for position, exercise in enumerate(prescription.exercises, start=1):
                connection.execute(
                    """
                    INSERT INTO lifting_exercises
                        (session_id, position, name, sets, reps,
                         target_weight_kg, rest_seconds)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        position,
                        exercise.name,
                        exercise.sets,
                        exercise.reps,
                        exercise.target_weight_kg,
                        exercise.rest_seconds,
                    ),
                )
        else:
            for position, segment in enumerate(prescription.segments, start=1):
                connection.execute(
                    """
                    INSERT INTO running_segments
                        (session_id, position, kind, distance_m,
                         duration_seconds, target_pace_seconds_per_km)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        position,
                        segment.kind.value,
                        segment.distance_m,
                        segment.duration_seconds,
                        segment.target_pace_seconds_per_km,
                    ),
                )

    @staticmethod
    def _program_from_row(row: Mapping[str, Any]) -> Program:
        values = dict(row)
        values["active"] = bool(values["active"])
        values["discipline"] = Discipline(values["discipline"])
        return Program(**values)
