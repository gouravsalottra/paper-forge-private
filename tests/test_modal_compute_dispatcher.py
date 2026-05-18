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


def test_generated_code_cleaner_removes_markdown_fences():
    from api.compute_dispatcher import _clean_generated_code, _extract_json_from_text, _generated_code_preflight_error

    cleaned = _clean_generated_code("```python\nprint('ok')\n```")

    assert cleaned == "print('ok')"
    assert _generated_code_preflight_error(cleaned) is None
    assert "sklearn" in (_generated_code_preflight_error("from sklearn.utils import resample") or "")
    parsed = _extract_json_from_text("{'primary_result': {'coefficient': np.float64(-0.043), 'p_value': None}}")
    assert parsed == {"primary_result": {"coefficient": -0.043, "p_value": None}}


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


def test_modal_router_selects_least_spend_healthy_account(tmp_path, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "router.db"))
    from api import modal_compute as mc

    accounts = [
        mc.ModalAccount("primary", "id1", "secret1"),
        mc.ModalAccount("secondary", "id2", "secret2"),
        mc.ModalAccount("tertiary", "id3", "secret3"),
    ]
    with mc._connect_db() as conn:
        mc._ensure_router_schema(conn)
        month = mc._usage_month()
        mc._execute(conn, "INSERT INTO modal_account_usage (alias, usage_month, estimated_spend_usd, monthly_budget_usd, status, failure_count) VALUES (?, ?, ?, ?, ?, ?)", ("primary", month, 12.0, 28.0, "healthy", 0))
        mc._execute(conn, "INSERT INTO modal_account_usage (alias, usage_month, estimated_spend_usd, monthly_budget_usd, status, failure_count) VALUES (?, ?, ?, ?, ?, ?)", ("secondary", month, 2.0, 28.0, "healthy", 0))
        mc._execute(conn, "INSERT INTO modal_account_usage (alias, usage_month, estimated_spend_usd, monthly_budget_usd, status, failure_count) VALUES (?, ?, ?, ?, ?, ?)", ("tertiary", month, 4.0, 28.0, "healthy", 0))
        conn.commit()

    account, routing = mc.select_modal_account(accounts)

    assert account.alias == "secondary"
    assert routing["routing_reason"] == "least_spend_healthy_under_budget"
    assert routing["eligible_aliases"] == ["secondary", "tertiary", "primary"]


def test_modal_router_excludes_over_budget_and_unhealthy_accounts(tmp_path, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "router.db"))
    from api import modal_compute as mc

    accounts = [
        mc.ModalAccount("primary", "id1", "secret1"),
        mc.ModalAccount("secondary", "id2", "secret2"),
        mc.ModalAccount("tertiary", "id3", "secret3"),
    ]
    with mc._connect_db() as conn:
        mc._ensure_router_schema(conn)
        month = mc._usage_month()
        mc._execute(conn, "INSERT INTO modal_account_usage (alias, usage_month, estimated_spend_usd, monthly_budget_usd, status, failure_count) VALUES (?, ?, ?, ?, ?, ?)", ("primary", month, 28.0, 28.0, "healthy", 0))
        mc._execute(conn, "INSERT INTO modal_account_usage (alias, usage_month, estimated_spend_usd, monthly_budget_usd, status, failure_count) VALUES (?, ?, ?, ?, ?, ?)", ("secondary", month, 1.0, 28.0, "unhealthy", 3))
        mc._execute(conn, "INSERT INTO modal_account_usage (alias, usage_month, estimated_spend_usd, monthly_budget_usd, status, failure_count) VALUES (?, ?, ?, ?, ?, ?)", ("tertiary", month, 7.0, 28.0, "healthy", 0))
        conn.commit()

    account, routing = mc.select_modal_account(accounts)

    assert account.alias == "tertiary"
    assert routing["eligible_aliases"] == ["tertiary"]


def test_modal_router_failover_uses_next_account_for_platform_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "router.db"))
    monkeypatch.setenv("MODAL_ROUTER_ENABLED", "1")
    monkeypatch.setenv("MODAL_ACCOUNT_ALIASES", "primary,secondary")
    monkeypatch.setenv("MODAL_PRIMARY_TOKEN_ID", "id1")
    monkeypatch.setenv("MODAL_PRIMARY_TOKEN_SECRET", "secret1")
    monkeypatch.setenv("MODAL_SECONDARY_TOKEN_ID", "id2")
    monkeypatch.setenv("MODAL_SECONDARY_TOKEN_SECRET", "secret2")
    from api import modal_compute as mc

    calls: list[str] = []

    def fake_execute(payload, account):
        calls.append(account.alias)
        if account.alias == "primary":
            raise RuntimeError("auth failed")
        return {"success": True, "returncode": 0, "runtime_seconds": 5, "files": [], "parsed": {"primary_result": {"label": "ok"}}}

    monkeypatch.setattr(mc, "execute_in_modal_account", fake_execute)

    result = mc.execute_in_modal({"session_id": "unit"})

    assert calls == ["primary", "secondary"]
    assert result["modal_account_alias"] == "secondary"
    assert result["routing"]["tried_aliases"] == ["primary", "secondary"]


def test_modal_router_generated_code_failure_does_not_mark_account_unhealthy(tmp_path, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "router.db"))
    monkeypatch.setenv("MODAL_ROUTER_ENABLED", "1")
    monkeypatch.setenv("MODAL_ACCOUNT_ALIASES", "primary")
    monkeypatch.setenv("MODAL_PRIMARY_TOKEN_ID", "id1")
    monkeypatch.setenv("MODAL_PRIMARY_TOKEN_SECRET", "secret1")
    from api import modal_compute as mc

    def fake_execute(payload, account):
        return {"success": False, "returncode": 1, "runtime_seconds": 2, "stderr": "NameError: generated code failed", "files": []}

    monkeypatch.setattr(mc, "execute_in_modal_account", fake_execute)

    result = mc.execute_in_modal({"session_id": "unit"})
    with mc._connect_db() as conn:
        row = mc._execute(conn, "SELECT status, failure_count FROM modal_account_usage WHERE alias=? AND usage_month=?", ("primary", mc._usage_month())).fetchone()

    assert result["success"] is False
    assert row["status"] == "healthy"
    assert row["failure_count"] == 0
