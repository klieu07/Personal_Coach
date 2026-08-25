from pathlib import Path

from fastapi.testclient import TestClient

from app.database import Database
from app.main import create_app


def make_client(database_path: Path) -> TestClient:
    return TestClient(create_app(database_path))


def create_session(
    client: TestClient, discipline: str, scheduled_for: str
) -> tuple[int, int]:
    profile = client.post(
        "/profiles", json={"name": "Kai", "timezone": "Asia/Shanghai"}
    ).json()
    program = client.post(
        "/programs",
        json={
            "profile_id": profile["id"],
            "name": f"My {discipline.title()} Plan",
            "discipline": discipline,
        },
    ).json()
    session = client.post(
        "/sessions",
        json={
            "program_id": program["id"],
            "scheduled_for": scheduled_for,
            "title": f"Structured {discipline} session",
        },
    ).json()
    return profile["id"], session["id"]


def test_lifting_prescription_result_and_progression(tmp_path: Path) -> None:
    with make_client(tmp_path / "coachline.sqlite3") as client:
        profile_id, session_id = create_session(client, "lifting", "2026-08-27")
        prescription = {
            "discipline": "lifting",
            "exercises": [
                {
                    "name": "Back Squat",
                    "sets": 3,
                    "reps": 5,
                    "target_weight_kg": 100,
                    "rest_seconds": 180,
                },
                {
                    "name": "Pull-up",
                    "sets": 3,
                    "reps": 8,
                    "target_weight_kg": None,
                    "rest_seconds": 120,
                },
            ],
        }

        saved = client.put(
            f"/sessions/{session_id}/prescription", json=prescription
        )
        assert saved.status_code == 200
        assert saved.json() == prescription

        today = client.get(
            f"/profiles/{profile_id}/today", params={"on": "2026-08-27"}
        )
        assert today.status_code == 200
        assert today.json()[0]["session"]["id"] == session_id
        assert today.json()[0]["prescription"] == prescription

        unknown_exercise = client.post(
            f"/sessions/{session_id}/result",
            json={
                "summary": "Invalid exercise",
                "lifting_sets": [
                    {
                        "exercise_name": "Bench Press",
                        "set_number": 1,
                        "reps": 5,
                        "weight_kg": 80,
                    }
                ],
            },
        )
        assert unknown_exercise.status_code == 409

        result = client.post(
            f"/sessions/{session_id}/result",
            json={
                "summary": "All squat sets completed",
                "completed_at": "2026-08-27T10:30:00Z",
                "lifting_sets": [
                    {
                        "exercise_name": "Back Squat",
                        "set_number": 1,
                        "reps": 5,
                        "weight_kg": 100,
                    },
                    {
                        "exercise_name": "Back Squat",
                        "set_number": 2,
                        "reps": 5,
                        "weight_kg": 100,
                    },
                ],
            },
        )
        assert result.status_code == 201
        assert len(result.json()["lifting_sets"]) == 2
        assert client.get(f"/sessions/{session_id}/result").json() == result.json()

        progression = client.post(
            f"/sessions/{session_id}/progression",
            json={
                "scheduled_for": "2026-09-03",
                "lifting_weight_increment_kg": 2.5,
            },
        )
        assert progression.status_code == 201
        progressed = progression.json()
        assert progressed["session"]["status"] == "planned"
        assert progressed["session"]["scheduled_for"] == "2026-09-03"
        assert progressed["prescription"]["exercises"][0][
            "target_weight_kg"
        ] == 102.5
        assert progressed["prescription"]["exercises"][1][
            "target_weight_kg"
        ] is None

        locked = client.put(
            f"/sessions/{session_id}/prescription", json=prescription
        )
        assert locked.status_code == 409


def test_running_structure_validation_metrics_and_progression(tmp_path: Path) -> None:
    with make_client(tmp_path / "coachline.sqlite3") as client:
        _, session_id = create_session(client, "running", "2026-08-28")
        prescription = {
            "discipline": "running",
            "segments": [
                {"kind": "warmup", "distance_m": 500},
                {
                    "kind": "work",
                    "distance_m": 1000,
                    "target_pace_seconds_per_km": 360,
                },
                {"kind": "cooldown", "duration_seconds": 300},
            ],
        }
        assert (
            client.put(
                f"/sessions/{session_id}/prescription", json=prescription
            ).status_code
            == 200
        )

        wrong_discipline = client.put(
            f"/sessions/{session_id}/prescription",
            json={
                "discipline": "lifting",
                "exercises": [{"name": "Squat", "sets": 3, "reps": 5}],
            },
        )
        assert wrong_discipline.status_code == 409

        invalid_segment = client.put(
            f"/sessions/{session_id}/prescription",
            json={
                "discipline": "running",
                "segments": [{"kind": "steady"}],
            },
        )
        assert invalid_segment.status_code == 422

        mixed_result = client.post(
            f"/sessions/{session_id}/result",
            json={
                "summary": "Wrong result kind",
                "lifting_sets": [
                    {
                        "exercise_name": "Squat",
                        "set_number": 1,
                        "reps": 5,
                    }
                ],
            },
        )
        assert mixed_result.status_code == 409

        result = client.post(
            f"/sessions/{session_id}/result",
            json={
                "summary": "Intervals completed",
                "running_metrics": {
                    "distance_m": 2000,
                    "duration_seconds": 780,
                    "average_heart_rate": 155,
                },
            },
        )
        assert result.status_code == 201
        assert result.json()["running_metrics"]["average_heart_rate"] == 155

        progression = client.post(
            f"/sessions/{session_id}/progression",
            json={
                "scheduled_for": "2026-09-04",
                "running_increase_percent": 10,
            },
        )
        assert progression.status_code == 201
        segments = progression.json()["prescription"]["segments"]
        assert segments[0]["distance_m"] == 500
        assert segments[1]["distance_m"] == 1100
        assert segments[2]["duration_seconds"] == 300


def test_progression_requires_completed_session_and_prescription(
    tmp_path: Path,
) -> None:
    with make_client(tmp_path / "coachline.sqlite3") as client:
        _, session_id = create_session(client, "lifting", "2026-08-29")

        not_completed = client.post(
            f"/sessions/{session_id}/progression",
            json={"scheduled_for": "2026-09-05"},
        )
        assert not_completed.status_code == 409

        client.post(
            f"/sessions/{session_id}/result", json={"summary": "Completed"}
        )
        no_prescription = client.post(
            f"/sessions/{session_id}/progression",
            json={"scheduled_for": "2026-09-05"},
        )
        assert no_prescription.status_code == 404


def test_phase2_database_is_upgraded_in_place(tmp_path: Path) -> None:
    database_path = tmp_path / "coachline.sqlite3"
    database = Database(database_path)
    phase2_migration = (
        Path(__file__).parents[1]
        / "app"
        / "migrations"
        / "001_training_core.sql"
    ).read_text(encoding="utf-8")

    with database.session() as connection:
        connection.execute(
            """
            CREATE TABLE schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.executescript(phase2_migration)
        connection.execute(
            "INSERT INTO schema_migrations (version) VALUES (?)",
            ("001_training_core",),
        )

    with make_client(database_path) as client:
        assert client.get("/health").status_code == 200

    with database.session() as connection:
        versions = [
            row["version"]
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ).fetchall()
        ]
        structured_table = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name = 'lifting_exercises'
            """
        ).fetchone()

    assert versions == [
        "001_training_core",
        "002_structured_training",
        "003_messaging",
        "004_ai_interpretation",
    ]
    assert structured_table is not None
