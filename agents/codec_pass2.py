"""CODEC Pass 2: independent paper-only reimplementation audit."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


class CodecPass2:
    def __init__(self, run_id: str, db_path: str = "state.db", output_dir: str = "paper_memory") -> None:
        self.run_id = run_id
        self.db_path = db_path
        self.output_dir = Path(output_dir)

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

    @staticmethod
    def _call_gpt4o(paper_text: str) -> str:
        try:
            from dotenv import load_dotenv
        except Exception:
            def load_dotenv(*_args, **_kwargs):
                return False

        load_dotenv()

        from openai import OpenAI

        client = OpenAI()
        system_prompt = (
            "You have not seen the codebase. You have not seen any prior analysis. "
            "You must work only from the provided research specification text."
        )
        user_prompt = (
            "Reimplement the methodology from this spec alone.\n"
            "Requirements:\n"
            "1) list full implementation steps in order\n"
            "2) specify assumptions needed due to underspecification\n"
            "3) flag every underspecified detail\n"
            "4) rate reproducibility from 1 to 5 with rationale\n"
            "5) do not reference any codebase files\n\n"
            f"PAPER SPEC START\n{paper_text}\nPAPER SPEC END"
        )

        resp = client.chat.completions.create(
            model="gpt-5.4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
        )
        return (resp.choices[0].message.content or "").strip()

    def _write_result_flag(self, status: str) -> None:
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with sqlite3.connect(self.db_path) as conn:
            cols = [row[1] for row in conn.execute("PRAGMA table_info(agent_results)")]
            if {"run_id", "agent", "result_flag", "created_at"}.issubset(cols):
                conn.execute(
                    "INSERT INTO agent_results (run_id, agent, job, result_flag, created_at) VALUES (?, ?, ?, ?, ?)",
                    (self.run_id, "CODEC", "PASS2", status, created_at),
                )
            elif {"result_id", "run_id", "phase_name", "agent_name", "status", "created_at"}.issubset(cols):
                conn.execute(
                    """
                    INSERT INTO agent_results (result_id, run_id, phase_name, agent_name, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (uuid.uuid4().hex, self.run_id, "CODEC", "CODEC_PASS2", status, created_at),
                )
            conn.commit()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run CODEC pass 2 (paper-only replication audit).")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--db-path", default="state.db")
    parser.add_argument("--output-dir", default="paper_memory")
    args = parser.parse_args()

    result = CodecPass2(run_id=args.run_id, db_path=args.db_path, output_dir=args.output_dir).run()
    print(json.dumps(result, indent=2))
