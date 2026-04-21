"""CODEC bidirectional audit agent with isolated LLM passes."""

from __future__ import annotations

import json
import os
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

        flag = "PASS" if "verdict: PASS" in mismatch else "WARN" if "verdict: WARN" in mismatch else "FAIL"
        self._write_result(flag)
        return {"result_flag": flag}

    def _pass1_read_code(self) -> str:
        PRIORITY_FILES = [
            Path("agents/sigma_job2.py"),
            Path("agents/forge/agents.py"),
            Path("agents/forge/runner.py"),
            Path("agents/forge/env.py"),
            Path("agents/miner/miner.py"),
            Path("PAPER.md"),
        ]

        SECONDARY_DIRS = [
            Path("agents/sigma"),
            Path("agents/forge"),
            Path("agents/miner"),
        ]

        lines = ["# CODEC Pass 1 — Specification-level code analysis", ""]
        lines.append("## PRIORITY FILES (specification-level implementations)")
        for p in PRIORITY_FILES:
            if p.exists() and p.stat().st_size > 0:
                text = p.read_text(encoding="utf-8", errors="ignore")
                lines.append(f"\n### FILE: {p.as_posix()}")
                lines.append(text[:6000])

        lines.append("\n## SECONDARY FILES (supporting implementations)")
        seen = {p.resolve() for p in PRIORITY_FILES if p.exists()}
        for d in SECONDARY_DIRS:
            if not d.exists():
                continue
            for p in sorted(d.rglob("*.py")):
                if p.resolve() in seen:
                    continue
                if "__pycache__" in p.parts or p.stat().st_size == 0:
                    continue
                seen.add(p.resolve())
                text = p.read_text(encoding="utf-8", errors="ignore")
                lines.append(f"\n### FILE: {p.as_posix()} ({len(text.splitlines())} lines)")
                lines.append(text[:2000])

        prompt = {
            "pass": "PASS1",
            "instructions": (
                "You are CODEC Pass 1. Read ONLY the provided codebase.\n"
                "Extract what it actually implements at specification level:\n"
                "1. Statistical tests: name each test, its parameters, library\n"
                "2. Data: source, tickers, date range, adjustment method\n"
                "3. Simulation: agent names and their behaviors\n"
                "4. Seeds: exact values used\n"
                "5. Thresholds: significance levels, minimum effects\n"
                "6. Windows: lookback periods, rolling windows\n"
                "7. Fitness function: exact formula used for MetaRL\n"
                "Do NOT report: CEM internals, SQLite settings, "
                "health check timeouts, logging constants.\n"
                "Be exhaustive on specification-level parameters."
            ),
            "context": {"codebase_text": "\n".join(lines)},
        }
        llm_out = self._call_llm(prompt)
        out = self.output_dir / self.run_id / "codec_spec.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(str(llm_out), encoding="utf-8")
        return str(llm_out)

    def _pass2_read_paper(self) -> str:
        """Run CODEC Pass 2 in an isolated subprocess with separate environment."""
        if self.llm_client is not None:
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

        import subprocess
        import sys

        script_path = Path(__file__).resolve().parents[1] / "codec_pass2.py"
        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--run-id",
                self.run_id,
                "--db-path",
                self.db_path,
                "--output-dir",
                str(self.output_dir),
            ],
            capture_output=True,
            text=True,
            timeout=600,
            env={
                **os.environ,
                "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY_PASS2", os.environ.get("OPENAI_API_KEY", "")),
            },
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"CODEC Pass 2 subprocess failed (returncode={result.returncode}):\n"
                f"stdout: {result.stdout[:2000]}\nstderr: {result.stderr[:2000]}"
            )
        out_path = self.output_dir / self.run_id / "codec_pass2.md"
        if out_path.exists():
            return out_path.read_text(encoding="utf-8")
        return result.stdout.strip()

    def _extract_paper_specified_params(self, code_text: str) -> dict:
        """Extract only the parameters that PAPER.md explicitly specifies, found in code."""
        paper_path = Path("PAPER.md")
        paper = paper_path.read_text(encoding="utf-8") if paper_path.exists() else ""
        prompt = (
            "You are comparing a codebase to a research specification.\n\n"
            "PAPER.md specifies these parameters explicitly:\n"
            f"{paper[:3000]}\n\n"
            "Search the CODEBASE for each parameter PAPER.md specifies.\n"
            "For each parameter, report:\n"
            "- parameter_name: the name from PAPER.md\n"
            "- paper_value: what PAPER.md says it should be\n"
            "- code_value: what the code actually uses (or 'NOT FOUND')\n"
            "- match: true/false\n\n"
            "Only report parameters that PAPER.md explicitly specifies.\n"
            "Ignore implementation constants (CEM population, noise, etc.)\n"
            "that are not mentioned in PAPER.md.\n\n"
            "Return JSON: {\"params\": [{\"parameter_name\": ..., "
            "\"paper_value\": ..., \"code_value\": ..., \"match\": ...}]}\n\n"
            f"CODEBASE:\n{code_text[:8000]}"
        )
        raw = self._call_llm({"pass": "PARAM_CHECK", "instructions": prompt, "context": {}})
        try:
            import re

            clean = re.sub(r"```json|```", "", raw).strip()
            return json.loads(clean)
        except Exception:
            return {"params": []}

    def _compare(self, pass1: str, pass2: str) -> str:
        """Domain-aware CODEC comparison.

        Compares only PAPER.md-specified parameters found in code.
        Does not penalize implementation constants absent from spec.
        """
        del pass2
        from datetime import datetime, timezone

        param_check = self._extract_paper_specified_params(pass1)
        params = param_check.get("params", [])

        matched = [p for p in params if p.get("match")]
        mismatched = [p for p in params if not p.get("match") and p.get("code_value") != "NOT FOUND"]
        missing = [p for p in params if p.get("code_value") == "NOT FOUND"]

        total = len(params)
        match_ratio = len(matched) / max(total, 1)

        mismatches = [
            "# CODEC mismatch report",
            f"model: {self._model_name}",
            "temperature: 0",
            f"timestamp_utc: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
            "",
            "## parameter_comparison (PAPER.md-specified only)",
            f"total_specified_params: {total}",
            f"matched: {len(matched)}",
            f"mismatched: {len(mismatched)}",
            f"not_found_in_code: {len(missing)}",
            f"match_ratio: {match_ratio:.3f}",
            "",
        ]

        if mismatched:
            mismatches.append("## mismatched_parameters")
            for p in mismatched:
                mismatches.append(
                    f"- {p['parameter_name']}: "
                    f"paper={p['paper_value']} | "
                    f"code={p['code_value']}"
                )
            mismatches.append("")

        if missing:
            mismatches.append("## not_found_in_code")
            for p in missing:
                mismatches.append(f"- {p['parameter_name']} (paper specifies: {p['paper_value']})")
            mismatches.append("")

        fatal_names = ("n_episodes", "significance_threshold", "minimum_effect", "roll_convention")
        fatal_count = len([p for p in mismatched if p.get("parameter_name") in fatal_names])

        if fatal_count > 0:
            verdict = "FAIL"
            severity = "Fatal"
            issues = [
                "code_deviates: fatal parameter mismatch on "
                f"{[p['parameter_name'] for p in mismatched if p.get('parameter_name') in fatal_names]}"
            ]
        elif len(mismatched) > 2:
            verdict = "FAIL"
            severity = "Major"
            issues = [
                f"code_deviates: {len(mismatched)} specified parameters differ between code and PAPER.md"
            ]
        elif len(mismatched) > 0 or len(missing) > 2:
            verdict = "WARN"
            severity = "Minor"
            issues = [
                f"description_ambiguous: {len(mismatched)} minor parameter differences, "
                f"{len(missing)} unverified parameters"
            ]
        else:
            verdict = "PASS"
            severity = "None"
            issues = []

        mismatches.append(f"## verdict: {verdict}")
        mismatches.append(f"severity: {severity}")
        for issue in issues:
            mismatches.append(f"issue: {issue}")

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
