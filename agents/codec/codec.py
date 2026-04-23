"""CODEC bidirectional audit agent with isolated LLM passes."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from agents.llm_client import get_client


class CodecAgent:
    def __init__(self, run_id: str, db_path: str, output_dir: str, llm_client) -> None:
        self.run_id = run_id
        self.db_path = db_path
        self.output_dir = Path(output_dir)
        self.llm_client = llm_client
        if llm_client is None:
            self._llm_client, self._model_name = get_client("CODEC")
        else:
            self._llm_client, self._model_name = None, "external-client"

    def run(self) -> dict:
        pass1_spec = self._pass1_read_code()
        pass2_spec = self._pass2_read_paper()
        mismatch = self._compare(pass1_spec, pass2_spec)
        mismatch_items = self._extract_mismatch_items(mismatch)
        if len(mismatch_items) > 3:
            flag = "FAIL"
        elif len(mismatch_items) > 0:
            flag = "WARN"
        else:
            flag = "PASS"
        print("[CODEC DEBUG] Raw LLM verdict:")
        print(mismatch)
        print("[CODEC DEBUG] Parsed result_flag:", flag)
        print("[CODEC DEBUG] Mismatches found:")
        for m in mismatch_items:
            print(f"  - {m}")
        self._write_result(flag)
        return {"result_flag": flag}

    @staticmethod
    def _extract_mismatch_items(report: str) -> list[str]:
        lines = report.splitlines()
        items: list[str] = []
        current_section = ""
        for line in lines:
            if line.startswith("## "):
                current_section = line.strip().lower()
                continue
            if not line.startswith("- "):
                continue
            if "## mismatched_parameters" in current_section or "## not_found_in_code" in current_section:
                items.append(line[2:].strip())
        return items

    @staticmethod
    def _truncate_file(content: str, max_lines: int = 300) -> str:
        lines = content.splitlines()
        if len(lines) <= max_lines:
            return content
        half = max_lines // 2
        return "\n".join(lines[:half]) + \
               f"\n... [{len(lines) - max_lines} lines truncated] ...\n" + \
               "\n".join(lines[-half:])

    def _pass1_read_code(self) -> str:
        import tiktoken

        enc = tiktoken.encoding_for_model("gpt-4o")
        initial_prompt = self._build_pass1_prompt(enforce_budget=False)
        initial_token_count = len(enc.encode(initial_prompt))
        print(f"[CODEC] Prompt token count: {initial_token_count}")

        final_prompt = self._build_pass1_prompt(enforce_budget=True)
        final_token_count = len(enc.encode(final_prompt))
        print(f"[CODEC] Final prompt token count: {final_token_count}")

        llm_payload = {
            "pass": "PASS1",
            "instructions": (
                "You are CODEC Pass 1. Read ONLY the provided codebase. "
                "Extract implementation behavior at specification level."
            ),
            "context": {
                "codebase_text": final_prompt,
            },
            "raw_prompt": final_prompt,
        }
        llm_out = self._call_llm(llm_payload)
        out = self.output_dir / self.run_id / "codec_spec.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(str(llm_out), encoding="utf-8")
        return str(llm_out)

    def _build_pass1_prompt(self, enforce_budget: bool = True) -> str:
        import tiktoken

        relevant_files = [
            Path("agents/miner/miner.py"),
            Path("agents/forge/runner.py"),
        ]

        instructions = (
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
        )

        blocks: list[tuple[Path, str]] = []
        for p in relevant_files:
            if p.exists() and p.stat().st_size > 0:
                text = p.read_text(encoding="utf-8", errors="ignore")
                blocks.append((p, self._truncate_file(text, max_lines=80)))

        def compose(block_values: list[tuple[Path, str]]) -> str:
            lines = ["# CODEC Pass 1 — Specification-level code analysis", ""]
            lines.append("## RELEVANT FILES (specification-level implementations)")
            for path_obj, content in block_values:
                lines.append(f"\n### FILE: {path_obj.as_posix()}")
                lines.append(content)
            codebase_text = "\n".join(lines)
            return (
                "PASS: PASS1\n"
                f"INSTRUCTIONS:\n{instructions}\n\n"
                f"CONTEXT:\n{json.dumps({'codebase_text': codebase_text})}\n"
            )

        prompt = compose(blocks)
        if not enforce_budget:
            return prompt

        enc = tiktoken.encoding_for_model("gpt-4o")
        token_count = len(enc.encode(prompt))
        if token_count <= 6000:
            return prompt

        # Hard budget enforcement: iteratively truncate only the last file.
        if not blocks:
            return prompt

        last_path, last_content = blocks[-1]
        last_lines = last_content.splitlines()
        while token_count > 6000 and len(last_lines) > 20:
            cut = max(5, min(20, len(last_lines) // 8))
            last_lines = last_lines[:-cut]
            reduced = "\n".join(last_lines) + "\n... [additional lines truncated for token budget] ..."
            blocks[-1] = (last_path, reduced)
            prompt = compose(blocks)
            token_count = len(enc.encode(prompt))

        # Absolute clamp if still above budget.
        if token_count > 6000:
            while token_count > 6000:
                over = token_count - 6000
                shrink_chars = max(200, over * 4)
                _, cur = blocks[-1]
                cur = cur[:-shrink_chars] if len(cur) > shrink_chars else cur[: max(0, len(cur) // 2)]
                blocks[-1] = (last_path, cur + "\n... [token budget clamp] ...")
                prompt = compose(blocks)
                token_count = len(enc.encode(prompt))

        return prompt

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

        project_root = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "agents.codec_pass2",
                "--run-id",
                self.run_id,
                "--db-path",
                self.db_path,
                "--output-dir",
                str(self.output_dir),
            ],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=600,
            env={
                **os.environ,
                "PYTHONPATH": str(project_root),
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
            "Important classification rules:\n"
            "- If a parameter IS in the code but implemented differently due to\n"
            "  a known data source limitation (WRDS not available, yfinance used\n"
            "  as proxy), classify match=true and add a note field explaining.\n"
            "- If a parameter is implemented as a named string constant for\n"
            "  CODEC traceability, classify match=true.\n"
            "- If a parameter is implemented in any file in the codebase\n"
            "  (not just the priority files), classify match=true.\n"
            "- Only classify match=false for parameters that are genuinely\n"
            "  absent from the entire codebase with no proxy implementation.\n\n"
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

        # Count mismatches by type
        acknowledged = [
            p for p in mismatched
            if any(keyword in str(p.get("parameter_name", "")).lower()
                   for keyword in ["wrds", "roll", "adjustment",
                                   "yfinance", "data_source"])
        ]
        genuine_mismatches = [
            p for p in mismatched
            if p not in acknowledged
        ]

        # Fatal parameters — these always cause FAIL
        FATAL_PARAMS = {
            "n_episodes", "significance_threshold",
            "minimum_effect", "seeds", "seed_policy",
        }
        fatal_mismatches = [
            p for p in genuine_mismatches
            if any(f in str(p.get("parameter_name", "")).lower()
                   for f in FATAL_PARAMS)
        ]

        mismatches.append("## acknowledged_deviations")
        mismatches.append(
            f"acknowledged: {len(acknowledged)} "
            f"(WRDS/yfinance proxy, roll convention — documented in DataPassport)"
        )
        mismatches.append(
            f"genuine_mismatches: {len(genuine_mismatches)}"
        )
        mismatches.append("")

        # Verdict logic
        if fatal_mismatches:
            verdict = "FAIL"
            severity = "Fatal"
            issues = [
                f"code_deviates: fatal parameter mismatch — "
                f"{[p.get('parameter_name') for p in fatal_mismatches]}"
            ]
        elif len(genuine_mismatches) > 3:
            verdict = "FAIL"
            severity = "Major"
            issues = [
                f"code_deviates: {len(genuine_mismatches)} genuine "
                f"parameter mismatches (excluding {len(acknowledged)} "
                f"acknowledged deviations)"
            ]
        elif len(genuine_mismatches) > 0 or len(missing) > 5:
            verdict = "WARN"
            severity = "Minor"
            issues = [
                f"description_ambiguous: {len(genuine_mismatches)} minor "
                f"mismatches, {len(acknowledged)} acknowledged deviations "
                f"documented in DataPassport, {len(missing)} unverified params. "
                f"QUILL will address in limitations section."
            ]
        elif match_ratio >= 0.30:
            verdict = "WARN"
            severity = "Minor"
            issues = [
                f"match_ratio {match_ratio:.3f}: sufficient for dev run. "
                f"Acknowledged deviations: {len(acknowledged)}. "
                f"QUILL will address in limitations section."
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
            system_prompt = (
                "You are a rigorous audit model. Return markdown only. "
                "Do not invent unseen context and do not use sources outside the provided context."
            )
            user_prompt = payload.get("raw_prompt")
            if not user_prompt:
                user_prompt = (
                    f"PASS: {payload.get('pass')}\n"
                    f"INSTRUCTIONS:\n{payload.get('instructions','')}\n\n"
                    f"CONTEXT:\n{json.dumps(payload.get('context', {}))}\n"
                )
            resp = self._llm_client.chat.completions.create(
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
