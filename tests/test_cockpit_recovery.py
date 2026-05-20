from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

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


def test_notebook_bootstrap_uses_blob_payload_instead_of_large_command(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("THRIVARC_STORAGE_BACKEND", "mock")
    from storage import blob

    blob.reset_mock_storage()

    import api.notebook_runtime as notebook_runtime

    notebook_text = json.dumps(
        {
            "cells": [{"cell_type": "code", "source": ["print('x')\n" * 10000], "metadata": {}, "outputs": []}],
            "metadata": {},
            "nbformat": 4,
            "nbformat_minor": 5,
        }
    )
    payload_url = notebook_runtime._bootstrap_payload_url("session-1", notebook_text, {"seed.csv": "a,b\n1,2\n"})
    script = notebook_runtime._workspace_seed_script(payload_url, "token-123")

    assert "print('x')" not in script
    assert len(script) < 65536
    assert "urllib.request.urlopen" in script
    assert "token-123" in script
    assert notebook_runtime.WORKSPACE_DIR in script
    assert "--allow-root" in script


def test_live_notebook_launch_attaches_modal_app(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("THRIVARC_STORAGE_BACKEND", "mock")
    from storage import blob

    blob.reset_mock_storage()

    import api.modal_compute as modal_compute
    import api.notebook_runtime as notebook_runtime

    monkeypatch.setattr(notebook_runtime, "_is_test_mode", lambda: False)
    monkeypatch.setattr(notebook_runtime, "_bootstrap_payload_url", lambda *args, **kwargs: "https://example.test/bootstrap.json")

    account = SimpleNamespace(alias="primary", token_id="token-id", token_secret="token-secret")
    monkeypatch.setattr(modal_compute, "load_modal_accounts", lambda: [account])
    monkeypatch.setattr(modal_compute, "select_modal_account", lambda accounts: (account, {"alias": "primary"}))

    captured: dict[str, object] = {}

    class _FakeImage:
        @staticmethod
        def debian_slim(*args, **kwargs):
            return _FakeImage()

        def pip_install(self, *args, **kwargs):
            captured["pip_install"] = args
            return self

    class _FakeClient:
        @staticmethod
        def from_credentials(token_id, token_secret):
            captured["credentials"] = (token_id, token_secret)
            return "client-obj"

    class _FakeApp:
        @staticmethod
        def lookup(name, **kwargs):
            captured["app_lookup"] = {"name": name, **kwargs}
            return "app-obj"

    class _FakeTunnel:
        url = "https://sandbox.example"

    class _FakeSandboxHandle:
        object_id = "sb-123"

        def wait_until_ready(self, timeout):
            captured["ready_timeout"] = timeout

        def tunnels(self, timeout):
            captured["tunnel_timeout"] = timeout
            return {8888: _FakeTunnel()}

    class _FakeSandbox:
        @staticmethod
        def create(*args, **kwargs):
            captured["sandbox_args"] = args
            captured["sandbox_kwargs"] = kwargs
            return _FakeSandboxHandle()

    fake_modal = SimpleNamespace(
        Client=_FakeClient,
        App=_FakeApp,
        Image=_FakeImage,
        Sandbox=_FakeSandbox,
        sandbox=SimpleNamespace(Probe=SimpleNamespace(with_tcp=lambda port: ("probe", port))),
    )
    monkeypatch.setitem(sys.modules, "modal", fake_modal)

    workspace = notebook_runtime.launch_or_resume_workspace("session-2", "{\"cells\": []}", seed_files={"seed.csv": "a,b\n1,2\n"})

    assert workspace["backend"] == "modal"
    assert workspace["access_url"].startswith("https://sandbox.example/lab/tree/analysis.ipynb")
    assert captured["sandbox_kwargs"]["app"] == "app-obj"
    assert captured["sandbox_kwargs"]["workdir"] == notebook_runtime.WORKSPACE_DIR
    assert captured["app_lookup"]["name"] == "thrivarc-compute"


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


def test_dashboard_delete_visible_removes_supplied_visible_sessions(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    first = client.post("/api/sessions", json={"topic": "Visible cleanup one"}).json()["session_id"]
    second = client.post("/api/sessions", json={"topic": "Visible cleanup two"}).json()["session_id"]
    keep = client.post("/api/sessions", json={"topic": "Keep this study"}).json()["session_id"]

    deleted = client.post("/api/sessions/bulk/delete-visible", json={"session_ids": [first, second]})
    assert deleted.status_code == 200
    assert set(deleted.json()["deleted_session_ids"]) == {first, second}

    listing = client.get("/api/sessions")
    remaining = [item["id"] for item in listing.json()]
    assert keep in remaining
    assert first not in remaining
    assert second not in remaining


def test_stale_running_cleanup_marks_only_sessions_without_backend_activity(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    stale = client.post("/api/sessions", json={"topic": "Stale running study"}).json()["session_id"]
    active = client.post("/api/sessions", json={"topic": "Active modal study"}).json()["session_id"]

    import api.sessions as sessions

    with sessions._with_conn() as conn:
        sessions._execute(conn, "UPDATE sessions SET status=?, updated_at=? WHERE id=?", ("running", sessions._now(), stale))
        sessions._execute(conn, "UPDATE sessions SET status=?, updated_at=? WHERE id=?", ("running", sessions._now(), active))
        sessions._execute(
            conn,
            "INSERT INTO sandbox_jobs (id, session_id, phase_name, status, backend, modal_account_alias, attempt_count, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("job-active", active, "Compute", "running", "modal", "primary", 1, sessions._now(), sessions._now()),
        )
        sessions._commit(conn)

    cleaned = client.post("/api/sessions/bulk/clean-stale-running", json={"stale_after_seconds": 0})
    assert cleaned.status_code == 200
    assert stale in cleaned.json()["stale_session_ids"]
    assert active not in cleaned.json()["stale_session_ids"]

    stale_summary = client.get(f"/api/sessions/{stale}").json()
    active_summary = client.get(f"/api/sessions/{active}").json()
    assert stale_summary["status"] == "stale_needs_attention"
    assert stale_summary["backend_activity"]["state"] == "stale"
    assert active_summary["status"] == "running"
    assert active_summary["backend_activity"]["state"] == "modal_job"


def test_dashboard_runs_include_backend_truth_and_next_action(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    session_id = client.post("/api/sessions", json={"topic": "Dashboard truth study"}).json()["session_id"]

    import api.sessions as sessions

    with sessions._with_conn() as conn:
        sessions._execute(conn, "UPDATE sessions SET status=?, updated_at=? WHERE id=?", ("running", sessions._now(), session_id))
        sessions._execute(
            conn,
            "INSERT INTO sandbox_jobs (id, session_id, phase_name, status, backend, modal_account_alias, attempt_count, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("job-dashboard-truth", session_id, "Compute", "running", "modal", "primary", 1, sessions._now(), sessions._now()),
        )
        sessions._commit(conn)

    runs = client.get("/runs")
    assert runs.status_code == 200
    row = next(item for item in runs.json()["runs"] if item["run_id"] == session_id)
    assert row["backend_activity"]["state"] == "modal_job"
    assert row["next_action"].startswith("Running")


def test_cockpit_exposes_compute_resource_policy_without_default_gpu(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    session_id = client.post("/api/sessions", json={"topic": "Resource policy study"}).json()["session_id"]

    cockpit = client.get(f"/api/sessions/{session_id}/cockpit")
    assert cockpit.status_code == 200
    policy = cockpit.json()["compute_resource_policy"]
    assert policy["backend"] == "modal"
    assert policy["default_tier"] == "cpu-small"
    assert "gpu-t4" in policy["allowed_tiers"]
    assert "GPU tiers are only allowed" in policy["gpu_policy"]


def test_export_and_quality_are_not_ready_without_writer_artifact(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    session_id = client.post("/api/sessions", json={"topic": "Premature export study"}).json()["session_id"]

    quality = client.get(f"/api/sessions/{session_id}/quality-report")
    assert quality.status_code == 200
    assert quality.json()["quality_report"]["status"] == "not_ready"
    assert quality.json()["quality_report"]["score"] is None

    cockpit = client.get(f"/api/sessions/{session_id}/cockpit")
    assert cockpit.status_code == 200
    assert cockpit.json()["export"]["ready"] is False
    assert "writer_complete" in cockpit.json()["export"]["missing"]

    exported = client.get(f"/api/sessions/{session_id}/export/overleaf.zip")
    assert exported.status_code == 409
    assert exported.json()["error_code"] == "EXPORT_NOT_READY"


def test_notebook_launch_failure_is_persisted_as_visible_workspace_error(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    session_id = client.post("/api/sessions", json={"topic": "Notebook failure study"}).json()["session_id"]

    import api.notebook_runtime as notebook_runtime

    def fail_launch(*args, **kwargs):
        raise RuntimeError("Modal auth failed")

    monkeypatch.setattr(notebook_runtime, "launch_or_resume_workspace", fail_launch)
    launched = client.post(f"/api/sessions/{session_id}/notebook/launch")
    assert launched.status_code == 502
    assert launched.json()["error_code"] == "NOTEBOOK_LAUNCH_FAILED"

    workspace = client.get(f"/api/sessions/{session_id}/notebook").json()["workspace"]
    assert workspace["status"] == "failed"
    assert "Modal auth failed" in workspace["last_error"]
