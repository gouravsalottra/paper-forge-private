"""SPECAUDIT Pass 2: protocol-only extraction.

Pass 2 reads PROTOCOL/PAPER specification only and writes specaudit_report.md.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel

from agents.aria.exceptions import StructuredOutputError
from agents.llm_client import get_client, track_usage


class SpecAuditResult(BaseModel):
    verdict: Literal["PASS", "FAIL"]
    assumptions: list[str]
    underspecified_details: list[str]
    reproducibility_score: int
    rationale: str


class SpecAuditPass2:
    def __init__(self, run_id: str, db_path: str = "pipeline.db", output_dir: str = "runs") -> None:
        self.run_id = run_id
        self.db_path = db_path
        self.output_dir = Path(output_dir)
        self._prompt_sha256: str | None = None

    def run(self) -> dict:
        protocol_path = Path("PROTOCOL.md")
        if not protocol_path.exists():
            protocol_path = Path("PAPER.md")
        if not protocol_path.exists():
            raise FileNotFoundError("PROTOCOL.md (or PAPER.md fallback) not found")
        protocol_text = protocol_path.read_text(encoding="utf-8")
        report = self._call_llm(protocol_text)
        out_dir = self.output_dir / self.run_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "specaudit_report.md"
        out_path.write_text(report, encoding="utf-8")
        self._write_result_flag("DONE")
        return {"result_flag": "DONE", "path": str(out_path)}

    def _call_llm(self, protocol_text: str) -> str:
        load_dotenv()
        # Explicitly ensure pass-2 key path is used.
        pass2_key = os.getenv("OPENAI_API_KEY_PASS2", os.getenv("OPENAI_API_KEY", ""))
        os.environ["OPENAI_API_KEY"] = pass2_key
        client, model = get_client("SPECAUDIT")
        prompt_path = Path("prompts/specaudit.md")
        prompt_rules = prompt_path.read_text(encoding="utf-8", errors="ignore") if prompt_path.exists() else ""
        system_prompt = (
            "You are SPECAUDIT pass 2. Read ONLY the protocol/spec text and extract claimed methodology. "
            "Do not reference source code."
        )
        user_prompt = (
            f"{prompt_rules}\n\n"
            "Return strict JSON with keys verdict, assumptions, underspecified_details, reproducibility_score, rationale.\n\n"
            f"PROTOCOL START\n{protocol_text}\nPROTOCOL END"
        )
        self._prompt_sha256 = hashlib.sha256(f"{system_prompt}\n{user_prompt}".encode("utf-8")).hexdigest()

        raw = "{}"
        for attempt in range(2):
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                temperature=0,
                response_format={"type": "json_object"},
            )
            track_usage(
                resp,
                run_id=self.run_id,
                phase_name="SPECAUDIT",
                agent_name="SPECAUDIT_PASS2",
                model=model,
                db_path=self.db_path,
            )
            raw = (resp.choices[0].message.content or "{}").strip()
            try:
                parsed = SpecAuditResult.model_validate(json.loads(raw))
                return json.dumps(parsed.model_dump(), indent=2)
            except Exception:
                if attempt == 1:
                    raise StructuredOutputError("SPECAUDIT", raw)
        raise StructuredOutputError("SPECAUDIT", raw)

    def _write_result_flag(self, status: str) -> None:
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with sqlite3.connect(self.db_path) as conn:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(agent_results)")]
            if {"run_id", "agent", "result_flag", "created_at"}.issubset(cols):
                if "prompt_sha256" in cols:
                    conn.execute(
                        "INSERT INTO agent_results (run_id, agent, job, prompt_sha256, result_flag, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (self.run_id, "SPECAUDIT", "PASS2", self._prompt_sha256, status, created_at),
                    )
                else:
                    conn.execute(
                        "INSERT INTO agent_results (run_id, agent, job, result_flag, created_at) VALUES (?, ?, ?, ?, ?)",
                        (self.run_id, "SPECAUDIT", "PASS2", status, created_at),
                    )
            elif {"result_id", "run_id", "phase_name", "agent_name", "status", "created_at"}.issubset(cols):
                if "prompt_sha256" in cols:
                    conn.execute(
                        """
                        INSERT INTO agent_results (result_id, run_id, phase_name, agent_name, prompt_sha256, status, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (uuid.uuid4().hex, self.run_id, "SPECAUDIT", "SPECAUDIT_PASS2", self._prompt_sha256, status, created_at),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO agent_results (result_id, run_id, phase_name, agent_name, status, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (uuid.uuid4().hex, self.run_id, "SPECAUDIT", "SPECAUDIT_PASS2", status, created_at),
                    )
            conn.commit()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run SPECAUDIT pass 2 (spec-only).")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--db-path", default="pipeline.db")
    parser.add_argument("--output-dir", default="runs")
    args = parser.parse_args()
    print(json.dumps(SpecAuditPass2(args.run_id, args.db_path, args.output_dir).run(), indent=2))
