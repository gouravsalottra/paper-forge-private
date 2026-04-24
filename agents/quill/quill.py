"""QUILL agent: deterministic verified-data LaTeX scaffold renderer."""

from __future__ import annotations

import csv
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class QuillDedupError(RuntimeError):
    """Compatibility exception retained for existing imports/tests."""


class QuillAgent:
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

    def run(self, revision_number: int = 1) -> dict[str, Any]:
        sources = self._load_sources()
        hawk = self._load_hawk_routing()

        if not hawk.get("approved_for_quill", False):
            self._write_result_flag("REVISION_REQUESTED")
            return {
                "result_flag": "REVISION_REQUESTED",
                "reason": "HAWK has not approved this run for QUILL rendering.",
                "approved_for_quill": False,
            }

        out_dir = self.output_dir / self.run_id
        out_dir.mkdir(parents=True, exist_ok=True)

        doc = self._render_tex(sources=sources, hawk=hawk)
        out_path = self._next_revision_path(out_dir, revision_number)
        out_path.write_text(doc, encoding="utf-8")

        self._write_result_flag("DONE")
        return {
            "result_flag": "DONE",
            "path": str(out_path),
            "approved_for_quill": True,
        }

    def _load_sources(self) -> dict[str, Any]:
        run_dir = self.output_dir / self.run_id
        pap = (run_dir / "pap.md").read_text(encoding="utf-8", errors="ignore") if (run_dir / "pap.md").exists() else ""

        stats_dir = self._first_existing(run_dir / "stats_tables", run_dir / "statstables")
        stats_tables: dict[str, list[dict[str, str]]] = {}
        if stats_dir and stats_dir.exists():
            for p in sorted(stats_dir.glob("*.csv")):
                stats_tables[p.name] = self._read_csv_dicts(p)

        references_path = run_dir / "references.bib"
        references_text = references_path.read_text(encoding="utf-8", errors="ignore") if references_path.exists() else ""

        return {
            "pap": pap,
            "stats_tables": stats_tables,
            "references_text": references_text,
            "references_exists": references_path.exists(),
        }

    def _load_hawk_routing(self) -> dict[str, Any]:
        run_dir = self.output_dir / self.run_id
        routings = sorted(run_dir.glob("hawk_routing_v*.json"), key=lambda p: p.name)
        if not routings:
            return {"approved_for_quill": False, "research_summary": {}, "mandatory_items": []}
        try:
            return json.loads(routings[-1].read_text(encoding="utf-8"))
        except Exception:
            return {"approved_for_quill": False, "research_summary": {}, "mandatory_items": []}

    @staticmethod
    def _read_csv_dicts(path: Path) -> list[dict[str, str]]:
        try:
            with path.open("r", encoding="utf-8", newline="") as f:
                return list(csv.DictReader(f))
        except Exception:
            return []

    def _render_tex(self, sources: dict[str, Any], hawk: dict[str, Any]) -> str:
        rs = hawk.get("research_summary", {}) or {}
        hypothesis = self._latex_escape(str(rs.get("hypothesis", "Hypothesis unavailable.")))
        primary_result = self._latex_escape(str(rs.get("primary_result", "Primary result unavailable.")))
        p_value = self._latex_escape(str(rs.get("p_value", "NA")))
        bonf = self._latex_escape(str(rs.get("bonferroni_threshold", "NA")))
        seed_consistent = self._latex_escape(str(rs.get("seed_consistent", "NA")))
        n_episodes = self._latex_escape(str(rs.get("n_episodes", "NA")))

        limitation_parts = []
        if str(rs.get("passes_bonferroni", "False")).lower() != "true":
            limitation_parts.append("the primary test did not pass the Bonferroni threshold")
        if str(rs.get("seed_consistent", "False")).lower() != "true":
            limitation_parts.append("directional consistency across seeds was not achieved")
        try:
            if int(float(str(rs.get("n_episodes", 0)))) < 500000:
                limitation_parts.append("episode count is below the 500000 production target")
        except Exception:
            pass
        limitation = "; ".join(limitation_parts) if limitation_parts else "no additional material limitations were flagged by HAWK"

        lines = [
            r"\documentclass[11pt]{article}",
            r"\usepackage[utf8]{inputenc}",
            r"\usepackage[T1]{fontenc}",
            r"\usepackage[margin=1in]{geometry}",
            r"\usepackage{booktabs}",
            r"\usepackage{longtable}",
            r"\usepackage{array}",
            r"\usepackage{natbib}",
            r"\begin{document}",
            r"\title{Verified Research Output Scaffold}",
            r"\author{Paper-Forge}",
            r"\date{\today}",
            r"\maketitle",
            r"\begin{abstract}",
            f"The pre-registered hypothesis stated in pap.md was: {hypothesis}.",
            f"The primary result was: {primary_result}; p-value={p_value} with Bonferroni threshold={bonf}.",
            f"A key limitation was that {self._latex_escape(limitation)}.",
            r"\end{abstract}",
            r"\section{Methodology}",
            self._methodology_from_pap(sources.get("pap", "")),
            r"\section{Findings}",
            r"\begin{itemize}",
            rf"\item Primary result: {primary_result}.",
            rf"\item Statistical threshold context: p-value={p_value}; Bonferroni threshold={bonf}.",
            rf"\item Seed consistency: {seed_consistent}.",
            rf"\item Episode count observed in simulation output: {n_episodes}.",
            r"\end{itemize}",
        ]

        for table_name, rows in sorted((sources.get("stats_tables") or {}).items()):
            lines.extend(self._render_stats_table_section(table_name, rows))

        if sources.get("references_exists"):
            lines.extend([
                r"\bibliographystyle{plainnat}",
                r"\bibliography{references}",
            ])

        lines.append(r"\end{document}")
        return "\n".join(lines) + "\n"

    def _methodology_from_pap(self, pap_text: str) -> str:
        if not pap_text.strip():
            return "No pap.md content was available for mechanical methodology extraction."

        # Mechanical extraction: include only key-value-like lines and list items.
        picked: list[str] = []
        for raw in pap_text.splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#") or line.startswith("-") or ":" in line or line.startswith("{") or line.startswith("}"):
                picked.append(self._latex_escape(line))
            if len(picked) >= 40:
                break
        if not picked:
            picked.append(self._latex_escape(pap_text[:1200]))

        out = [r"\begin{itemize}"]
        out.extend([f"\\item {x}" for x in picked])
        out.append(r"\end{itemize}")
        return "\n".join(out)

    def _render_stats_table_section(self, table_name: str, rows: list[dict[str, str]]) -> list[str]:
        section_title = self._latex_escape(table_name.replace("_", " ").replace(".csv", ""))
        lines = [f"\\section{{Statistics: {section_title}}}"]

        if not rows:
            lines.append("No rows available in this table.")
            return lines

        headers = list(rows[0].keys())
        col_spec = "l" + "c" * max(0, len(headers) - 1)
        lines.extend([
            r"\begin{longtable}{" + col_spec + "}",
            r"\toprule",
            " & ".join(self._latex_escape(h) for h in headers) + r" \\",
            r"\midrule",
        ])
        for row in rows:
            vals = [self._latex_escape(str(row.get(h, ""))) for h in headers]
            lines.append(" & ".join(vals) + r" \\")
        lines.extend([r"\bottomrule", r"\end{longtable}"])

        # Mechanical bullet interpretation (no generated prose)
        lines.append(r"\begin{itemize}")
        for i, row in enumerate(rows[:5], start=1):
            bits = [f"{k}={row.get(k, '')}" for k in headers[:6]]
            lines.append("\\item Row " + str(i) + ": " + self._latex_escape("; ".join(bits)))
        lines.append(r"\end{itemize}")
        return lines

    @staticmethod
    def _latex_escape(text: str) -> str:
        return (
            text.replace("\\", r"\textbackslash{}")
            .replace("&", r"\&")
            .replace("%", r"\%")
            .replace("$", r"\$")
            .replace("#", r"\#")
            .replace("_", r"\_")
            .replace("{", r"\{")
            .replace("}", r"\}")
            .replace("~", r"\textasciitilde{}")
            .replace("^", r"\textasciicircum{}")
        )

    @staticmethod
    def _next_revision_path(out_dir: Path, revision_number: int) -> Path:
        if revision_number <= 1:
            candidate = out_dir / "paper_draft_v1.tex"
            if not candidate.exists():
                return candidate
        candidate = out_dir / f"paper_draft_v{revision_number}.tex"
        if not candidate.exists():
            return candidate
        n = revision_number
        while True:
            n += 1
            c = out_dir / f"paper_draft_v{n}.tex"
            if not c.exists():
                return c

    @staticmethod
    def _quality_gate(doc: str) -> None:
        """Compatibility quality gate retained for tests."""
        refs = len(re.findall(r"\\bibitem\{", doc))
        visuals = len(re.findall(r"\\begin\{table\}|\\begin\{figure\}", doc))
        results = re.search(r"\\section\{Results\}(.*?)(?:\\section\{|\\appendix|\\end\{document\}|$)", doc, flags=re.S)
        numeric_tokens = len(re.findall(r"[-+]?\d*\.?\d+", results.group(1) if results else ""))

        errors = []
        if refs < 25:
            errors.append(f"references too low ({refs} < 25)")
        if visuals < 8:
            errors.append(f"tables/figures too low ({visuals} < 8)")
        if numeric_tokens < 20:
            errors.append(f"results numeric tokens too low ({numeric_tokens} < 20)")
        if errors:
            raise ValueError("; ".join(errors))

    def _write_result_flag(self, flag: str) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with sqlite3.connect(self.db_path) as conn:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(agent_results)")}
            if {"run_id", "agent", "result_flag", "created_at"}.issubset(cols):
                conn.execute(
                    "INSERT INTO agent_results "
                    "(run_id, agent, job, result_flag, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (self.run_id, "QUILL", None, flag, now),
                )
            elif {"result_id", "run_id", "phase_name", "agent_name", "status", "created_at"}.issubset(cols):
                conn.execute(
                    "INSERT INTO agent_results "
                    "(result_id, run_id, phase_name, agent_name, status, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (uuid.uuid4().hex, self.run_id, "QUILL", "QUILL", flag, now),
                )
            conn.commit()

    @staticmethod
    def _first_existing(*candidates: Path) -> Path | None:
        for p in candidates:
            if p and p.exists():
                return p
        return None
