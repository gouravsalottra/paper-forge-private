"""CODEC bidirectional audit agent with isolated LLM passes."""

from __future__ import annotations

import difflib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class CodecAgent:
    def __init__(self, run_id: str, db_path: str, output_dir: str, llm_client) -> None:
        self.run_id = run_id
        self.db_path = db_path
        self.output_dir = Path(output_dir)
        self.llm_client = llm_client
        self._model_name: str = "gpt-5.4"

    def run(self) -> dict:
        pass1_spec = self._pass1_read_code()
        pass2_spec = self._pass2_read_paper()
        mismatch = self._compare(pass1_spec, pass2_spec)

        flag = "PASS" if "severity: Fatal" not in mismatch and "severity: Major" not in mismatch else "FAIL"
        self._write_result(flag)
        return {"result_flag": flag}

    def _pass1_read_code(self) -> str:
        files = sorted(Path("agents").rglob("*.py"))
        lines = ["# CODEC Pass 1 Spec", ""]
        for p in files:
            rel = p.as_posix()
            text = p.read_text(encoding="utf-8", errors="ignore")
            if not text.strip():
                continue
            lines.append(f"## {rel}")
            lines.append(f"- lines: {len(text.splitlines())}")
            lines.append("```python")
            lines.append(text[:8000])
            lines.append("```")

        prompt = {
            "pass": "PASS1",
            "instructions": (
                "You are CODEC Pass 1. Read ONLY the provided codebase text. "
                "Extract what the code actually does: data sources, transforms, parameters, reward function, "
                "evaluation method, and undocumented steps. Be literal and forensic."
            ),
            "context": {"codebase_text": "\n".join(lines)},
        }
        llm_out = self._call_llm(prompt)
        out = self.output_dir / self.run_id / "codec_spec.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(str(llm_out), encoding="utf-8")
        return str(llm_out)

    def _pass2_read_paper(self) -> str:
        paper_path = Path("PAPER.md")
        paper = paper_path.read_text(encoding="utf-8", errors="ignore") if paper_path.exists() else ""

        prompt = {
            "pass": "PASS2",
            "instructions": (
                "You have not seen the codebase. You have not seen any prior analysis.\n"
                "You are CODEC Pass 2. Read ONLY PAPER.md content. Reimplement the methodology from spec alone, "
                "flag underspecified details, and rate reproducibility 1-5."
            ),
            "context": {"methods_text": paper},
        }
        llm_out = self._call_llm(prompt)
        out = self.output_dir / self.run_id / "codec_pass2.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(str(llm_out), encoding="utf-8")
        return str(llm_out)

    def _compare(self, pass1: str, pass2: str) -> str:
        diff = list(difflib.unified_diff(pass1.splitlines(), pass2.splitlines(), lineterm=""))
        mismatches = [
            "# CODEC mismatch report",
            f"model: {self._model_name}",
            "temperature: 0",
            f"timestamp_utc: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
            "",
        ]
        if not diff:
            mismatches.append("No discrepancies detected.")
        else:
            p1 = pass1.lower()
            p2 = pass2.lower()
            critical_terms = [
                "sharpe",
                "garch",
                "markov",
                "bootstrap",
                "bonferroni",
                "concentration",
                "momentum",
            ]
            missing = [t for t in critical_terms if (t in p1) != (t in p2)]
            intersection = sum(1 for t in critical_terms if t in p1 and t in p2)
            similarity = intersection / max(len(critical_terms), 1)

            mismatches.append("section: methodology")
            if len(missing) >= 2:
                mismatches.append(
                    "issue: critical specification terms are asymmetric across code and paper-derived passes"
                )
                mismatches.append("severity: Major")
            elif len(missing) == 1:
                mismatches.append("issue: one critical term is asymmetric across passes")
                mismatches.append("severity: Minor")
            elif similarity < 0.5:
                mismatches.append("issue: weak semantic overlap between implementation and specification text")
                mismatches.append("severity: Major")
            else:
                mismatches.append("issue: wording differences detected but core terms align")
                mismatches.append("severity: Minor")
            mismatches.append("code_location: agents/*")
            mismatches.append("paper_location: PAPER.md methods/statistical sections")
            if missing:
                mismatches.append(f"missing_terms: {', '.join(missing)}")
            mismatches.append(f"term_overlap_ratio: {similarity:.2f}")
            mismatches.append("")
            mismatches.extend(diff[:40])

        report = "\n".join(mismatches) + "\n"
        out = self.output_dir / self.run_id / "codec_mismatch.md"
        out.write_text(report, encoding="utf-8")
        return report

    @staticmethod
    def _revision_number_from_name(path: Path) -> int:
        stem = path.stem
        if "_v" in stem:
            try:
                return int(stem.rsplit("_v", 1)[1])
            except ValueError:
                return -1
        return -1

    def _call_llm(self, payload: dict) -> str:
        if self.llm_client is None:
            try:
                from dotenv import load_dotenv
            except Exception:
                def load_dotenv(*_args, **_kwargs):
                    return False

            load_dotenv()
            from openai import OpenAI

            client = OpenAI()
            system_prompt = (
                "You are a rigorous audit model. Return markdown only. "
                "Do not invent unseen context and do not use sources outside the provided context."
            )
            user_prompt = (
                f"PASS: {payload.get('pass')}\n"
                f"INSTRUCTIONS:\n{payload.get('instructions','')}\n\n"
                f"CONTEXT:\n{json.dumps(payload.get('context', {}))}\n"
            )
            resp = client.chat.completions.create(
                model=self._model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
            )
            return (resp.choices[0].message.content or "").strip()
        if callable(self.llm_client):
            return str(self.llm_client(payload))
        if hasattr(self.llm_client, "call"):
            return str(self.llm_client.call(**payload))
        if hasattr(self.llm_client, "complete"):
            return str(self.llm_client.complete(**payload))
        return str(payload)

    def _write_result(self, flag: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(agent_results)")}
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            if {"run_id", "agent", "result_flag", "created_at"}.issubset(cols):
                conn.execute(
                    "INSERT INTO agent_results (run_id, agent, job, result_flag, created_at) VALUES (?, ?, ?, ?, ?)",
                    (self.run_id, "CODEC", None, flag, now),
                )
            elif {"result_id", "run_id", "phase_name", "agent_name", "status", "created_at"}.issubset(cols):
                import uuid
                conn.execute(
                    """
                    INSERT INTO agent_results (result_id, run_id, phase_name, agent_name, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (uuid.uuid4().hex, self.run_id, "CODEC", "CODEC", flag, now),
                )
            else:
                raise RuntimeError("Unsupported agent_results schema in codec writer")
            conn.commit()
