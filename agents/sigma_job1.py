"""SIGMA Job 1: write and commit a Pre-Analysis Plan (PAP)."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI


class SigmaJob1:
    def __init__(self, run_id: str, db_path: str = "state.db") -> None:
        self.run_id = run_id
        self.db_path = db_path
        self.client = OpenAI()

    def run(self) -> dict:
        _skills_candidates = [
            Path("agents/sigma/skills.md"),
            Path("skills/sigma_job1_skills.md"),
            Path("agents/sigma_job1_skills.md"),
        ]
        _skills_path = next((p for p in _skills_candidates if p.exists()), None)
        if _skills_path is None:
            skills_text = "# SIGMA Job 1\nWrite a formal Pre-Analysis Plan as strict JSON."
        else:
            skills_text = _skills_path.read_text(encoding="utf-8")

        paper_sections = self._parse_paper(Path("PAPER.md"))
        hypothesis = self._require_section(paper_sections, "Hypothesis")
        primary_metric = self._require_section(paper_sections, "Primary Metric")
        statistical_tests = self._require_section(paper_sections, "Statistical Tests")
        significance_threshold = self._require_section(paper_sections, "Significance Threshold")
        minimum_effect = self._require_section(paper_sections, "Minimum Effect Size")
        exclusions = self._require_section(paper_sections, "Exclusion Rules")
        seed_policy = self._require_section(paper_sections, "Seed Policy")

        system_prompt = (
            "You are SIGMA Job 1. Produce a formal Pre-Analysis Plan as strict JSON only. "
            "Use the exact values provided. Do not add extra keys."
        )
        user_prompt = (
            "Write the PAP as a JSON object with EXACT keys:\n"
            "claim_text\n"
            "primary_metric\n"
            "estimator\n"
            "significance_rule\n"
            "minimum_effect\n"
            "exclusions\n"
            "seeds\n\n"
            "Requirements:\n"
            "- claim_text must be the full hypothesis as a falsifiable statement.\n"
            "- primary_metric must be the exact metric definition.\n"
            "- estimator must include exact statistical methods, library names, and parameters.\n"
            "- significance_rule must include exact p-value threshold and correction method.\n"
            "- minimum_effect must be the minimum effect size in Sharpe units.\n"
            "- exclusions must capture the data exclusion rules.\n"
            "- seeds must be a JSON array of three integers.\n\n"
            f"Reference Skill Rules:\n{skills_text}\n\n"
            f"Hypothesis:\n{hypothesis}\n\n"
            f"Primary Metric:\n{primary_metric}\n\n"
            f"Statistical Tests:\n{statistical_tests}\n\n"
            f"Significance Threshold:\n{significance_threshold}\n\n"
            f"Minimum Effect Size:\n{minimum_effect}\n\n"
            f"Exclusion Rules:\n{exclusions}\n\n"
            f"Seed Policy:\n{seed_policy}\n"
        )

        try:
            completion = self.client.chat.completions.create(
                model="gpt-5.4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )
            pap_json_str = completion.choices[0].message.content or "{}"
            pap_obj = json.loads(pap_json_str)
        except Exception:
            seeds = [int(x) for x in re.findall(r"-?\d+", seed_policy)[:3]]
            if len(seeds) < 3:
                seeds = [1337, 42, 9999]
            pap_obj = {
                "claim_text": hypothesis,
                "primary_metric": primary_metric,
                "estimator": statistical_tests,
                "significance_rule": significance_threshold,
                "minimum_effect": minimum_effect,
                "exclusions": exclusions,
                "seeds": seeds,
            }

        canonical_json = json.dumps(pap_obj, sort_keys=True, separators=(",", ":"))
        pap_sha256 = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")

        pap_id = uuid.uuid4().hex
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO pap (
                    pap_id,
                    run_id,
                    status,
                    created_at,
                    updated_at,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (pap_id, self.run_id, "COMMITTED", now, now, canonical_json),
            )

            conn.execute(
                """
                INSERT INTO pap_lock (run_id, locked_at, locked_by, pap_sha256, forge_started_at)
                VALUES (?, ?, ?, ?, NULL)
                ON CONFLICT(run_id) DO UPDATE SET
                    locked_at = excluded.locked_at,
                    locked_by = excluded.locked_by,
                    pap_sha256 = excluded.pap_sha256,
                    forge_started_at = NULL
                """,
                (self.run_id, now, "SIGMA_JOB1", pap_sha256),
            )
            conn.commit()

        print(f"🔒 PAP committed. SHA-256: {pap_sha256[:16]}...")
        return pap_obj

    @staticmethod
    def _parse_paper(path: Path) -> dict[str, str]:
        text = path.read_text(encoding="utf-8")
        sections: dict[str, list[str]] = {}
        current: str | None = None

        for line in text.splitlines():
            if line.startswith("## "):
                current = line[3:].strip()
                sections[current] = []
            elif current is not None:
                sections[current].append(line)

        return {k: "\n".join(v).strip() for k, v in sections.items()}

    @staticmethod
    def _require_section(sections: dict[str, str], name: str) -> str:
        value = sections.get(name, "").strip()
        if not value:
            raise ValueError(f"Missing required PAPER.md section: {name}")
        return value
