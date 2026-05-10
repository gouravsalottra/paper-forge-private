"""CODEAUDIT Pass 2: independent paper-only reimplementation audit."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from agents.aria.exceptions import StructuredOutputError
from agents.llm_client import get_client, track_usage


class SpecAuditResult(BaseModel):
    verdict: Literal["PASS", "FAIL"]
    assumptions: list[str]
    underspecified_details: list[str]
    reproducibility_score: int
    rationale: str


class CodecPass2:
    def __init__(self, run_id: str, db_path: str = "pipeline.db", output_dir: str = "runs") -> None:
        self.run_id = run_id
        self.db_path = db_path
        self.output_dir = Path(output_dir)
        self._prompt_sha256: str | None = None

    def run(self) -> dict:
        paper_path = Path("PAPER.md")
        if not paper_path.exists():
            raise FileNotFoundError("PAPER.md not found")

        paper_text = paper_path.read_text(encoding="utf-8")
        audit_text = self._call_gpt4o(paper_text)

        out_dir = self.output_dir / self.run_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "codec_pass2.md"
        out_path.write_text(audit_text, encoding="utf-8")

        self._write_result_flag("DONE")
        return {"result_flag": "DONE", "path": str(out_path)}

    def _call_gpt4o(self, paper_text: str) -> str:
        try:
            from dotenv import load_dotenv
        except Exception:
            def load_dotenv(*_args, **_kwargs):
                return False

        load_dotenv()

        client, model = get_client("CODEAUDIT")
        system_prompt = (
            "You have not seen the codebase. You have not seen any prior analysis. "
            "You must work only from the provided research specification text."
        )
        user_prompt = (
            "Reimplement the methodology from this spec alone.\n"
            "Return strict JSON with keys:\n"
            "{\n"
            '  "verdict": "PASS" | "FAIL",\n'
            '  "assumptions": [str],\n'
            '  "underspecified_details": [str],\n'
            '  "reproducibility_score": int,\n'
            '  "rationale": str\n'
            "}\n"
            "Do not reference any codebase files.\n\n"
            f"PAPER SPEC START\n{paper_text}\nPAPER SPEC END"
        )
        self._prompt_sha256 = hashlib.sha256(
            f"{system_prompt}\n{user_prompt}".encode("utf-8")
        ).hexdigest()

        raw = "{}"
        for attempt in range(2):
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )
            track_usage(
                resp,
                run_id=self.run_id,
                phase_name="CODEAUDIT",
                agent_name="CODEAUDIT_PASS2",
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
            cols = [row[1] for row in conn.execute("PRAGMA table_info(agent_results)")]
            if {"run_id", "agent", "result_flag", "created_at"}.issubset(cols):
                if "prompt_sha256" in cols:
                    conn.execute(
                        "INSERT INTO agent_results (run_id, agent, job, prompt_sha256, result_flag, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (self.run_id, "CODEAUDIT", "PASS2", self._prompt_sha256, status, created_at),
                    )
                else:
                    conn.execute(
                        "INSERT INTO agent_results (run_id, agent, job, result_flag, created_at) VALUES (?, ?, ?, ?, ?)",
                        (self.run_id, "CODEAUDIT", "PASS2", status, created_at),
                    )
            elif {"result_id", "run_id", "phase_name", "agent_name", "status", "created_at"}.issubset(cols):
                if "prompt_sha256" in cols:
                    conn.execute(
                        """
                        INSERT INTO agent_results (result_id, run_id, phase_name, agent_name, prompt_sha256, status, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (uuid.uuid4().hex, self.run_id, "CODEAUDIT", "CODEAUDIT_PASS2", self._prompt_sha256, status, created_at),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO agent_results (result_id, run_id, phase_name, agent_name, status, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (uuid.uuid4().hex, self.run_id, "CODEAUDIT", "CODEAUDIT_PASS2", status, created_at),
                    )
            conn.commit()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run CODEAUDIT pass 2 (paper-only replication audit).")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--db-path", default="pipeline.db")
    parser.add_argument("--output-dir", default="runs")
    args = parser.parse_args()

    result = CodecPass2(run_id=args.run_id, db_path=args.db_path, output_dir=args.output_dir).run()
    print(json.dumps(result, indent=2))
