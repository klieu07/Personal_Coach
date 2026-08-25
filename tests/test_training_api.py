from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def make_client(database_path: Path) -> TestClient:
    return TestClient(
        create_app(database_path, admin_token="test-owner-token"),
        headers={"Authorization": "Bearer test-owner-token"},
    )


def create_training_plan(client: TestClient) -> tuple[int, int, int]:
    profile_response = client.post(
        "/profiles", json={"name": "Kai", "timezone": "Asia/Shanghai"}
    )
    assert profile_response.status_code == 201
    profile_id = profile_response.json()["id"]

    program_response = client.post(
        "/programs",
        json={
            "profile_id": profile_id,
            "name": "First 5K",
            "discipline": "running",
        },
    )
    assert program_response.status_code == 201
    program_id = program_response.json()["id"]

    session_response = client.post(
        "/sessions",
        json={
            "program_id": program_id,
            "scheduled_for": "2026-08-26",
            "title": "Easy 5 km",
            "notes": "Keep the pace conversational",
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["id"]

    return profile_id, program_id, session_id


def test_training_workflow_persists_and_completes_session(tmp_path: Path) -> None:
    database_path = tmp_path / "coachline.sqlite3"

    with make_client(database_path) as client:
        profile_id, program_id, session_id = create_training_plan(client)

        assert client.get(f"/profiles/{profile_id}").json() == {
            "name": "Kai",
            "timezone": "Asia/Shanghai",
            "id": profile_id,
        }
        assert client.get(f"/profiles/{profile_id}/programs").json() == [
            {
                "profile_id": profile_id,
                "name": "First 5K",
                "discipline": "running",
                "id": program_id,
                "active": True,
            }
        ]

        result_response = client.post(
            f"/sessions/{session_id}/result",
            json={
                "summary": "Finished in 31:20 and felt comfortable",
                "completed_at": "2026-08-26T10:30:00Z",
            },
        )
        assert result_response.status_code == 201
        assert result_response.json() == {
            "id": 1,
            "session_id": session_id,
            "summary": "Finished in 31:20 and felt comfortable",
            "completed_at": "2026-08-26T10:30:00Z",
            "lifting_sets": [],
            "running_metrics": None,
        }
        assert client.get(f"/sessions/{session_id}").json()["status"] == "completed"

    # A fresh application instance reads the same durable state and safely
    # recognizes that the migration has already run.
    with make_client(database_path) as restarted_client:
        completed = restarted_client.get(
            f"/profiles/{profile_id}/sessions", params={"status": "completed"}
        )
        assert completed.status_code == 200
        assert [session["id"] for session in completed.json()] == [session_id]


def test_skipped_session_must_be_replanned_before_result(tmp_path: Path) -> None:
    with make_client(tmp_path / "coachline.sqlite3") as client:
        _, _, session_id = create_training_plan(client)

        skipped = client.patch(
            f"/sessions/{session_id}/status", json={"status": "skipped"}
        )
        assert skipped.status_code == 200
        assert skipped.json()["status"] == "skipped"

        conflict = client.post(
            f"/sessions/{session_id}/result", json={"summary": "Done"}
        )
        assert conflict.status_code == 409
        assert conflict.json()["detail"] == (
            "A skipped session must be replanned before completion"
        )

        replanned = client.patch(
            f"/sessions/{session_id}/status", json={"status": "planned"}
        )
        assert replanned.status_code == 200

        completed = client.post(
            f"/sessions/{session_id}/result", json={"summary": "Done after all"}
        )
        assert completed.status_code == 201

        duplicate = client.post(
            f"/sessions/{session_id}/result", json={"summary": "Duplicate"}
        )
        assert duplicate.status_code == 409


def test_unknown_parent_resources_return_not_found(tmp_path: Path) -> None:
    with make_client(tmp_path / "coachline.sqlite3") as client:
        program_response = client.post(
            "/programs",
            json={
                "profile_id": 404,
                "name": "Missing",
                "discipline": "lifting",
            },
        )
        session_response = client.post(
            "/sessions",
            json={
                "program_id": 404,
                "scheduled_for": "2026-08-26",
                "title": "Missing",
            },
        )

    assert program_response.status_code == 404
    assert session_response.status_code == 404
