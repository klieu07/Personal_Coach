"""Portable SQLite and PostgreSQL connection and migration support."""

import sqlite3
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

import psycopg
from psycopg.rows import dict_row


DATABASE_INTEGRITY_ERRORS = (sqlite3.IntegrityError, psycopg.IntegrityError)
MIGRATION_LOCK_ID = 1_384_987_072
REMINDER_CLAIM_LOCK_ID = 1_384_987_073


class DatabaseBackend(StrEnum):
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"


class DatabaseCursor(Protocol):
    rowcount: int

    def fetchone(self) -> Mapping[str, Any] | None: ...

    def fetchall(self) -> list[Mapping[str, Any]]: ...


class DatabaseConnection(Protocol):
    def execute(
        self, query: str, parameters: Sequence[object] = ()
    ) -> DatabaseCursor: ...

    def execute_script(self, script: str) -> None: ...

    def acquire_migration_lock(self) -> None: ...

    def acquire_reminder_claim_lock(self) -> None: ...


class _SQLiteConnection:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def execute(
        self, query: str, parameters: Sequence[object] = ()
    ) -> sqlite3.Cursor:
        sqlite_parameters = tuple(
            value.isoformat() if isinstance(value, datetime) else value
            for value in parameters
        )
        return self.connection.execute(query, sqlite_parameters)

    def execute_script(self, script: str) -> None:
        self.connection.executescript(script)

    def acquire_migration_lock(self) -> None:
        return None

    def acquire_reminder_claim_lock(self) -> None:
        self.connection.execute("BEGIN IMMEDIATE")


class _PostgreSQLConnection:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def execute(
        self, query: str, parameters: Sequence[object] = ()
    ) -> DatabaseCursor:
        return self.connection.execute(
            self._translate_placeholders(query), tuple(parameters)
        )

    def execute_script(self, script: str) -> None:
        for statement in script.split(";"):
            if statement.strip():
                self.connection.execute(statement)

    def acquire_migration_lock(self) -> None:
        self.connection.execute(
            "SELECT pg_advisory_xact_lock(%s)", (MIGRATION_LOCK_ID,)
        )

    def acquire_reminder_claim_lock(self) -> None:
        self.connection.execute(
            "SELECT pg_advisory_xact_lock(%s)", (REMINDER_CLAIM_LOCK_ID,)
        )

    @staticmethod
    def _translate_placeholders(query: str) -> str:
        """Translate Coachline's portable qmark parameters for Psycopg."""

        return query.replace("?", "%s")


class Database:
    """Select a database backend and provide transaction-scoped sessions."""

    def __init__(
        self,
        source: str | Path,
        *,
        postgres_connect: Callable[..., Any] | None = None,
    ) -> None:
        raw_source = str(source)
        if raw_source.startswith(("postgresql://", "postgres://")):
            self.backend = DatabaseBackend.POSTGRESQL
            self.dsn = self._normalize_postgres_url(raw_source)
            self.path: Path | None = None
        else:
            self.backend = DatabaseBackend.SQLITE
            self.path = Path(source)
            self.dsn = None
        self._postgres_connect = postgres_connect or psycopg.connect

    @contextmanager
    def session(self) -> Iterator[DatabaseConnection]:
        """Provide a committed transaction or roll it back on failure."""

        if self.backend is DatabaseBackend.SQLITE:
            assert self.path is not None
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            try:
                with connection:
                    yield _SQLiteConnection(connection)
            finally:
                connection.close()
            return

        assert self.dsn is not None
        with self._postgres_connect(
            self.dsn,
            row_factory=dict_row,
            connect_timeout=5,
        ) as connection:
            yield _PostgreSQLConnection(connection)

    def migrate(self) -> None:
        migrations_dir = Path(__file__).with_name("migrations")
        if self.backend is DatabaseBackend.POSTGRESQL:
            migrations_dir = migrations_dir / "postgresql"

        with self.session() as connection:
            connection.acquire_migration_lock()
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            applied = {
                row["version"]
                for row in connection.execute(
                    "SELECT version FROM schema_migrations"
                ).fetchall()
            }

            for migration in sorted(migrations_dir.glob("[0-9][0-9][0-9]_*.sql")):
                if migration.stem in applied:
                    continue
                connection.execute_script(migration.read_text(encoding="utf-8"))
                connection.execute(
                    "INSERT INTO schema_migrations (version) VALUES (?)",
                    (migration.stem,),
                )

    def ping(self) -> None:
        with self.session() as connection:
            connection.execute("SELECT 1 AS healthy").fetchone()

    @staticmethod
    def _normalize_postgres_url(value: str) -> str:
        if value.startswith("postgres://"):
            return "postgresql://" + value.removeprefix("postgres://")
        return value
