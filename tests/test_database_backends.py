from pathlib import Path
from typing import Any

from psycopg.rows import dict_row

from app.database import Database, DatabaseBackend


class FakeCursor:
    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        *,
        rowcount: int = 0,
    ) -> None:
        self.rows = rows or []
        self.rowcount = rowcount

    def fetchone(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows


class FakePostgresState:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.applied: set[str] = set()
        self.connect_calls: list[dict[str, Any]] = []


class FakePostgresConnection:
    def __init__(self, state: FakePostgresState) -> None:
        self.state = state
        self.exit_error: object | None = None

    def __enter__(self) -> "FakePostgresConnection":
        return self

    def __exit__(
        self,
        error_type: object,
        error: object,
        traceback: object,
    ) -> None:
        self.exit_error = error

    def execute(
        self, query: str, parameters: tuple[object, ...] = ()
    ) -> FakeCursor:
        normalized = " ".join(query.split())
        self.state.executed.append((normalized, tuple(parameters)))
        if normalized == "SELECT version FROM schema_migrations":
            return FakeCursor(
                [{"version": version} for version in sorted(self.state.applied)]
            )
        if normalized.startswith("INSERT INTO schema_migrations"):
            self.state.applied.add(str(parameters[0]))
        if normalized == "SELECT %s AS value":
            return FakeCursor([{"value": parameters[0]}])
        return FakeCursor()


def fake_connect_factory(state: FakePostgresState) -> Any:
    def connect(dsn: str, **options: Any) -> FakePostgresConnection:
        state.connect_calls.append({"dsn": dsn, **options})
        return FakePostgresConnection(state)

    return connect


def test_sqlite_remains_the_default_file_backend(tmp_path: Path) -> None:
    database = Database(tmp_path / "coachline.sqlite3")

    assert database.backend is DatabaseBackend.SQLITE
    assert database.path == tmp_path / "coachline.sqlite3"
    assert database.dsn is None


def test_postgres_url_uses_dict_rows_transactions_and_qmark_translation() -> None:
    state = FakePostgresState()
    database = Database(
        "postgres://coachline:secret@database/coachline",
        postgres_connect=fake_connect_factory(state),
    )

    with database.session() as connection:
        row = connection.execute("SELECT ? AS value", (7,)).fetchone()

    assert database.backend is DatabaseBackend.POSTGRESQL
    assert database.dsn == (
        "postgresql://coachline:secret@database/coachline"
    )
    assert row == {"value": 7}
    assert state.executed == [("SELECT %s AS value", (7,))]
    assert state.connect_calls == [
        {
            "dsn": "postgresql://coachline:secret@database/coachline",
            "row_factory": dict_row,
            "connect_timeout": 5,
        }
    ]


def test_postgres_migrations_are_native_locked_and_idempotent() -> None:
    state = FakePostgresState()
    database = Database(
        "postgresql://database/coachline",
        postgres_connect=fake_connect_factory(state),
    )

    database.migrate()
    first_run_statements = list(state.executed)
    database.migrate()
    second_run_statements = state.executed[len(first_run_statements) :]

    assert state.applied == {
        "001_training_core",
        "002_structured_training",
        "003_messaging",
        "004_ai_interpretation",
        "005_proactive_reminders",
        "006_nutrition_ledger",
    }
    all_sql = "\n".join(query for query, _ in first_run_statements)
    assert "pg_advisory_xact_lock" in all_sql
    assert "BIGSERIAL PRIMARY KEY" in all_sql
    assert "AUTOINCREMENT" not in all_sql
    assert not any(
        query.startswith("CREATE TABLE profiles")
        for query, _ in second_run_statements
    )
