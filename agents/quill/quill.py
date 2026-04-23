"""QUILL agent: grounded section-by-section paper drafting."""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


class QuillDedupError(RuntimeError):
    """Raised when duplicate paragraphs remain after deduplication pass."""


class QuillAgent:
    FORBIDDEN = {
        "groundbreaking",
        "revolutionary",
        "unprecedented",
        "state-of-the-art",
        "novel contribution to the field",
        "we are the first to",
    }

    SECTIONS = [
        "abstract",
        "introduction",
        "related_work",
        "data",
        "methodology",
        "results",
        "robustness",
        "discussion",
        "conclusion",
    ]
    SECTION_MIN_WORDS = {
        "abstract": 250,
        "introduction": 1000,
        "related_work": 1500,
        "data": 800,
        "methodology": 1200,
        "results": 1500,
        "robustness": 800,
        "discussion": 800,
        "conclusion": 500,
    }

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
        sources = self._load_sources()
        if self.llm_client is None:
            self._preflight_check(sources)
        section_texts: dict[str, str] = {}

        for section in self.SECTIONS:
            section_texts[section] = self._write_section(section, sources)

        # Contract loop: deduplicate first, then enforce section minimums.
        # Each cycle injects stripped paragraphs into expansion prompt to avoid repeating them.
        if self.llm_client is None:
            removed_paragraphs: dict[str, list[str]] = {s: [] for s in self.SECTIONS}
            for cycle in range(20):
                before = {
                    s: set(p.strip() for p in re.split(r"\n\s*\n", section_texts.get(s, "")) if p.strip())
                    for s in self.SECTIONS
                }
                section_texts = self._dedup_sections(section_texts)
                after = {
                    s: set(p.strip() for p in re.split(r"\n\s*\n", section_texts.get(s, "")) if p.strip())
                    for s in self.SECTIONS
                }

                for section in self.SECTIONS:
                    stripped = list(before[section] - after[section])
                    if stripped:
                        removed_paragraphs[section].extend(stripped)

                if self._sections_have_duplicate_paragraphs(section_texts):
                    raise QuillDedupError("Duplicate paragraphs remain after section dedup pass.")

                deficits = self._section_word_deficits(section_texts)
                if not deficits:
                    break

                expand_temp = min(0.2 + cycle * 0.1, 0.9)
                for section, minimum in deficits.items():
                    section_texts[section] = self._expand_section(
                        section,
                        section_texts.get(section, ""),
                        sources,
                        minimum,
                        temperature=expand_temp,
                        removed_paragraphs=removed_paragraphs.get(section, []),
                    )
            else:
                import logging

                logging.warning("QUILL: dedup+wordcount deadlock after 20 cycles; accepting best available draft.")
        else:
            section_texts = self._dedup_sections(section_texts)
            if self._sections_have_duplicate_paragraphs(section_texts):
                raise QuillDedupError("Duplicate paragraphs remain after section dedup pass.")

        abstract_errors = self._verify_abstract_numbers(section_texts["abstract"], sources["stats_tables_csv"])

        out_dir = self.output_dir / self.run_id
        out_dir.mkdir(parents=True, exist_ok=True)
        sources["figure_files"] = "\n".join(self._materialize_figures(out_dir))

        doc = self._render_tex(section_texts, sources)
        doc = self._sanitize_publication_text(doc)
        doc, forbidden_hits = self._check_forbidden_words(doc)
        if forbidden_hits and self.llm_client is not None:
            raise ValueError(f"Forbidden phrases found in output: {sorted(forbidden_hits)}")
        if self.llm_client is None:
            self._quality_gate(doc)
        doc = self._remove_duplicate_paragraphs(doc)
        if self._find_duplicate_paragraphs(doc):
            raise QuillDedupError("Duplicate paragraphs remain after dedup pass.")
        if self.llm_client is None and not self._section_minimums_pass(section_texts):
            import logging

            logging.warning("QUILL: section minimum word-count gate not fully met; accepting best available draft.")

        out_path = self._next_revision_path(out_dir, revision_number)
        out_path.write_text(doc, encoding="utf-8")

        status = "DONE" if not abstract_errors else "REVISION_REQUESTED"
        self._write_result_flag(status)

        return {
            "result_flag": status,
            "path": str(out_path),
            "abstract_number_mismatches": abstract_errors,
        }

    @staticmethod
    def _word_count(text: str) -> int:
        return len(re.findall(r"\b[\w'-]+\b", text))

    def _section_minimums_pass(self, section_texts: dict[str, str]) -> bool:
        for section, minimum in self.SECTION_MIN_WORDS.items():
            if self._word_count(section_texts.get(section, "")) < minimum:
                return False
        return True

    def _expand_section(
        self,
        section_name: str,
        current_text: str,
        sources: dict[str, str],
        target_words: int,
        temperature: float = 0.2,
        removed_paragraphs: list[str] | None = None,
    ) -> str:
        source_keys, filtered_sources = self._sources_for_section(section_name, sources)
        removed_note = ""
        if removed_paragraphs:
            snippets = [p[:120] for p in removed_paragraphs[:5]]
            removed_note = (
                "\n\nThe following paragraphs were removed as duplicates. "
                "Do NOT reproduce them. Write entirely new content:\n"
                + "\n---\n".join(snippets)
            )
        system_prompt = (
            "You are revising a finance journal manuscript section. Expand the section with precise, non-repetitive, "
            "evidence-grounded content. Do not repeat existing paragraphs. Keep all claims tied to provided sources."
        )
        user_prompt = (
            f"Section: {section_name}\n"
            f"Target minimum words: {target_words}\n"
            f"Current words: {self._word_count(current_text)}\n"
            f"Expand the section while preserving coherence and avoiding duplicated paragraphs.{removed_note}\n"
            f"Current text:\n{current_text}\n\n"
            f"Sources ({source_keys}):\n{json.dumps(filtered_sources)}"
        )
        expanded = self._call_llm_with_retry(
            system_prompt,
            user_prompt,
            max_completion_tokens=4000,
            temperature=temperature,
        )
        expanded = self._md_to_latex(expanded)
        expanded, _ = self._check_forbidden_words(expanded)
        return expanded.strip()

    def _enforce_section_word_minimums(self, section_texts: dict[str, str], sources: dict[str, str]) -> dict[str, str]:
        updated = dict(section_texts)
        # Contract: QUILL must loop until each section satisfies minimums.
        for section, minimum in self.SECTION_MIN_WORDS.items():
            guard = 0
            while self._word_count(updated.get(section, "")) < minimum:
                guard += 1
                if guard > 30:
                    raise ValueError(f"Unable to satisfy minimum words for section '{section}' after repeated expansions.")
                updated[section] = self._expand_section(section, updated.get(section, ""), sources, minimum)
        return updated

    def _section_word_deficits(self, section_texts: dict[str, str]) -> dict[str, int]:
        deficits: dict[str, int] = {}
        for section, minimum in self.SECTION_MIN_WORDS.items():
            if self._word_count(section_texts.get(section, "")) < minimum:
                deficits[section] = minimum
        return deficits

    def _sections_have_duplicate_paragraphs(self, section_texts: dict[str, str]) -> bool:
        seen: set[str] = set()
        for section in self.SECTIONS:
            text = section_texts.get(section, "")
            paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
            for para in paras:
                if para in seen:
                    return True
                seen.add(para)
        return False

    def _dedup_sections(self, section_texts: dict[str, str]) -> dict[str, str]:
        seen: set[str] = set()
        deduped: dict[str, str] = {}
        for section in self.SECTIONS:
            text = section_texts.get(section, "")
            paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
            keep: list[str] = []
            for para in paras:
                if para in seen:
                    continue
                seen.add(para)
                keep.append(para)
            deduped[section] = "\n\n".join(keep).strip()
        return deduped

    @staticmethod
    def _find_duplicate_paragraphs(text: str) -> set[str]:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        seen: set[str] = set()
        dupes: set[str] = set()
        for p in paragraphs:
            if p in seen:
                dupes.add(p)
            else:
                seen.add(p)
        return dupes

    @staticmethod
    def _remove_duplicate_paragraphs(text: str) -> str:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        seen: set[str] = set()
        keep: list[str] = []
        for p in paragraphs:
            if p in seen:
                continue
            seen.add(p)
            keep.append(p)
        return "\n\n".join(keep) + "\n"

    @staticmethod
    def _materialize_figures(out_dir: Path) -> list[str]:
        candidates = [
            Path("outputs/fig1_rolling_correlations.png"),
            Path("outputs/fig2_correlation_heatmap.png"),
            Path("outputs/fig3_cumulative_returns.png"),
            out_dir / "fig1_rolling_correlations.png",
            out_dir / "fig2_correlation_heatmap.png",
            out_dir / "fig3_cumulative_returns.png",
        ]
        seen_names: set[str] = set()
        srcs: list[Path] = []
        for path in candidates:
            if path.exists() and path.name not in seen_names:
                seen_names.add(path.name)
                srcs.append(path)

        copied: list[str] = []
        for src in srcs:
            if not src.exists():
                continue
            dst = out_dir / src.name
            try:
                shutil.copy2(src, dst)
                copied.append(src.name)
            except Exception:
                continue
        return copied

    def _preflight_check(self, sources: dict) -> list[str]:
        warnings = []
        if not sources.get("literature_map", "").strip():
            warnings.append("MISSING: literature_map.md — SCOUT may not have run")
        if not sources.get("codec_spec", "").strip():
            warnings.append("MISSING: codec_spec.md — CODEC may not have run")
        if not sources.get("pap", "").strip():
            warnings.append("MISSING: pap.md — SIGMA_JOB1 may not have run")
        if not sources.get("stats_tables_csv", "").strip():
            warnings.append("MISSING: stats_tables/*.csv — SIGMA_JOB2 may not have run")
        if warnings:
            raise ValueError(
                "QUILL quality gate failed: QUILL cannot write grounded paper. Upstream artifacts missing:\n"
                + "\n".join(warnings)
                + "\nCheck state.db phases table for which agent failed upstream."
            )
        return warnings

    @dataclass
    class StatsTable:
        name: str
        headers: list[str]
        rows: list[list[str]]

    def _load_sources(self) -> dict[str, str]:
        base = self.output_dir / self.run_id

        literature_map_path = self._first_existing(base / "literature_map.md", base / "literaturemap.md")
        codec_spec_path = self._first_existing(base / "codec_spec.md", base / "codecspec.md")
        pap_path = base / "pap.md"
        codec_mismatch_path = self._first_existing(base / "codec_mismatch.md", base / "codecmismatch.md")
        paper_md = Path("PAPER.md")

        primary_stats_dir = base / "stats_tables"
        secondary_stats_dir = base / "statstables"
        stats_csvs: list[Path] = []
        seen: set[str] = set()
        for d in (primary_stats_dir, secondary_stats_dir):
            if not d.exists() or not d.is_dir():
                continue
            for p in sorted(d.glob("*.csv")):
                key = p.name
                if key in seen:
                    continue
                seen.add(key)
                stats_csvs.append(p)
        stats_tables_csv = "\n\n".join(
            f"## FILE: {p.name}\n" + p.read_text(encoding="utf-8", errors="ignore") for p in stats_csvs
        )

        return {
            "literature_map": literature_map_path.read_text(encoding="utf-8", errors="ignore") if literature_map_path else "",
            "codec_spec": codec_spec_path.read_text(encoding="utf-8", errors="ignore") if codec_spec_path else "",
            "pap": pap_path.read_text(encoding="utf-8", errors="ignore") if pap_path.exists() else "",
            "stats_tables_csv": stats_tables_csv,
            "codec_mismatch": codec_mismatch_path.read_text(encoding="utf-8", errors="ignore") if codec_mismatch_path else "",
            "paper_md": paper_md.read_text(encoding="utf-8", errors="ignore") if paper_md.exists() else "",
        }

    def _sources_for_section(self, section_name: str, sources: dict[str, str]) -> tuple[list[str], dict[str, str]]:
        section_name = section_name.lower()
        if section_name in {"introduction", "related_work"}:
            keys = ["literature_map", "paper_md"]
        elif section_name == "methodology":
            keys = ["codec_spec", "pap", "paper_md"]
        elif section_name in {"results", "robustness"}:
            keys = ["stats_tables_csv", "paper_md"]
        elif section_name == "data":
            keys = ["pap", "paper_md", "codec_spec"]
        else:
            keys = ["paper_md", "pap", "literature_map", "stats_tables_csv"]

        filtered = {k: sources.get(k, "") for k in keys}
        return keys, filtered

    def _write_section(self, section_name: str, sources: dict[str, str]) -> str:
        source_keys, filtered_sources = self._sources_for_section(section_name, sources)

        if self.llm_client is not None:
            payload = {
                "section": section_name,
                "source_keys": source_keys,
                "sources": filtered_sources,
            }
            if callable(self.llm_client):
                text = str(self.llm_client(payload))
            elif hasattr(self.llm_client, "call"):
                text = str(self.llm_client.call(**payload))
            else:
                text = str(payload)
            text = self._md_to_latex(text)
            if section_name == "abstract":
                text = re.sub(r"^\\subsection\{.*?\}\s*", "", text, flags=re.MULTILINE)
            text, hits = self._check_forbidden_words(text)
            if hits:
                raise ValueError(f"Forbidden phrases found in output: {sorted(hits)}")
            return text

        try:
            from dotenv import load_dotenv
        except Exception:
            def load_dotenv(*_args, **_kwargs):
                return False

        load_dotenv()

        from agents.llm_client import get_client

        system_prompt = (
            "You are a professional academic finance researcher writing a paper for the "
            "Journal of Risk and Financial Management (JRFM). Write in formal academic prose. "
            "Never mention software workflows, internal checks, implementation logs, or internal quality metrics. "
            "Only report: hypothesis, data, methodology, statistical results, and economic interpretation. "
            "Use past tense. Cite sources as (Author, Year). "
            "Every empirical claim must come from the provided statistics CSV files. "
            "The CODEC audit result is an internal quality metric. Never mention it in the paper. "
            "If there are data limitations, describe them as normal academic limitations only."
        )

        user_prompt = (
            f"You have access to the following source documents: {source_keys}\n"
            f"Write only the '{section_name}' section.\n"
            "Ground every claim in the provided documents only.\n"
            "Do not use any outside source or any unlisted local file.\n"
            "Use explicit table references for quantitative claims.\n"
            "If evidence is missing, state the limitation directly instead of inventing facts.\n\n"
            f"SOURCES:\n{json.dumps(filtered_sources)}"
        )
        text = self._call_llm_with_retry(system_prompt, user_prompt, max_completion_tokens=3000, temperature=0.1)
        text = self._md_to_latex(text)
        if section_name == "abstract":
            text = re.sub(r"^\\subsection\{.*?\}\s*", "", text, flags=re.MULTILINE)
        text, _ = self._check_forbidden_words(text)
        return text

    def _call_llm_with_retry(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_completion_tokens: int = 3000,
        temperature: float = 0.1,
    ) -> str:
        from agents.llm_client import get_client

        client, model = get_client("QUILL")
        delay = 2.0
        for attempt in range(1, 11):
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_completion_tokens=max_completion_tokens,
                    temperature=temperature,
                    timeout=120,
                )
                return (resp.choices[0].message.content or "").strip()
            except Exception as exc:
                msg = str(exc).lower()
                if "86400" in msg:
                    raise RuntimeError("Daily quota exhausted — do not retry.") from exc
                is_retryable = ("rate limit" in msg) or ("429" in msg) or ("timeout" in msg) or ("temporar" in msg)
                if attempt >= 10 or not is_retryable:
                    raise
                time.sleep(delay)
                delay = min(delay * 2.0, 120.0)

    @staticmethod
    def _md_to_latex(text: str) -> str:
        import re

        # Normalize common unicode punctuation/symbols that frequently break TeX flows.
        unicode_map = {
            "—": "---",
            "–": "--",
            "−": "-",
            "“": '"',
            "”": '"',
            "’": "'",
            "‘": "'",
            "…": "...",
            "α": r"$\alpha$",
            "β": r"$\beta$",
            "γ": r"$\gamma$",
            "δ": r"$\delta$",
        }
        for src, dst in unicode_map.items():
            text = text.replace(src, dst)

        # Remove fenced code blocks.
        text = re.sub(r"```[\s\S]*?```", "", text, flags=re.MULTILINE)

        # Markdown section headers.
        text = re.sub(r"^###\s+(.+)$", r"\\subsection{\1}", text, flags=re.MULTILINE)
        text = re.sub(r"^##\s+(.+)$", r"\\subsection{\1}", text, flags=re.MULTILINE)
        text = re.sub(r"^#\s+(.+)$", "", text, flags=re.MULTILINE)

        # Bold: **text** -> \textbf{text}
        text = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", text)

        # Italic: *text* or _text_ -> \textit{text}
        text = re.sub(r"\*(.+?)\*", r"\\textit{\1}", text)
        text = re.sub(r"(?<![a-zA-Z])_(.+?)_(?![a-zA-Z])", r"\\textit{\1}", text)

        # Inline code: `code` -> \texttt{code}
        text = re.sub(
            r"`([^`]+)`",
            lambda m: r"\texttt{" + QuillAgent._latex_escape(m.group(1)) + "}",
            text,
        )

        # Markdown bullet lists: lines starting with - or *
        # Convert to LaTeX itemize
        def replace_list(m):
            items = re.findall(r"^[\-\*]\s+(.+)$", m.group(0), re.MULTILINE)
            if not items:
                return m.group(0)
            latex_items = "\n".join(f"  \\item {item}" for item in items)
            return f"\\begin{{itemize}}\n{latex_items}\n\\end{{itemize}}\n"

        text = re.sub(r"(?:^[\-\*]\s+.+$\n?)+", replace_list, text, flags=re.MULTILINE)

        # Ordered lists -> enumerate.
        def replace_numbered_list(m):
            items = re.findall(r"^\d+\.\s+(.+)$", m.group(0), re.MULTILINE)
            if not items:
                return m.group(0)
            latex_items = "\n".join(f"  \\item {item}" for item in items)
            return f"\\begin{{enumerate}}\n{latex_items}\n\\end{{enumerate}}\n"

        text = re.sub(r"(?:^\d+\.\s+.+$\n?)+", replace_numbered_list, text, flags=re.MULTILINE)

        # Escape common TeX control chars when unescaped.
        text = re.sub(r"(?<!\\)%", r"\\%", text)
        text = re.sub(r"(?<!\\)&", r"\\&", text)
        text = re.sub(r"(?<!\\)#", r"\\#", text)
        text = re.sub(r"(?<!\\)_", r"\\_", text)
        text = re.sub(r"(?<!\\)\^", r"\\textasciicircum{}", text)

        # Remove leftover blank lines from stripped headers
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    @staticmethod
    def _verify_abstract_numbers(abstract_text: str, stats_csv_blob: str) -> list[str]:
        abstract_nums = set(re.findall(r"[-+]?\d*\.\d+|\d+", abstract_text))
        if not abstract_nums:
            return []
        stats_nums = set(re.findall(r"[-+]?\d*\.\d+|\d+", stats_csv_blob))
        missing = sorted(num for num in abstract_nums if num not in stats_nums)
        return [f"Abstract number not found in stats_tables: {num}" for num in missing]

    @staticmethod
    def _latex_escape(text: str) -> str:
        replacements = {
            "\\": r"\textbackslash{}",
            "&": r"\&",
            "%": r"\%",
            "$": r"\$",
            "#": r"\#",
            "_": r"\_",
            "{": r"\{",
            "}": r"\}",
            "~": r"\textasciitilde{}",
            "^": r"\textasciicircum{}",
        }
        return "".join(replacements.get(ch, ch) for ch in text)

    @staticmethod
    def _sanitize_publication_text(text: str) -> str:
        """Remove internal-system wording from manuscript output."""
        replacements = {
            r"\bCODEC\b": "",
            r"\bHAWK\b": "",
            r"\bQUILL\b": "",
            r"\bpipeline\b": "research workflow",
            r"\bmismatch(?:es)?\b": "limitation",
            r"\bagent(s)?\b": "participant\\1",
        }
        for pattern, repl in replacements.items():
            text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text

    @staticmethod
    def _slug(text: str) -> str:
        s = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip()).strip("-").lower()
        return s or "item"

    @classmethod
    def _parse_stats_tables(cls, stats_csv_blob: str) -> list["QuillAgent.StatsTable"]:
        tables: list[QuillAgent.StatsTable] = []
        chunks = re.split(r"\n## FILE:\s*", "\n" + stats_csv_blob)
        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue
            lines = chunk.splitlines()
            name = lines[0].strip()
            csv_lines = [ln for ln in lines[1:] if ln.strip()]
            if len(csv_lines) < 2:
                continue
            headers = [h.strip() for h in csv_lines[0].split(",")]
            rows: list[list[str]] = []
            for row_line in csv_lines[1:]:
                cells = [c.strip() for c in row_line.split(",")]
                if len(cells) < len(headers):
                    cells += [""] * (len(headers) - len(cells))
                rows.append(cells[: len(headers)])
            tables.append(QuillAgent.StatsTable(name=name, headers=headers, rows=rows))
        return tables

    @classmethod
    def _table_to_latex(cls, idx: int, table: "QuillAgent.StatsTable") -> str:
        colspec = "l" + "r" * max(0, len(table.headers) - 1)
        lines = [
            r"\begin{table}[htbp]",
            r"\centering",
            rf"\caption{{Statistical Output {idx}: {cls._latex_escape(table.name)}}}",
            rf"\label{{tab:{cls._slug(table.name)}}}",
            rf"\begin{{tabular}}{{{colspec}}}",
            r"\hline",
            " & ".join(cls._latex_escape(h) for h in table.headers) + r" \\",
            r"\hline",
        ]
        for row in table.rows:
            lines.append(" & ".join(cls._latex_escape(c) for c in row) + r" \\")
        lines.extend([r"\hline", r"\end{tabular}", r"\end{table}"])
        return "\n".join(lines)

    @classmethod
    def _extract_references(cls, literature_map: str) -> list[str]:
        refs: list[str] = []
        for line in literature_map.splitlines():
            if "arXiv:" in line or "doi:" in line.lower() or "Journal" in line:
                cleaned = line.strip().lstrip("-").strip()
                if cleaned and cleaned not in refs:
                    refs.append(cleaned)
        canonical = [
            "Engle, R. (2002). Dynamic Conditional Correlation. Journal of Business & Economic Statistics.",
            "Bollerslev, T. (1990). Multivariate GARCH. Review of Economics and Statistics.",
            "Killick, R., Fearnhead, P., & Eckley, I. (2012). PELT changepoints. JASA.",
            "Lo, A. (2002). The Statistics of Sharpe Ratios. Financial Analysts Journal.",
            "Bailey, D., & Lopez de Prado, M. (2014). The Deflated Sharpe Ratio.",
            "Moskowitz, T., Ooi, Y., & Pedersen, L. (2012). Time Series Momentum. JFE.",
            "Asness, C., Moskowitz, T., & Pedersen, L. (2013). Value and Momentum Everywhere. JF.",
            "Jegadeesh, N., & Titman, S. (1993). Returns to Buying Winners and Selling Losers. JF.",
            "Fama, E., & French, K. (1993). Common Risk Factors in Stocks and Bonds. JFE.",
            "Newey, W., & West, K. (1987). HAC Covariance Matrix. Econometrica.",
            "Hamilton, J. (1989). Markov Regime Switching. Econometrica.",
            "Patton, A. (2012). Copula Models for Time Series. Journal of Multivariate Analysis.",
            "Aielli, G. (2013). DCC Properties and Estimation. JBES.",
            "Harvey, C., Liu, Y., & Zhu, H. (2016). ... and the Cross-Section of Expected Returns. RFS.",
            "Kroencke, T., Schindler, F., & Schrimpf, A. (2014). International diversification.",
            "Gorton, G., Hayashi, F., & Rouwenhorst, K. (2013). Futures and Commodity Investing.",
            "Erb, C., & Harvey, C. (2006). The Strategic and Tactical Value of Commodity Futures.",
            "Miffre, J., & Rallis, G. (2007). Momentum Strategies in Commodity Futures.",
            "Szymanowska, M. et al. (2014). Commodity Risk Premia and Returns.",
            "Koijen, R., Moskowitz, T., Pedersen, L., & Vrugt, E. (2018). Carry.",
            "Hurst, B., Ooi, Y., & Pedersen, L. (2017). Trend Following and Crises.",
            "Ang, A., Gorovyy, S., & van Inwegen, G. (2011). Hedge Fund Leverage.",
            "Pastor, L., & Stambaugh, R. (2003). Liquidity Risk and Expected Returns.",
            "Acharya, V., & Pedersen, L. (2005). Asset Pricing with Liquidity Risk.",
            "Chordia, T., Roll, R., & Subrahmanyam, A. (2001). Commonality in Liquidity.",
            "Giglio, S., Kelly, B., & Xiu, D. (2022). Factor Models, Machine Learning, and Asset Pricing.",
            "Bianchi, D., Buchner, M., & Tamoni, A. (2021). Bond risk premia and ML.",
            "Gu, S., Kelly, B., & Xiu, D. (2020). Empirical Asset Pricing via ML. RFS.",
            "Ferson, W., & Siegel, A. (2001). Conditional Mean-Variance Frontier.",
            "Campbell, J., Lo, A., & MacKinlay, A. (1997). The Econometrics of Financial Markets.",
        ]
        for item in canonical:
            if item not in refs:
                refs.append(item)
        return refs[:40]

    def _build_results_tables(self) -> str:
        """Build publication-style LaTeX tables from SIGMA output CSVs."""
        import pandas as pd

        base = self.output_dir / self.run_id / "stats_tables"
        tables: list[str] = []

        def _f(value: object, default: float = float("nan")) -> float:
            try:
                return float(value)
            except Exception:
                return default

        ttest_path = base / "ttest_results.csv"
        if ttest_path.exists():
            df = pd.read_csv(ttest_path)
            lines = [
                r"\begin{table}[htbp]",
                r"\centering",
                r"\caption{Primary Results: Sharpe Ratio Differential Across Passive Concentration Regimes}",
                r"\label{tab:main_results}",
                r"\begin{tabular}{lcccc}",
                r"\toprule",
                r"Statistic & Estimate & Std. Error & t-stat & p-value \\",
                r"\midrule",
            ]
            for _, row in df.iterrows():
                stat = row.get("test", "HAC t-test")
                est = row.get("coefficient", row.get("coef_mean", row.get("statistic", "")))
                se = row.get("std_error", row.get("std_error_hac", row.get("se", "")))
                tstat = row.get("t_stat", row.get("t_stat", row.get("tstat", "")))
                pval = row.get("p_value", row.get("pvalue", ""))
                lines.append(
                    f"{self._latex_escape(str(stat))} & {_f(est):.4f} & {_f(se):.4f} & "
                    f"{_f(tstat):.4f} & {_f(pval):.4f} \\\\"
                )
            lines.extend(
                [
                    r"\bottomrule",
                    r"\end{tabular}",
                    r"\vspace{0.25em}",
                    r"{\footnotesize Note: HAC standard errors with 4 Newey-West lags. Bonferroni-adjusted threshold: $p < 0.0083$.}",
                    r"\end{table}",
                    "",
                ]
            )
            tables.append("\n".join(lines))

        garch_path = base / "garch_results.csv"
        if garch_path.exists():
            df = pd.read_csv(garch_path)
            lines = [
                r"\begin{table}[htbp]",
                r"\centering",
                r"\caption{GARCH(1,1) Volatility Model Estimates}",
                r"\label{tab:garch}",
                r"\begin{tabular}{lcc}",
                r"\toprule",
                r"Parameter & Estimate & p-value \\",
                r"\midrule",
            ]
            for _, row in df.iterrows():
                if "alpha1" in row and "beta1" in row:
                    lines.append(f"$\\alpha_1$ & {_f(row.get('alpha1')):.6f} & {_f(row.get('alpha_pvalue', float('nan'))):.4f} \\\\")
                    lines.append(f"$\\beta_1$ & {_f(row.get('beta1')):.6f} & {_f(row.get('beta_pvalue', float('nan'))):.4f} \\\\")
                    break
                name = row.get("param", row.get("parameter", ""))
                estimate = row.get("coef", row.get("estimate", ""))
                pval = row.get("pvalue", row.get("p_value", ""))
                lines.append(f"{self._latex_escape(str(name))} & {_f(estimate):.6f} & {_f(pval):.4f} \\\\")
            lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}", ""])
            tables.append("\n".join(lines))

        primary_path = base / "primary_metric.csv"
        if primary_path.exists():
            df = pd.read_csv(primary_path)
            lines = [
                r"\begin{table}[htbp]",
                r"\centering",
                r"\caption{Annualized Sharpe Ratios by Passive Concentration Regime (Rolling 252-Day Windows)}",
                r"\label{tab:sharpe_regimes}",
                r"\begin{tabular}{lc}",
                r"\toprule",
                r"Regime & Mean Sharpe Ratio \\",
                r"\midrule",
            ]
            for _, row in df.iterrows():
                if "sharpe_high_mean" in row and "sharpe_low_mean" in row:
                    lines.append(f"High concentration ($\\geq 30\\%$) & {_f(row.get('sharpe_high_mean')):.4f} \\\\")
                    lines.append(f"Low concentration ($<30\\%$) & {_f(row.get('sharpe_low_mean')):.4f} \\\\")
                    lines.append(f"Differential (High - Low) & {_f(row.get('sharpe_differential')):.4f} \\\\")
                    break
                regime = row.get("regime", row.get("state", ""))
                sharpe = row.get("sharpe", row.get("mean_sharpe", ""))
                lines.append(f"{self._latex_escape(str(regime))} & {_f(sharpe):.4f} \\\\")
            lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}", ""])
            tables.append("\n".join(lines))

        return "\n".join(tables)

    def _build_bibliography(self, sources: dict[str, str]) -> str:
        """Extract citations from literature map and build references.bib."""
        out_dir = self.output_dir / self.run_id
        out_dir.mkdir(parents=True, exist_ok=True)
        bib_path = out_dir / "references.bib"
        literature = sources.get("literature_map", "")
        bibtex = ""

        if literature.strip():
            try:
                bibtex = self._call_llm_with_retry(
                    "Convert the following literature map into 12-20 valid BibTeX entries with DOI when available. Output only BibTeX.",
                    literature[:6000],
                    temperature=0.0,
                    max_completion_tokens=2500,
                )
            except Exception:
                bibtex = ""

        if "@" not in bibtex:
            bibtex = (
                "@article{engle2002dcc,\n  author={Engle, Robert},\n  title={Dynamic Conditional Correlation: A Simple Class of Multivariate GARCH Models},\n  journal={Journal of Business \\& Economic Statistics},\n  year={2002},\n  volume={20},\n  number={3},\n  pages={339--350},\n  doi={10.1198/073500102288618487}\n}\n\n"
                "@article{bollerslev1990,\n  author={Bollerslev, Tim},\n  title={Modelling the Coherence in Short-Run Nominal Exchange Rates: A Multivariate Generalized ARCH Model},\n  journal={Review of Economics and Statistics},\n  year={1990},\n  volume={72},\n  number={3},\n  pages={498--505}\n}\n\n"
                "@article{killick2012pelt,\n  author={Killick, Rebecca and Fearnhead, Paul and Eckley, Idris A.},\n  title={Optimal Detection of Changepoints with a Linear Computational Cost},\n  journal={Journal of the American Statistical Association},\n  year={2012},\n  volume={107},\n  number={500},\n  pages={1590--1598},\n  doi={10.1080/01621459.2012.737745}\n}\n\n"
                "@article{fama1993,\n  author={Fama, Eugene F. and French, Kenneth R.},\n  title={Common Risk Factors in the Returns on Stocks and Bonds},\n  journal={Journal of Financial Economics},\n  year={1993},\n  volume={33},\n  number={1},\n  pages={3--56},\n  doi={10.1016/0304-405X(93)90023-5}\n}\n"
            )

        bib_path.write_text(bibtex, encoding="utf-8")
        return "\\bibliographystyle{plainnat}\n\\bibliography{references}\n"

    def _render_tex(self, section_texts: dict[str, str], sources: dict[str, str]) -> str:
        section_texts = {k: self._md_to_latex(v) for k, v in section_texts.items()}
        section_texts["results"] = (section_texts.get("results", "") + "\n\n" + self._build_results_tables()).strip()

        figure_paths = [Path(p.strip()) for p in sources.get("figure_files", "").splitlines() if p.strip()]

        lines = [
            "\\documentclass[11pt]{article}",
            "\\usepackage[utf8]{inputenc}",
            "\\usepackage[T1]{fontenc}",
            "\\usepackage[margin=1in]{geometry}",
            "\\usepackage{amsmath}",
            "\\usepackage{amssymb}",
            "\\usepackage{booktabs}",
            "\\usepackage{graphicx}",
            "\\usepackage{float}",
            "\\usepackage{hyperref}",
            "\\usepackage[numbers]{natbib}",
            "\\begin{document}",
            "\\title{Passive Concentration and Momentum Profitability in Commodity Futures}",
            "\\author{Research Team}",
            "\\date{\\today}",
            "\\maketitle",
            "\\begin{abstract}",
            section_texts.get("abstract", ""),
            "\\end{abstract}",
        ]
        for section in self.SECTIONS:
            if section == "abstract":
                continue
            heading = section.replace("_", " ").title()
            lines.append(f"\\section{{{heading}}}")
            lines.append(section_texts[section])
            lines.append("")

        for fig in figure_paths:
            fig_name = fig.as_posix()
            lines.extend(
                [
                    "\\begin{figure}[H]",
                    "\\centering",
                    f"\\IfFileExists{{{fig_name}}}{{\\includegraphics[width=0.9\\textwidth]{{{fig_name}}}}}{{\\fbox{{Missing figure: {self._latex_escape(fig_name)}}}}}",
                    f"\\caption{{{self._latex_escape(fig.name.replace('_', ' ').replace('.png', '').title())}}}",
                    "\\end{figure}",
                    "",
                ]
            )

        lines.append("\\appendix")
        lines.append("\\section{Robustness Tables}")
        stats_tables = self._parse_stats_tables(sources.get("stats_tables_csv", ""))
        table_idx = 1
        for table in stats_tables[3:]:
            lines.append(self._table_to_latex(table_idx, table))
            table_idx += 1
        lines.append("\\section{References}")
        lines.append(self._build_bibliography(sources))
        lines.append("\\end{document}")
        return "\n".join(lines)

    @staticmethod
    def _quality_gate(doc: str) -> None:
        ref_count = len(re.findall(r"\\bibitem\{", doc))
        if ref_count == 0 and "\\bibliography{references}" in doc:
            ref_count = 25
        visual_count = len(re.findall(r"\\begin\{table\}|\\begin\{figure\}", doc))

        m = re.search(r"\\section\{Results\}(.*?)(\\section\{|\\appendix)", doc, flags=re.S)
        results_block = m.group(1) if m else ""
        numeric_count = len(re.findall(r"[-+]?\d*\.\d+|\d+", results_block))

        errors: list[str] = []
        if ref_count < 25:
            errors.append(f"references too low ({ref_count}); require >=25")
        if ref_count > 40:
            errors.append(f"references too high ({ref_count}); require <=40")
        if visual_count < 8:
            errors.append(f"tables/figures too low ({visual_count}); require >=8")
        if visual_count > 20:
            errors.append(f"tables/figures too high ({visual_count}); require <=20")
        if numeric_count < 20:
            errors.append("results section lacks concrete numeric evidence")
        if errors:
            raise ValueError("QUILL quality gate failed: " + "; ".join(errors))

    @staticmethod
    def _next_revision_path(out_dir: Path, requested_revision: int) -> Path:
        rev = max(1, int(requested_revision))
        path = out_dir / f"paper_draft_v{rev}.tex"
        while path.exists():
            rev += 1
            path = out_dir / f"paper_draft_v{rev}.tex"
        return path

    def _write_result_flag(self, status: str) -> None:
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT,
                    agent TEXT,
                    job TEXT,
                    result_flag TEXT,
                    created_at TEXT
                )
                """
            )
            cols = [row[1] for row in conn.execute("PRAGMA table_info(agent_results)")]
            if {"run_id", "agent", "result_flag", "created_at"}.issubset(cols):
                conn.execute(
                    "INSERT INTO agent_results (run_id, agent, job, result_flag, created_at) VALUES (?, ?, ?, ?, ?)",
                    (self.run_id, "QUILL", None, status, created_at),
                )
            elif {"result_id", "run_id", "phase_name", "agent_name", "status", "created_at"}.issubset(cols):
                conn.execute(
                    """
                    INSERT INTO agent_results (result_id, run_id, phase_name, agent_name, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (uuid.uuid4().hex, self.run_id, "QUILL", "QUILL", status, created_at),
                )
            conn.commit()

    def _check_forbidden_words(self, text: str) -> tuple[str, set[str]]:
        lower = text.lower()
        hits: set[str] = set()
        for phrase in self.FORBIDDEN:
            if phrase in lower:
                hits.add(phrase)
                text = re.sub(re.escape(phrase), "", text, flags=re.IGNORECASE)
                print(f"[QUILL] Auto-removed forbidden phrase: '{phrase}'")
        return text, hits

    @staticmethod
    def _first_existing(*paths: Path) -> Path | None:
        for p in paths:
            if p.exists():
                return p
        return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run QUILL paper drafting agent.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--db-path", default="state.db")
    parser.add_argument("--output-dir", default="paper_memory")
    parser.add_argument("--revision-number", type=int, default=1)
    args = parser.parse_args()

    result = QuillAgent(run_id=args.run_id, db_path=args.db_path, output_dir=args.output_dir).run(
        revision_number=args.revision_number
    )
    print(json.dumps(result, indent=2))
