"""CODEAUDIT Pass 1: code-only extraction.

Pass 1 reads source code artifacts only and writes codeaudit_spec.md.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from agents.llm_client import get_client, track_usage


class CodeAuditPass1:
    def __init__(self, run_id: str, db_path: str = "pipeline.db", output_dir: str = "runs") -> None:
        self.run_id = run_id
        self.db_path = db_path
        self.output_dir = Path(output_dir)
        self._prompt_sha256: str | None = None

    def run(self) -> dict:
        files = self._collect_code_files()
        if not files:
            raise FileNotFoundError("No code files found for CODEAUDIT pass 1")
        code_context = self._build_code_context(files)
        spec_md = self._call_llm(code_context)

        out_dir = self.output_dir / self.run_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "codeaudit_spec.md"
        out_path.write_text(spec_md, encoding="utf-8")
        self._write_result_flag("DONE")
        return {"result_flag": "DONE", "path": str(out_path), "files_scanned": len(files)}

    @staticmethod
    def _collect_code_files() -> list[Path]:
        paths: list[Path] = []
        for p in sorted(Path("agents").rglob("*.py")):
            if "__pycache__" in p.parts or p.stat().st_size == 0:
                continue
            paths.append(p)
        return paths

    @staticmethod
    def _build_code_context(files: list[Path]) -> str:
        chunks: list[str] = []
        for path in files:
            text = path.read_text(encoding="utf-8", errors="ignore")
            chunks.append(f"\n\n### FILE: {path.as_posix()}\n{text}")
        return "".join(chunks)

    def _call_llm(self, code_context: str) -> str:
        load_dotenv()
        # Explicitly route through primary pass-1 key.
        os.environ.setdefault("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", ""))
        client, model = get_client("CODEAUDIT")
        prompt_path = Path("prompts/codeaudit.md")
        prompt_rules = prompt_path.read_text(encoding="utf-8", errors="ignore") if prompt_path.exists() else ""
        system_prompt = (
            "You are CODEAUDIT pass 1. Read ONLY source code and extract actual implemented behavior. "
            "Do not infer from protocol/spec documents."
        )
        user_prompt = (
            f"{prompt_rules}\n\n"
            "Return markdown sections for data, transforms, parameters, reward, and evaluation.\n\n"
            f"CODE CONTEXT START\n{code_context}\nCODE CONTEXT END"
        )
        self._prompt_sha256 = hashlib.sha256(f"{system_prompt}\n{user_prompt}".encode("utf-8")).hexdigest()
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0,
        )
        track_usage(
            resp,
            run_id=self.run_id,
            phase_name="CODEAUDIT",
            agent_name="CODEAUDIT_PASS1",
            model=model,
            db_path=self.db_path,
        )
        return (resp.choices[0].message.content or "").strip()

    def _write_result_flag(self, status: str) -> None:
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with sqlite3.connect(self.db_path) as conn:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(agent_results)")]
            if {"run_id", "agent", "result_flag", "created_at"}.issubset(cols):
                if "prompt_sha256" in cols:
                    conn.execute(
                        "INSERT INTO agent_results (run_id, agent, job, prompt_sha256, result_flag, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (self.run_id, "CODEAUDIT", "PASS1", self._prompt_sha256, status, created_at),
                    )
                else:
                    conn.execute(
                        "INSERT INTO agent_results (run_id, agent, job, result_flag, created_at) VALUES (?, ?, ?, ?, ?)",
                        (self.run_id, "CODEAUDIT", "PASS1", status, created_at),
                    )
            elif {"result_id", "run_id", "phase_name", "agent_name", "status", "created_at"}.issubset(cols):
                if "prompt_sha256" in cols:
                    conn.execute(
                        """
                        INSERT INTO agent_results (result_id, run_id, phase_name, agent_name, prompt_sha256, status, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (uuid.uuid4().hex, self.run_id, "CODEAUDIT", "CODEAUDIT_PASS1", self._prompt_sha256, status, created_at),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO agent_results (result_id, run_id, phase_name, agent_name, status, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (uuid.uuid4().hex, self.run_id, "CODEAUDIT", "CODEAUDIT_PASS1", status, created_at),
                    )
            conn.commit()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run CODEAUDIT pass 1 (code-only).")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--db-path", default="pipeline.db")
    parser.add_argument("--output-dir", default="runs")
    args = parser.parse_args()
    print(json.dumps(CodeAuditPass1(args.run_id, args.db_path, args.output_dir).run(), indent=2))
