"""CODEC Pass 1: code-to-spec audit with code-only context."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from agents.llm_client import get_client, track_usage


class CodecPass1:
    def __init__(self, run_id: str, db_path: str = "state.db", output_dir: str = "paper_memory") -> None:
        self.run_id = run_id
        self.db_path = db_path
        self.output_dir = Path(output_dir)
        self._prompt_sha256: str | None = None

    def run(self) -> dict:
        code_files = self._collect_code_files()
        if not code_files:
            raise FileNotFoundError("No non-empty Python files found in agents/**/*.py")

        code_context = self._build_code_context(code_files)
        spec_text = self._call_gpt4o(code_context)

        out_dir = self.output_dir / self.run_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "codec_spec.md"
        out_path.write_text(spec_text, encoding="utf-8")

        self._write_result_flag("DONE")
        return {"result_flag": "DONE", "path": str(out_path), "files_scanned": len(code_files)}

    @staticmethod
    def _collect_code_files() -> list[Path]:
        root = Path("agents")
        paths: list[Path] = []
        for p in sorted(root.rglob("*.py")):
            if "__pycache__" in p.parts:
                continue
            if p.stat().st_size == 0:
                continue
            paths.append(p)
        return paths

    @staticmethod
    def _build_code_context(files: list[Path]) -> str:
        chunks: list[str] = []
        for path in files:
            rel = path.as_posix()
            text = path.read_text(encoding="utf-8", errors="ignore")
            chunks.append(f"\n\n### FILE: {rel}\n{text}")
        return "".join(chunks)

    def _call_gpt4o(self, code_context: str) -> str:
        try:
            from dotenv import load_dotenv
        except Exception:
            def load_dotenv(*_args, **_kwargs):
                return False

        load_dotenv()

        client, model = get_client("CODEC")
        system_prompt = (
            "You are CODEC Pass 1. Analyze ONLY the provided codebase content. "
            "Do not use or request paper/spec content. Be literal and forensic."
        )
        user_prompt = (
            "Extract what the code actually does:\n"
            "1) data sources\n"
            "2) transforms\n"
            "3) parameters/defaults\n"
            "4) reward function\n"
            "5) evaluation method\n"
            "6) undocumented or implicit steps\n\n"
            "Use markdown with clear headings and file references.\n\n"
            f"CODEBASE CONTENT START\n{code_context}\nCODEBASE CONTENT END"
        )
        self._prompt_sha256 = hashlib.sha256(
            f"{system_prompt}\n{user_prompt}".encode("utf-8")
        ).hexdigest()

        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
        )
        track_usage(
            resp,
            run_id=self.run_id,
            phase_name="CODEC",
            agent_name="CODEC_PASS1",
            model=model,
            db_path=self.db_path,
        )
        return (resp.choices[0].message.content or "").strip()

    def _write_result_flag(self, status: str) -> None:
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with sqlite3.connect(self.db_path) as conn:
            cols = [row[1] for row in conn.execute("PRAGMA table_info(agent_results)")]
            if {"run_id", "agent", "result_flag", "created_at"}.issubset(cols):
                if "prompt_sha256" in cols:
                    conn.execute(
                        "INSERT INTO agent_results (run_id, agent, job, prompt_sha256, result_flag, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (self.run_id, "CODEC", "PASS1", self._prompt_sha256, status, created_at),
                    )
                else:
                    conn.execute(
                        "INSERT INTO agent_results (run_id, agent, job, result_flag, created_at) VALUES (?, ?, ?, ?, ?)",
                        (self.run_id, "CODEC", "PASS1", status, created_at),
                    )
            elif {"result_id", "run_id", "phase_name", "agent_name", "status", "created_at"}.issubset(cols):
                if "prompt_sha256" in cols:
                    conn.execute(
                        """
                        INSERT INTO agent_results (result_id, run_id, phase_name, agent_name, prompt_sha256, status, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (uuid.uuid4().hex, self.run_id, "CODEC", "CODEC_PASS1", self._prompt_sha256, status, created_at),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO agent_results (result_id, run_id, phase_name, agent_name, status, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (uuid.uuid4().hex, self.run_id, "CODEC", "CODEC_PASS1", status, created_at),
                    )
            conn.commit()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run CODEC pass 1 (code-only audit).")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--db-path", default="state.db")
    parser.add_argument("--output-dir", default="paper_memory")
    args = parser.parse_args()

    result = CodecPass1(run_id=args.run_id, db_path=args.db_path, output_dir=args.output_dir).run()
    print(json.dumps(result, indent=2))
