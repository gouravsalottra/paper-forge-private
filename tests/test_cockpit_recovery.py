from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient


def _client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "sessions.db"))
    monkeypatch.setenv("THRIVARC_STORAGE_BACKEND", "mock")
    from storage import blob

    blob.reset_mock_storage()
    from main import app

    return TestClient(app)


def test_model_registry_lists_chat_capable_deployments(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(
        "THRIVARC_ALLOWED_MODELS",
        "gpt-4o,gpt-4o-mini,gpt-5.4,text-embedding-3-large",
    )
    client = _client(tmp_path, monkeypatch)
    response = client.get("/api/models")
    assert response.status_code == 200
    body = response.json()
    names = [item["name"] for item in body["models"]]
    assert "gpt-4o" in names
    assert "gpt-4o-mini" in names
    assert "gpt-5.4" in names
    assert "text-embedding-3-large" not in names
    assert body["default_model"] == "gpt-4o"
    assert body["fallback_model"] == "gpt-4o"
    assert any(item["capabilities"]["chat"] for item in body["models"])


def test_prompt_studio_supports_full_working_prompt_and_notes(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    created = client.post("/api/sessions", json={"topic": "Prompt control study"})
    session_id = created.json()["session_id"]

    saved = client.put(
        f"/api/sessions/{session_id}/prompt-amplifiers",
        json={
            "agent_name": "Writer Agent",
            "working_prompt": "Write with the density of a Journal of Finance author and prioritize mechanism.",
            "session_notes": "Use a skeptical reader voice and tie every claim to evidence.",
            "editor": "admin",
        },
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["template"]["working_prompt_version"] == 1
    assert body["template"]["notes_version"] == 1
    assert "Journal of Finance" in body["composed_prompt"]["composed_prompt"]
    assert "skeptical reader voice" in body["composed_prompt"]["composed_prompt"]
    assert "LOCKED THRIVARC SAFETY CONTRACT" in body["composed_prompt"]["composed_prompt"]

    updated = client.put(
        f"/api/sessions/{session_id}/prompt-amplifiers",
        json={
            "agent_name": "Writer Agent",
            "working_prompt": "Write like a top empirical finance researcher with a referee-conscious structure.",
            "editor": "admin",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["template"]["working_prompt_version"] == 2

    listing = client.get(f"/api/sessions/{session_id}/prompt-amplifiers")
    assert listing.status_code == 200
    template = next(item for item in listing.json()["templates"] if item["agent_name"] == "Writer Agent")
    assert template["working_prompt_version"] == 2
    assert template["notes_version"] == 1
    assert "skeptical reader voice" in template["session_notes"]


def test_specialist_threads_persist_and_use_selected_model(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    created = client.post("/api/sessions", json={"topic": "Specialist thread study"})
    session_id = created.json()["session_id"]

    client.put(
        f"/api/sessions/{session_id}/model-settings",
        json={"phase_name": "Writer Agent", "model_name": "gpt-4o"},
    )

    import api.sessions as sessions

    captured: dict[str, str] = {}

    class _FakeMessage:
        content = "The introduction should open with the mechanism, not the workflow."

    class _FakeChoice:
        message = _FakeMessage()

    class _FakeResponse:
        choices = [_FakeChoice()]

    class _FakeCompletions:
        def create(self, **kwargs):
            captured["model"] = kwargs.get("model")
            return _FakeResponse()

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    monkeypatch.setattr(sessions, "_agent_client", lambda: _FakeClient())

    first = client.post(
        f"/api/sessions/{session_id}/specialists/Writer Agent/messages",
        json={"message": "Rewrite the introduction opening.", "mode": "critique"},
    )
    assert first.status_code == 200
    assert first.json()["assistant_message"]["model_name"] == "gpt-4o"
    assert captured["model"] == "gpt-4o"

    second = client.post(
        f"/api/sessions/{session_id}/specialists/Writer Agent/messages",
        json={"message": "Make it sharper and more skeptical.", "mode": "revise_prompt"},
    )
    assert second.status_code == 200

    thread = client.get(f"/api/sessions/{session_id}/specialists/Writer Agent")
    assert thread.status_code == 200
    messages = thread.json()["thread"]["messages"]
    assert len(messages) == 4
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert messages[-1]["mode"] == "revise_prompt"


def test_specialist_can_create_draft_compute_cell(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    created = client.post("/api/sessions", json={"topic": "Notebook suggestion study"})
    session_id = created.json()["session_id"]

    import api.sessions as sessions

    class _FakeMessage:
        content = "import pandas as pd\n\nsummary = data.describe()\nprint(summary)"

    class _FakeChoice:
        message = _FakeMessage()

    class _FakeResponse:
        choices = [_FakeChoice()]

    class _FakeCompletions:
        def create(self, **kwargs):
            return _FakeResponse()

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    monkeypatch.setattr(sessions, "_agent_client", lambda: _FakeClient())

    response = client.post(
        f"/api/sessions/{session_id}/specialists/Method / Compute Agent/messages",
        json={"message": "Generate a notebook cell that profiles the dataset.", "mode": "generate_notebook_cell"},
    )
    assert response.status_code == 200
    actions = response.json()["assistant_message"]["actions"]
    assert actions
    assert actions[0]["type"] == "draft_compute_cell"

    cells = client.get(f"/api/sessions/{session_id}/compute-cells")
    assert any("profile" in (cell["title"] or "").lower() for cell in cells.json()["cells"])


def test_notebook_workspace_launch_and_sync_round_trip(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    created = client.post("/api/sessions", json={"topic": "Notebook launch study"})
    session_id = created.json()["session_id"]

    import api.notebook_runtime as notebook_runtime

    launched = {
        "status": "running",
        "backend": "modal",
        "modal_account_alias": "primary",
        "sandbox_id": "sb-123",
        "access_url": "https://notebook.example/lab?token=abc",
        "can_embed": True,
        "sync_status": "not_synced",
    }
    monkeypatch.setattr(notebook_runtime, "launch_or_resume_workspace", lambda *args, **kwargs: launched)
    monkeypatch.setattr(
        notebook_runtime,
        "sync_workspace_artifacts",
        lambda *args, **kwargs: {
            "synced_paths": [
                f"sessions/{session_id}/06_compute/notebook/analysis.ipynb",
                f"sessions/{session_id}/06_compute/notebook/analysis.py",
            ],
            "status": "synced",
        },
    )

    before = client.get(f"/api/sessions/{session_id}/notebook")
    assert before.status_code == 200
    assert before.json()["workspace"]["status"] in {"not_started", "ready"}

    start = client.post(f"/api/sessions/{session_id}/notebook/launch")
    assert start.status_code == 200
    assert start.json()["workspace"]["access_url"] == launched["access_url"]
    assert start.json()["workspace"]["backend"] == "modal"

    sync = client.post(f"/api/sessions/{session_id}/notebook/sync")
    assert sync.status_code == 200
    assert sync.json()["workspace"]["sync_status"] == "synced"
    assert len(sync.json()["workspace"]["artifact_paths"]) == 2


def test_bulk_delete_completed_sessions(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    first = client.post("/api/sessions", json={"topic": "Completed study"})
    second = client.post("/api/sessions", json={"topic": "Running study"})
    completed_id = first.json()["session_id"]
    running_id = second.json()["session_id"]

    import api.sessions as sessions

    with sessions._with_conn() as conn:
        sessions._execute(conn, "UPDATE sessions SET status=?, updated_at=? WHERE id=?", ("paper_unlocked", sessions._now(), completed_id))
        sessions._execute(conn, "UPDATE sessions SET status=?, updated_at=? WHERE id=?", ("running", sessions._now(), running_id))
        sessions._commit(conn)

    deleted = client.post("/api/sessions/bulk/delete-completed")
    assert deleted.status_code == 200
    assert completed_id in deleted.json()["deleted_session_ids"]
    assert running_id not in deleted.json()["deleted_session_ids"]

    listing = client.get("/api/sessions")
    remaining = [item["id"] for item in listing.json()]
    assert running_id in remaining
    assert completed_id not in remaining
