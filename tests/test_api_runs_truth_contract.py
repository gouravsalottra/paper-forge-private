from __future__ import annotations

import json
from pathlib import Path

from api import runs


def _meta() -> dict:
    return {
        "research_state": "confirmatory_pap",
        "runspec": {"research": {"topic": "test"}, "blueprint": {}},
        "plan": {
            "research_package": {"track": "confirmatory", "label": "Confirmatory package"},
            "reviewer_gate": {"writer_rule": "Writer is last and never invents numbers."},
            "repair_contract_template": {"max_cycles_per_issue": 3},
            "integrity_artifacts": {"data_passport": {"visible_name": "DataPassport"}, "deviation_register": {"visible_name": "Deviation Register"}},
            "audit_boundary": {"code_audit_agent": {"definition": "Technical correctness check."}},
            "paper_code_verifier": {"final_position": "immediately before Writer export"},
        },
    }


def test_truth_contract_exposes_run_integrity_layers() -> None:
    contract = runs._truth_contract("run-1", _meta())

    assert contract["research_state"] == "confirmatory_pap"
    assert contract["runspec_present"] is True
    assert contract["research_package"]["track"] == "confirmatory"
    assert contract["paper_gate"]["writer_rule"] == "Writer is last and never invents numbers."
    assert contract["repair_contract_template"]["max_cycles_per_issue"] == 3
    assert contract["artifact_manifest"]["integrity"]["deviation_register"].endswith("deviation_register.json")
    assert contract["orchestration"]["writer_gate"].startswith("WRITER starts only after")
    assert {item["phase"] for item in contract["failure_catalog"]} >= {"DATAPULL", "REVIEWER", "WRITER"}


def test_write_contract_artifacts_creates_research_memory_structure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(runs, "RUN_STORE", tmp_path)

    runs._write_contract_artifacts("run-2", _meta())

    truth_path = tmp_path / "run-2" / "01_integrity" / "truth_contract.json"
    deviation_path = tmp_path / "run-2" / "01_integrity" / "deviation_register.json"
    runspec_path = tmp_path / "run-2" / "00_runspec" / "runspec.json"
    assert truth_path.exists()
    assert deviation_path.exists()
    assert runspec_path.exists()
    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    assert truth["integrity_artifacts"]["data_passport"]["visible_name"] == "DataPassport"
