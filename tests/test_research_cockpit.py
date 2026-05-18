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
