"""HAWK agent: Journal of Finance-standard referee and pipeline router."""

from __future__ import annotations

import json
import re
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


class HawkAgent:
    def __init__(
        self,
        run_id: str,
        db_path: str = "state.db",
        output_dir: str = "paper_memory",
        llm_client=None,
    ) -> None:
        self.run_id = run_id
        self.db_path = db_path
        self.output_dir = Path(output_dir)
        self.llm_client = llm_client

    def run(self, revision_number: int = 1) -> dict:
        context = self._load_review_context()
        report = self._write_referee_report(context, revision_number)
        if len(report.strip()) < 500:
            # Enforce artifact quality/size contract.
            for _ in range(3):
                report = self._write_referee_report(context, revision_number)
                if len(report.strip()) >= 500:
                    break
            if len(report.strip()) < 500:
                raise RuntimeError("HAWK report generation failed size gate (<500 bytes).")
        routing = self._parse_routing(report)
        methodology_score = self._score_methodology_rubric(context)
        routing["methodology_score_10"] = methodology_score

        out_dir = self.output_dir / self.run_id
        out_dir.mkdir(parents=True, exist_ok=True)

        report_path = out_dir / f"hawk_review_v{revision_number}.md"
        routing_path = out_dir / f"hawk_routing_v{revision_number}.json"
        report_path.write_text(report, encoding="utf-8")
        routing_path.write_text(json.dumps(routing, indent=2), encoding="utf-8")

        flag = self._decide(routing, revision_number)
        self._write_result_flag(flag)

        return {
            "result_flag": flag,
            "recommendation": routing.get("recommendation", "MAJOR_REVISION"),
            "report_path": str(report_path),
            "routing_path": str(routing_path),
            "routing": routing,
        }

    def _load_review_context(self) -> dict:
        base = self.output_dir / self.run_id
        drafts = sorted(
            base.glob("paper_draft_v*.tex"),
            key=lambda p: int(re.search(r"_v(\d+)\.tex$", p.name).group(1))
            if re.search(r"_v(\d+)\.tex$", p.name)
            else -1,
        )
        paper = drafts[-1].read_text(encoding="utf-8") if drafts else ""

        stats_parts: list[str] = []
        seen: set[str] = set()
        for d in [base / "stats_tables", base / "statstables"]:
            if d.exists():
                for p in sorted(d.glob("*.csv")):
                    if p.name in seen:
                        continue
                    seen.add(p.name)
                    stats_parts.append(f"## {p.name}\n" + p.read_text(encoding="utf-8"))
        stats = "\n\n".join(stats_parts)

        codec_spec_path = self._first_existing(base / "codec_spec.md", base / "codecspec.md")
        mismatch_path = self._first_existing(base / "codec_mismatch.md", base / "codecmismatch.md")
        codec_spec = codec_spec_path.read_text(encoding="utf-8") if codec_spec_path else ""
        mismatch = mismatch_path.read_text(encoding="utf-8") if mismatch_path else ""

        pap_status = self._pap_lock_status()

        return {
            "paper_draft": paper,
            "stats_tables_csv": stats,
            "codec_spec": codec_spec,
            "codec_mismatch": mismatch,
            "pap_lock_status": pap_status,
        }

    def _write_referee_report(self, context: dict, revision_number: int) -> str:
        system_prompt = """You are a senior referee for the Journal of Finance.
You have reviewed 200+ empirical finance papers over 20 years.
You are rigorous, direct, and specific. You identify exact problems.

Your referee report must follow this EXACT structure:

## Summary
One paragraph: what the paper attempts, whether the identification is valid,
and your overall read. Be direct. Do not hedge.

## Mandatory revision items
Each item must have ALL of these:
- Section and line reference (e.g., "Section 3, line 47")
- The exact problem stated as economic/statistical logic
- What specific analysis or evidence would resolve it
- Which pipeline component is responsible (tag EXACTLY one):
  [FORGE] if the simulation needs redesigning
  [SIGMA] if an additional statistical test must be run
  [MINER] if there is a data quality or coverage issue
  [QUILL] if the writing is unclear, inconsistent, or overclaiming
  [CODEC] if the code does not implement what the paper claims

## Optional suggestions
Improvements that would strengthen but are not blocking.
Each tagged with the responsible component.

## Decision
Exactly one of: REJECT / MAJOR_REVISION / MINOR_REVISION / ACCEPT

Decision rules:
- REJECT: fundamental identification flaw, results not reproducible,
  or critical CODEC mismatch unresolved
- MAJOR_REVISION: missing pre-committed tests, weak identification,
  numbers inconsistent between abstract and tables
- MINOR_REVISION: presentation issues, missing robustness checks,
  minor inconsistencies
- ACCEPT: all pre-committed tests run and reported, results honestly
  stated, methods match code, CODEC clean

Never give numeric scores. Never be vague. Every mandatory item
must have an exact fix that a researcher can execute.

If CODEC mismatch shows FAIL: this is automatically a REJECT or
MAJOR_REVISION with a [CODEC] mandatory item."""

        paper = context.get("paper_draft", "")
        if len(paper) > 12000:
            paper = paper[:8000] + "\n\n[...middle truncated...]\n\n" + paper[-4000:]

        user_prompt = (
            f"Referee report for revision {revision_number}.\n\n"
            f"PAPER DRAFT:\n{paper}\n\n"
            f"STATISTICAL RESULTS:\n{context.get('stats_tables_csv','')[:4000]}\n\n"
            f"CODEC AUDIT STATUS:\n{context.get('codec_mismatch','')[:2000]}\n\n"
            f"PAP LOCK STATUS:\n{context.get('pap_lock_status','')}\n\n"
            "Write the complete referee report now."
        )

        return self._call_llm(system_prompt, user_prompt, max_completion_tokens=3000)

    def _parse_routing(self, report: str) -> dict:
        prompt = (
            "Extract routing instructions from this referee report as JSON.\n\n"
            "Return EXACTLY this structure:\n"
            "{\n"
            '  "recommendation": "REJECT|MAJOR_REVISION|MINOR_REVISION|ACCEPT",\n'
            '  "mandatory_items": [\n'
            "    {\n"
            '      "item_number": 1,\n'
            '      "agent": "FORGE|SIGMA|MINER|QUILL|CODEC",\n'
            '      "issue": "exact problem description",\n'
            '      "required_action": "exactly what must be done",\n'
            '      "blocking": true\n'
            "    }\n"
            "  ],\n"
            '  "optional_items": [\n'
            "    {\n"
            '      "item_number": 1,\n'
            '      "agent": "QUILL",\n'
            '      "suggestion": "description"\n'
            "    }\n"
            "  ],\n"
            '  "routes_to_forge": false,\n'
            '  "routes_to_sigma": false,\n'
            '  "routes_to_miner": false,\n'
            '  "routes_to_quill": false,\n'
            '  "routes_to_codec": false\n'
            "}\n\n"
            "Set routes_to_X = true if ANY mandatory item has agent = X.\n"
            "Return ONLY valid JSON. No markdown fences.\n\n"
            f"REFEREE REPORT:\n{report}"
        )
        raw = self._call_llm(
            "You extract structured JSON from referee reports.",
            prompt,
            max_completion_tokens=2000,
        )
        try:
            clean = re.sub(r"```json|```", "", raw).strip()
            parsed = json.loads(clean)
            parsed.setdefault("mandatory_items", [])
            parsed.setdefault("optional_items", [])
            for key in ["routes_to_forge", "routes_to_sigma", "routes_to_miner", "routes_to_quill", "routes_to_codec"]:
                parsed.setdefault(key, False)
            return parsed
        except Exception:
            return {
                "recommendation": "MAJOR_REVISION",
                "mandatory_items": [],
                "optional_items": [],
                "routes_to_forge": False,
                "routes_to_sigma": False,
                "routes_to_miner": False,
                "routes_to_quill": True,
                "routes_to_codec": False,
            }

    @staticmethod
    def _decide(routing: dict, revision_number: int) -> str:
        rec = routing.get("recommendation", "MAJOR_REVISION")
        mandatory = routing.get("mandatory_items", [])
        blocking = [m for m in mandatory if m.get("blocking", True)]

        # Zero blocking items = nothing left to fix = ACCEPT
        if not blocking:
            return "APPROVED"

        if rec == "ACCEPT":
            return "APPROVED"

        if rec == "REJECT":
            return "ESCALATE" if revision_number >= 3 else "REVISION_REQUESTED"

        if blocking and revision_number >= 5:
            return "ESCALATE"

        return "REVISION_REQUESTED"

    def _score_methodology_rubric(self, context: dict) -> float:
        prompt = (
            "Score the paper methodology from 1 to 10 using strict finance-review standards.\n"
            "Return JSON only: {\"methodology_score_10\": <number>}.\n\n"
            f"PAPER:\n{context.get('paper_draft', '')[:6000]}\n\n"
            f"STATS:\n{context.get('stats_tables_csv', '')[:3000]}\n"
        )
        raw = self._call_llm(
            "You are a strict methodology scorer. Return valid JSON only.",
            prompt,
            max_completion_tokens=300,
        )
        try:
            clean = re.sub(r"```json|```", "", raw).strip()
            parsed = json.loads(clean)
            score = float(parsed.get("methodology_score_10", 0.0))
            return max(0.0, min(10.0, score))
        except Exception:
            return 0.0

    def _call_llm(self, system: str, user: str, max_completion_tokens: int = 2000) -> str:
        if self.llm_client is not None:
            if callable(self.llm_client):
                return str(self.llm_client({"system": system, "user": user}))

        try:
            from dotenv import load_dotenv
        except Exception:
            def load_dotenv(*a, **k):
                return False

        load_dotenv()
        from agents.llm_client import get_client

        delay = 2.0
        for attempt in range(1, 11):
            try:
                client, model = get_client("HAWK")
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    max_completion_tokens=max_completion_tokens,
                    temperature=0.1,
                    timeout=120,
                )
                return (resp.choices[0].message.content or "").strip()
            except Exception as exc:
                msg = str(exc).lower()
                if "86400" in msg:
                    raise RuntimeError("Daily quota exhausted — do not retry.") from exc
                retryable = ("rate limit" in msg) or ("429" in msg) or ("timeout" in msg) or ("temporar" in msg)
                if attempt >= 10 or not retryable:
                    raise
                time.sleep(delay)
                delay = min(delay * 2.0, 120.0)
        raise RuntimeError("HAWK LLM call retries exhausted unexpectedly.")

    def _pap_lock_status(self) -> str:
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    "SELECT locked_at, locked_by, pap_sha256, forge_started_at "
                    "FROM pap_lock WHERE run_id=? ORDER BY locked_at DESC LIMIT 1",
                    (self.run_id,),
                ).fetchone()
            if row is None:
                return "NO_PAP_LOCK_ROW — pre-registration not completed"
            locked_at, locked_by, pap_sha, forge_started = row
            return (
                f"locked_at={locked_at}; locked_by={locked_by}; "
                f"pap_sha256={'present' if pap_sha else 'MISSING'}; "
                f"forge_started_at={forge_started}; "
                f"temporal_ordering={'VERIFIED' if locked_at and forge_started and locked_at < forge_started else 'CHECK NEEDED'}"
            )
        except Exception as exc:
            return f"PAP_LOCK_LOOKUP_ERROR: {exc}"

    def _write_result_flag(self, flag: str) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with sqlite3.connect(self.db_path) as conn:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(agent_results)")}
            if {"run_id", "agent", "result_flag", "created_at"}.issubset(cols):
                conn.execute(
                    "INSERT INTO agent_results "
                    "(run_id, agent, job, result_flag, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (self.run_id, "HAWK", None, flag, now),
                )
            elif {"result_id", "run_id", "phase_name", "agent_name", "status", "created_at"}.issubset(cols):
                conn.execute(
                    "INSERT INTO agent_results "
                    "(result_id, run_id, phase_name, agent_name, status, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (uuid.uuid4().hex, self.run_id, "HAWK", "HAWK", flag, now),
                )
            conn.commit()

    @staticmethod
    def _first_existing(*candidates: Path) -> Path | None:
        for p in candidates:
            if p.exists():
                return p
        return None
