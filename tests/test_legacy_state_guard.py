from __future__ import annotations

import pytest
from fastapi import HTTPException


def test_production_disables_legacy_runs_even_if_flag_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    from api import runs

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("THRIVARC_ENABLE_LEGACY_RUNS", "1")

    assert runs._legacy_runs_enabled() is False


def test_legacy_runs_require_explicit_nonproduction_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    from api import runs

    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("THRIVARC_ENABLE_LEGACY_RUNS", raising=False)
    assert runs._legacy_runs_enabled() is False

    monkeypatch.setenv("THRIVARC_ENABLE_LEGACY_RUNS", "true")
    assert runs._legacy_runs_enabled() is True


def test_run_status_does_not_touch_legacy_db_when_legacy_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from api import runs

    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("THRIVARC_ENABLE_LEGACY_RUNS", raising=False)
    monkeypatch.setattr(runs, "_canonical_run_object", lambda _run_id: None)

    def fail_if_called():
        raise AssertionError("legacy pipeline DB should not be touched")

    monkeypatch.setattr(runs, "_connect", fail_if_called)

    with pytest.raises(HTTPException) as exc:
        runs.run_status("old-run")

    assert exc.value.status_code == 404


def test_legacy_read_endpoints_are_blocked_when_legacy_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from api import runs

    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("THRIVARC_ENABLE_LEGACY_RUNS", raising=False)
    monkeypatch.setattr(runs, "_canonical_session_exists", lambda _run_id: False)

    def fail_if_called():
        raise AssertionError("legacy pipeline DB should not be touched")

    monkeypatch.setattr(runs, "_connect", fail_if_called)

    for handler in (runs.run_truth_contract, runs.run_log, runs.run_artifacts):
        with pytest.raises(HTTPException) as exc:
            handler("old-run")
        assert exc.value.status_code == 404
