"""Persistence boundary for Coachline's training domain."""

import sqlite3
from datetime import datetime, timezone
from typing import Protocol

from app.database import Database
from app.schemas import (
    Discipline,
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


class NotFoundError(Exception):
    """Raised when a requested domain object does not exist."""


class ConflictError(Exception):
    """Raised when a requested state transition is invalid."""


class CoachlineRepository(Protocol):
    """Storage contract that a future PostgreSQL adapter can implement."""

    def create_profile(self, payload: ProfileCreate) -> Profile: ...

    def get_profile(self, profile_id: int) -> Profile: ...

    def create_program(self, payload: ProgramCreate) -> Program: ...

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


class SQLiteCoachlineRepository:
    """Store the training domain in SQLite behind a replaceable boundary."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def create_profile(self, payload: ProfileCreate) -> Profile:
        with self.database.session() as connection:
            cursor = connection.execute(
                "INSERT INTO profiles (name, timezone) VALUES (?, ?)",
                (payload.name, payload.timezone),
            )
            return Profile(id=cursor.lastrowid, **payload.model_dump())

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
                """,
                (payload.profile_id, payload.name, payload.discipline.value),
            )
            return Program(id=cursor.lastrowid, active=True, **payload.model_dump())

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

    def create_session(self, payload: SessionCreate) -> TrainingSession:
        self._get_program(payload.program_id)
        with self.database.session() as connection:
            cursor = connection.execute(
                """
                INSERT INTO training_sessions
                    (program_id, scheduled_for, title, notes)
                VALUES (?, ?, ?, ?)
                """,
                (
                    payload.program_id,
                    payload.scheduled_for.isoformat(),
                    payload.title,
                    payload.notes,
                ),
            )
            return TrainingSession(
                id=cursor.lastrowid,
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
                    """,
                    (session_id, payload.summary, completed_at.isoformat()),
                )
                connection.execute(
                    """
                    UPDATE training_sessions SET status = 'completed'
                    WHERE id = ?
                    """,
                    (session_id,),
                )
        except sqlite3.IntegrityError as exc:
            raise ConflictError(f"Session {session_id} already has a result") from exc

        return WorkoutResult(
            id=cursor.lastrowid,
            session_id=session_id,
            summary=payload.summary,
            completed_at=completed_at,
        )

    def _get_program(self, program_id: int) -> Program:
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

    @staticmethod
    def _program_from_row(row: sqlite3.Row) -> Program:
        values = dict(row)
        values["active"] = bool(values["active"])
        values["discipline"] = Discipline(values["discipline"])
        return Program(**values)
