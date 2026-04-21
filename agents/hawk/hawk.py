"""HAWK agent: hostile reviewer and revision gate."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class HawkAgent:
    RUBRIC_KEYS = [
        "contribution_novelty",
        "identification_validity",
        "methodology_correctness",
        "robustness_evidence",
        "internal_consistency",
        "economic_significance",
        "presentation_quality",
    ]

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
        self._last_user_prompt: str = ""

    def run(self, revision_number: int = 1) -> dict:
        context = self._load_review_context()
        scores = self._score_rubric(context)
        comments = self._write_review(context=context, scores=scores, revision_number=revision_number)

        out_dir = self.output_dir / self.run_id
        out_dir.mkdir(parents=True, exist_ok=True)

        scores_path = out_dir / f"hawk_scores_v{revision_number}.json"
        review_path = out_dir / f"hawk_review_v{revision_number}.md"

        scores_path.write_text(json.dumps(scores, indent=2), encoding="utf-8")
        review_path.write_text(self._render_review_markdown(comments), encoding="utf-8")

        result_flag = self._decide(comments, scores, revision_number)
        self._write_result_flag(result_flag)

        return {
            "result_flag": result_flag,
            "scores_path": str(scores_path),
            "review_path": str(review_path),
            "scores": scores,
            "comments": comments,
            "prompt_preview": self._last_user_prompt[:300],
        }

    def _load_review_context(self) -> dict[str, str]:
        base = self.output_dir / self.run_id
        drafts = sorted(base.glob("paper_draft_v*.tex"), key=self._revision_number_from_name)
        current_paper = drafts[-1] if drafts else base / "paper_draft_v1.tex"

        codec_spec_path = self._first_existing(base / "codec_spec.md", base / "codecspec.md")
        mismatch_path = self._first_existing(base / "codec_mismatch.md", base / "codecmismatch.md")
        stats_csv_blob = ""
        stats_parts: list[str] = []
        seen: set[str] = set()
        stats_dirs = [base / "stats_tables", base / "statstables"]
        for d in stats_dirs:
            if not d.exists() or not d.is_dir():
                continue
            for p in sorted(d.glob("*.csv")):
                if p.name in seen:
                    continue
                seen.add(p.name)
                stats_parts.append(f"## FILE: {p.name}\n" + p.read_text(encoding="utf-8", errors="ignore"))
        if stats_parts:
            stats_csv_blob = "\n\n".join(stats_parts)

        stats_dir = self._first_existing(base / "stats_tables", base / "statstables")
        pap_lock_status = self._pap_lock_status()

        return {
            "paper_draft": current_paper.read_text(encoding="utf-8", errors="ignore") if current_paper.exists() else "",
            "codec_spec": codec_spec_path.read_text(encoding="utf-8", errors="ignore") if codec_spec_path else "",
            "stats_tables_csv": stats_csv_blob,
            "codec_mismatch": mismatch_path.read_text(encoding="utf-8", errors="ignore") if mismatch_path else "",
            "pap_lock_status": pap_lock_status,
            "paper_path": str(current_paper),
            "codec_spec_path": str(codec_spec_path) if codec_spec_path else "",
            "stats_dir": str(stats_dir) if stats_dir else "",
            "codec_mismatch_path": str(mismatch_path) if mismatch_path else "",
        }

    @staticmethod
    def _revision_number_from_name(path: Path) -> int:
        m = re.search(r"_v(\d+)\.tex$", path.name)
        return int(m.group(1)) if m else -1

    def _build_user_prompt(self, context: dict[str, str]) -> str:
        paper_text = context.get("paper_draft", "")
        if len(paper_text) <= 14000:
            paper_excerpt = paper_text
        else:
            # Use head + tail so scores are not biased by missing later sections.
            paper_excerpt = paper_text[:9000] + "\n\n[...snip...]\n\n" + paper_text[-5000:]
        stats_text = context.get("stats_tables_csv", "")
        codec_text = context.get("codec_spec", "")
        mismatch_text = context.get("codec_mismatch", "")
        pap_lock_status = context.get("pap_lock_status", "")

        return (
            "Score the paper on this rubric using integers 1-5 only:\n"
            + "\n".join(f"- {k}" for k in self.RUBRIC_KEYS)
            + "\n\nReturn strict JSON with these exact keys only.\n\n"
            "You MUST use the full provided context.\n"
            "If evidence is missing, lower the score and justify later in review comments.\n\n"
            f"PAPER DRAFT (head+tail excerpt):\n{paper_excerpt}\n\n"
            f"STATS TABLES (all CSV rows):\n{stats_text}\n\n"
            f"CODEC SPEC:\n{codec_text}\n\n"
            f"CODEC MISMATCH:\n{mismatch_text}\n\n"
            f"RUN PAP LOCK STATUS:\n{pap_lock_status}\n"
        )

    def _score_rubric(self, context: dict[str, str]) -> dict[str, int]:
        if self.llm_client is not None:
            payload = {
                "task": "score_rubric",
                "rubric_keys": self.RUBRIC_KEYS,
                "context": context,
            }
            if callable(self.llm_client):
                raw = str(self.llm_client(payload))
            elif hasattr(self.llm_client, "call"):
                raw = str(self.llm_client.call(**payload))
            else:
                raw = ""
            parsed = self._extract_scores_from_text(raw)
            if parsed:
                return parsed
            raise ValueError("GPT-5.4 returned unparseable scores: " + raw[:200])

        try:
            from dotenv import load_dotenv
        except Exception:
            def load_dotenv(*_args, **_kwargs):
                return False

        load_dotenv()

        from openai import OpenAI

        client = OpenAI()
        system_prompt = "You are HAWK, a hostile empirical finance reviewer. Score strictly 1-5."
        user_prompt = self._build_user_prompt(context)
        self._last_user_prompt = user_prompt

        resp = client.chat.completions.create(
            model="gpt-5.4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        raw = (resp.choices[0].message.content or "{}").strip()
        parsed = self._extract_scores_from_text(raw)
        if parsed is None:
            raise ValueError("GPT-5.4 returned unparseable scores: " + raw[:200])
        return parsed

    def _write_review(self, context: dict[str, str], scores: dict[str, int], revision_number: int) -> list[dict[str, str]]:
        low_dims = [k for k in self.RUBRIC_KEYS if int(scores.get(k, 0)) < 4]
        if not low_dims:
            return []

        numbered_paper = self._number_paper(context.get("paper_draft", ""))

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
                "You are HAWK write_review. Produce specific, actionable finance-review comments only. "
                "Use the run PAP lock status as source of truth for commitment state. "
                "Do not infer commitment from static template text in PAPER.md."
            )
            user_prompt = (
                "For each low-scoring rubric dimension, output one JSON object with fields:\n"
                "section, issue, severity, required_action\n"
                "Rules:\n"
                "1) Quote the exact weak sentence from the paper.\n"
                "2) Include section name and approximate line number.\n"
                "3) Explain the specific methodological/evidentiary problem.\n"
                "4) required_action must be exact and testable (table/check/citation/estimator change).\n"
                "5) No boilerplate placeholders.\n"
                "Return JSON: {\"comments\": [ ... ]}.\n\n"
                f"Revision: {revision_number}\n"
                f"Low scoring dimensions: {low_dims}\n\n"
                f"SCORES:\n{json.dumps(scores)}\n\n"
                f"PAPER WITH LINE NUMBERS:\n{numbered_paper}\n\n"
                f"STATS TABLES:\n{context.get('stats_tables_csv','')}\n\n"
                f"CODEC SPEC:\n{context.get('codec_spec','')}\n\n"
                f"CODEC MISMATCH:\n{context.get('codec_mismatch','')}\n"
                f"RUN PAP LOCK STATUS:\n{context.get('pap_lock_status','')}\n"
            )
            resp = client.chat.completions.create(
                model="gpt-5.4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            raw = (resp.choices[0].message.content or "{}").strip()
            parsed = self._extract_comments(raw)
            if parsed:
                return parsed

        return self._fallback_specific_comments(context=context, scores=scores)

    @staticmethod
    def _extract_comments(raw: str) -> list[dict[str, str]]:
        try:
            obj = json.loads(raw)
            comments = obj.get("comments", []) if isinstance(obj, dict) else []
            out = []
            for c in comments:
                if not isinstance(c, dict):
                    continue
                section = str(c.get("section", "")).strip()
                issue = str(c.get("issue", "")).strip()
                severity = str(c.get("severity", "Major")).strip()
                action = str(c.get("required_action", "")).strip()
                if section and issue and action:
                    out.append(
                        {
                            "section": section,
                            "issue": issue,
                            "severity": severity if severity in {"Fatal", "Major", "Minor"} else "Major",
                            "required_action": action,
                        }
                    )
            return out
        except Exception:
            return []

    def _fallback_specific_comments(self, context: dict[str, str], scores: dict[str, int]) -> list[dict[str, str]]:
        sections = self._section_index(context.get("paper_draft", ""))
        comments: list[dict[str, str]] = []

        dim_to_section = {
            "contribution_novelty": "Introduction",
            "identification_validity": "Methodology",
            "methodology_correctness": "Methodology",
            "robustness_evidence": "Robustness",
            "internal_consistency": "Results",
            "economic_significance": "Results",
            "presentation_quality": "Discussion",
        }

        for dim in self.RUBRIC_KEYS:
            score = int(scores.get(dim, 0))
            if score >= 4:
                continue
            target_sec = dim_to_section.get(dim, "Introduction")
            line_no, quote = self._find_quote_for_section(sections, target_sec)
            severity = "Fatal" if score <= 2 else "Major"
            comments.append(
                {
                    "section": f"{target_sec} (line ~{line_no})",
                    "issue": (
                        f"Quoted sentence: \"{quote}\". This evidence is insufficient for '{dim}' because "
                        "the claim is not linked to a verifiable estimator output or explicit identification control."
                    ),
                    "severity": severity,
                    "required_action": (
                        "Add a sentence-level method/result link with exact table/metric references and include one "
                        "explicit validation check (e.g., Newey-West result, bootstrap interval, or subperiod robustness)."
                    ),
                }
            )
        return comments

    @staticmethod
    def _number_paper(text: str) -> str:
        lines = text.splitlines()
        return "\n".join(f"{i+1:04d}: {ln}" for i, ln in enumerate(lines))

    @staticmethod
    def _section_index(text: str) -> list[dict[str, Any]]:
        lines = text.splitlines()
        out: list[dict[str, Any]] = []
        current = {"name": "Preamble", "start": 1, "lines": []}
        for i, ln in enumerate(lines, start=1):
            s = ln.strip()
            if s.startswith("\\section"):
                out.append(current)
                name = re.sub(r"\\section\*?\{([^}]*)\}.*", r"\1", s)
                current = {"name": name if name != s else "Section", "start": i, "lines": []}
            current["lines"].append((i, ln))
        out.append(current)
        return out

    @staticmethod
    def _find_quote_for_section(sections: list[dict[str, Any]], target: str) -> tuple[int, str]:
        target_l = target.lower()
        chosen = None
        for sec in sections:
            if target_l in str(sec.get("name", "")).lower():
                chosen = sec
                break
        if chosen is None:
            chosen = sections[0] if sections else {"lines": [(1, "")], "start": 1}

        for ln_no, ln in chosen.get("lines", []):
            text = ln.strip()
            if text and not text.startswith("\\section"):
                return int(ln_no), text[:280]
        start = int(chosen.get("start", 1))
        return start, "[No non-empty sentence found in this section]"

    @staticmethod
    def _render_review_markdown(comments: list[dict[str, str]]) -> str:
        if not comments:
            return "# HAWK Review\n\nNo blocking issues found.\n"

        lines = ["# HAWK Review", ""]
        for c in comments:
            lines.append(f"Section: {c['section']}")
            lines.append(f"Issue: {c['issue']}")
            lines.append(f"Severity: {c['severity']}")
            lines.append(f"Required action: {c['required_action']}")
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _decide(comments: list[dict[str, str]], scores: dict[str, int], revision_number: int) -> str:
        severities = [c.get("severity", "") for c in comments]
        fatal_count = sum(1 for s in severities if s == "Fatal")
        major_count = sum(1 for s in severities if s == "Major")

        if revision_number >= 3 and (fatal_count > 0 or major_count > 2):
            return "ESCALATE"
        if fatal_count > 0:
            return "REVISION_REQUESTED"
        if major_count > 2:
            return "REVISION_REQUESTED"
        if all(int(scores.get(k, 0)) >= 4 for k in HawkAgent.RUBRIC_KEYS):
            return "APPROVED"
        return "REVISION_REQUESTED"

    def _pap_lock_status(self) -> str:
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    """
                    SELECT locked_at, locked_by, pap_sha256, forge_started_at
                    FROM pap_lock
                    WHERE run_id=?
                    ORDER BY locked_at DESC
                    LIMIT 1
                    """,
                    (self.run_id,),
                ).fetchone()
            if row is None:
                return "NO_PAP_LOCK_ROW"
            locked_at, locked_by, pap_sha, forge_started_at = row
            return (
                f"locked_at={locked_at}; locked_by={locked_by}; "
                f"pap_sha256={'present' if pap_sha else 'missing'}; forge_started_at={forge_started_at}"
            )
        except Exception as exc:
            return f"PAP_LOCK_LOOKUP_ERROR: {exc}"

    @staticmethod
    def _extract_scores_from_text(text: str) -> dict[str, int] | None:
        text = text.strip()
        if not text:
            return None

        try:
            obj = json.loads(text)
            parsed = {k: int(obj[k]) for k in HawkAgent.RUBRIC_KEYS if k in obj}
            if len(parsed) == len(HawkAgent.RUBRIC_KEYS):
                return {k: max(1, min(5, v)) for k, v in parsed.items()}
        except Exception:
            pass

        parsed: dict[str, int] = {}
        for k in HawkAgent.RUBRIC_KEYS:
            m = re.search(rf"{re.escape(k)}\s*[:=]\s*([1-5])", text)
            if m:
                parsed[k] = int(m.group(1))
        if len(parsed) == len(HawkAgent.RUBRIC_KEYS):
            return parsed
        return None

    def _write_result_flag(self, status: str) -> None:
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with sqlite3.connect(self.db_path) as conn:
            cols = [row[1] for row in conn.execute("PRAGMA table_info(agent_results)")]
            if {"run_id", "agent", "result_flag", "created_at"}.issubset(cols):
                conn.execute(
                    "INSERT INTO agent_results (run_id, agent, job, result_flag, created_at) VALUES (?, ?, ?, ?, ?)",
                    (self.run_id, "HAWK", None, status, created_at),
                )
            elif {"result_id", "run_id", "phase_name", "agent_name", "status", "created_at"}.issubset(cols):
                conn.execute(
                    """
                    INSERT INTO agent_results (result_id, run_id, phase_name, agent_name, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (uuid.uuid4().hex, self.run_id, "HAWK", "HAWK", status, created_at),
                )
            conn.commit()

    @staticmethod
    def _first_existing(*paths: Path) -> Path | None:
        for p in paths:
            if p.exists():
                return p
        return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run HAWK hostile-review agent.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--db-path", default="state.db")
    parser.add_argument("--output-dir", default="paper_memory")
    parser.add_argument("--revision-number", type=int, default=1)
    args = parser.parse_args()

    result = HawkAgent(run_id=args.run_id, db_path=args.db_path, output_dir=args.output_dir).run(
        revision_number=args.revision_number
    )
    print(json.dumps(result, indent=2))
