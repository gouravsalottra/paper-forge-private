from __future__ import annotations

import io
import json
import zipfile
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


def test_cockpit_creates_gates_followups_sandbox_and_events(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    created = client.post("/api/sessions", json={"topic": "Does liquidity predict ETF returns?"})
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    cockpit = client.get(f"/api/sessions/{session_id}/cockpit")
    assert cockpit.status_code == 200
    body = cockpit.json()
    assert body["phase_model"] == [
        "Topic", "Blueprint", "Literature", "Data", "Method Plan", "Compute", "Stats / Audit", "Review", "Writer", "Export"
    ]
    assert body["pending_approval"]["phase_name"] == "Topic"
    assert "approval_required" in body["sse_events"]
    assert body["autopilot"]["hard_limits"]["network_policy"] == "allowlist_only"
    assert body["modal_router"]["policy"] == "least_spend_healthy_under_budget"
    assert body["modal_router"]["budget_enforcement"] == "app_soft_cap"

    gate_id = body["pending_approval"]["id"]
    decided = client.post(f"/api/sessions/{session_id}/approvals/{gate_id}/decision", json={"decision": "approve", "approver": "admin"})
    assert decided.status_code == 200
    assert decided.json()["approval_gate"]["status"] == "approved"

    followup = client.post(
        f"/api/sessions/{session_id}/followups",
        json={"phase_name": "Compute", "instruction": "Add a robustness regression before the next phase."},
    )
    assert followup.status_code == 200
    assert followup.json()["followup"]["classification"] == "phase_local_revision"

    deviation = client.post(
        f"/api/sessions/{session_id}/followups",
        json={"instruction": "Change the hypothesis and date range."},
    )
    assert deviation.status_code == 200
    assert deviation.json()["followup"]["classification"] == "blueprint_changing_deviation"

    job = client.post(f"/api/sessions/{session_id}/sandbox/jobs", json={"phase_name": "Compute"})
    assert job.status_code == 200
    job_id = job.json()["sandbox_job"]["id"]
    updated = client.patch(
        f"/api/sessions/{session_id}/sandbox/jobs/{job_id}",
        json={"status": "complete", "artifact_paths": ["sessions/x/figures/a.png"], "cost_metrics": {"compute_seconds": 3}},
    )
    assert updated.status_code == 200
    assert updated.json()["sandbox_job"]["status"] == "complete"

    stream = client.get(f"/api/sessions/{session_id}/stream")
    assert "followup_classified" in stream.text
    assert "sandbox_job_update" in stream.text


def test_overleaf_zip_export_contains_project_manifest_and_assets(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    created = client.post("/api/sessions", json={"topic": "Export a research project"})
    session_id = created.json()["session_id"]

    from storage import blob

    blob.write_artifact(session_id, "11_paper/final.tex", r"\documentclass{article}\begin{document}Hi\end{document}")
    blob.write_artifact(session_id, "02_literature/bibliography.bib", "@article{a2020,title={A},year={2020}}")
    blob.write_artifact(session_id, "figures/fig1.png", b"fakepng")
    blob.write_artifact(session_id, "07_statistics/results_tables/table1.csv", "Metric,Value\nA,1\n")
    blob.write_artifact(session_id, "06_compute/method_outputs/code.py", "print(ok)\n")

    response = client.get(f"/api/sessions/{session_id}/export/overleaf.zip")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")

    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        names = set(zf.namelist())
        assert "11_paper/final.tex" in names
        assert "02_literature/bibliography.bib" in names
        assert "figures/fig1.png" in names
        assert "07_statistics/results_tables/table1.csv" in names
        assert "06_compute/method_outputs/code.py" in names
        assert "run_manifest.json" in names
        assert "README.md" in names
        manifest = json.loads(zf.read("run_manifest.json"))
        assert manifest["session_id"] == session_id
        assert manifest["reproducibility"]["legacy_state_used"] is False

    artifacts = client.get(f"/api/sessions/{session_id}/artifacts").json()["artifacts"]
    assert any(item["path"].endswith("11_paper/overleaf_project.zip") for item in artifacts)


def test_prompt_studio_cells_model_settings_and_quality_report(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    created = client.post("/api/sessions", json={"topic": "Does VIX predict SPY returns?"})
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    prompt = client.put(
        f"/api/sessions/{session_id}/prompt-amplifiers",
        json={
            "agent_name": "Writer Agent",
            "amplifier_text": "Write a deeper Journal of Finance style paper with full economic intuition.",
            "editor": "admin",
        },
    )
    assert prompt.status_code == 200
    body = prompt.json()
    assert body["amplifier"]["version"] == 1
    assert "LOCKED THRIVARC SAFETY CONTRACT" in body["composed_prompt"]["composed_prompt"]
    assert "Journal of Finance" in body["composed_prompt"]["composed_prompt"]

    composed = client.get(f"/api/sessions/{session_id}/prompts/composed", params={"agent": "Writer Agent"})
    assert composed.status_code == 200
    assert composed.json()["prompt_sha256"]

    model = client.put(
        f"/api/sessions/{session_id}/model-settings",
        json={"phase_name": "Writer", "model_name": "gpt-4o"},
    )
    assert model.status_code == 200
    rejected = client.put(
        f"/api/sessions/{session_id}/model-settings",
        json={"phase_name": "Writer", "model_name": "not-configured"},
    )
    assert rejected.status_code == 400
    assert rejected.json()["error_code"] == "MODEL_NOT_ALLOWED"

    cells = client.get(f"/api/sessions/{session_id}/compute-cells")
    assert cells.status_code == 200
    assert len(cells.json()["cells"]) >= 4

    added = client.post(
        f"/api/sessions/{session_id}/compute-cells",
        json={"title": "Extra robustness", "code": "print('extra robustness')"},
    )
    assert added.status_code == 200
    cell_id = added.json()["cell"]["id"]
    patched = client.patch(
        f"/api/sessions/{session_id}/compute-cells/{cell_id}",
        json={"title": "Extra robustness updated", "code": "print('updated')"},
    )
    assert patched.status_code == 200
    assert patched.json()["cell"]["version"] == 2

    import api.sessions as sessions

    def fake_execute(session_id_arg, blueprint, code):
        return {
            "success": True,
            "raw_results": {"raw_output": "ok", "analysis_code": code},
            "csv_outputs": {"07_statistics/results_tables/cell.csv": "Metric,Value\nA,1\n"},
            "figure_artifacts": {},
            "execution_artifacts": {"analysis_code": {"blob_path": f"sessions/{session_id_arg}/06_compute/generated_code/analysis_code.py"}},
            "stats_rows": [],
            "analysis_code": code,
            "execution_metadata": {"backend": "modal", "modal_account_alias": "primary", "runtime_seconds": 1.2},
        }

    monkeypatch.setattr(sessions, "execute_custom_analysis_code", fake_execute)
    run_cell = client.post(f"/api/sessions/{session_id}/compute-cells/{cell_id}/run")
    assert run_cell.status_code == 200
    assert run_cell.json()["status"] == "complete"
    assert run_cell.json()["execution_metadata"]["backend"] == "modal"

    from storage import blob

    blob.write_artifact(session_id, "11_paper/final.tex", "\\section{Results}\nShort paper")
    quality = client.get(f"/api/sessions/{session_id}/quality-report")
    assert quality.status_code == 200
    assert quality.json()["quality_report"]["status"] == "needs_repair"

    exported = client.get(f"/api/sessions/{session_id}/export/overleaf.zip")
    assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.content)) as zf:
        names = set(zf.namelist())
        assert "12_prompts/prompt_manifest.json" in names
        assert "12_quality/paper_quality_report.json" in names
        assert "06_compute/notebook/analysis.py" in names
        assert "06_compute/notebook/analysis.ipynb" in names
