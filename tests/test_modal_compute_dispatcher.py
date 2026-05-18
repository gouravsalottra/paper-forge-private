from __future__ import annotations

import base64
from pathlib import Path


def _write_csv(tmp_path: Path) -> str:
    path = tmp_path / "input.csv"
    path.write_text("date,value\n2020-01-01,1.0\n2020-01-02,2.0\n", encoding="utf-8")
    return str(path)


def test_modal_payload_does_not_include_process_secrets(tmp_path, monkeypatch):
    from api.compute_dispatcher import _modal_payload

    monkeypatch.setenv("OPENAI_API_KEY", "secret-openai")
    monkeypatch.setenv("DATABASE_URL", "postgresql://secret")
    monkeypatch.setenv("MODAL_TOKEN_ID", "secret-token-id")
    monkeypatch.setenv("MODAL_TOKEN_SECRET", "secret-token-secret")

    payload = _modal_payload("print('ok')", _write_csv(tmp_path), None, "unit", {"topic": "x"})

    serialized = str(payload)
    assert "OPENAI_API_KEY" not in payload
    assert "DATABASE_URL" not in payload
    assert "MODAL_TOKEN_ID" not in payload
    assert "MODAL_TOKEN_SECRET" not in payload
    assert "secret-openai" not in serialized
    assert "postgresql://secret" not in serialized
    assert base64.b64decode(payload["data_csv_b64"]).startswith(b"date,value")


def test_execute_analysis_code_uses_modal_backend_and_materializes_outputs(tmp_path, monkeypatch):
    import api.compute_dispatcher as cd
    import api.modal_compute as modal_compute

    data_csv = _write_csv(tmp_path)
    monkeypatch.setattr(cd, "_compute_backend", lambda: "modal")

    def fake_modal(payload):
        result_csv = b"Test,Statistic\nModal regression,1.23\n"
        figure = b"fake-png-bytes"
        return {
            "success": True,
            "returncode": 0,
            "stdout": '{"primary_result":{"label":"Modal regression","t_statistic":1.23,"p_value":0.22},"figures":[],"result_csvs":[]}\n',
            "stderr": "",
            "parsed": {"primary_result": {"label": "Modal regression", "t_statistic": 1.23, "p_value": 0.22}},
            "runtime_seconds": 2.5,
            "files": [
                {"kind": "result_csv", "filename": "Modal Results.csv", "content_b64": base64.b64encode(result_csv).decode("ascii")},
                {"kind": "figure", "filename": "Modal Figure.png", "content_b64": base64.b64encode(figure).decode("ascii")},
            ],
        }

    monkeypatch.setattr(modal_compute, "execute_in_modal", fake_modal)

    result = cd._execute_analysis_code("print('modal')", data_csv, "unit-modal", {"topic": "x"}, {"columns": ["value"]})

    assert result["compute_backend"] == "modal"
    assert result["execution_attempts"] == 1
    assert result["runtime_seconds"] == 2.5
    assert Path(result["result_csvs"][0]).exists()
    assert Path(result["figures"][0]).exists()
    assert result["primary_result"]["label"] == "Modal regression"


def test_modal_failure_uses_api_side_repair_and_resubmits(tmp_path, monkeypatch):
    import api.compute_dispatcher as cd
    import api.modal_compute as modal_compute

    data_csv = _write_csv(tmp_path)
    calls = {"modal": 0, "fix": 0}
    monkeypatch.setattr(cd, "_compute_backend", lambda: "modal")

    def fake_modal(payload):
        calls["modal"] += 1
        if calls["modal"] == 1:
            return {"success": False, "returncode": 1, "stdout": "", "stderr": "NameError: broken", "files": []}
        return {
            "success": True,
            "returncode": 0,
            "stdout": '{"primary_result":{"label":"Fixed analysis","p_value":0.04}}\n',
            "stderr": "",
            "parsed": {"primary_result": {"label": "Fixed analysis", "p_value": 0.04}},
            "files": [],
        }

    def fake_fix(code, error, blueprint, schema):
        calls["fix"] += 1
        assert "NameError" in error
        return "print('fixed')"

    monkeypatch.setattr(modal_compute, "execute_in_modal", fake_modal)
    monkeypatch.setattr(cd, "_llm_fix_code", fake_fix)

    result = cd._execute_analysis_code("print(broken)", data_csv, "unit-retry", {"topic": "x"}, {"columns": ["value"]})

    assert calls == {"modal": 2, "fix": 1}
    assert result["compute_backend"] == "modal"
    assert result["execution_attempts"] == 2
    assert result["primary_result"]["label"] == "Fixed analysis"
