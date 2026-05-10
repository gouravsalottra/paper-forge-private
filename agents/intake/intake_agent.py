from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import json

from .auth_manager import authenticate_wrds
from .protocol_writer import IntakeSession, ProtocolWriter
from .recommendation_engine import RecommendationEngine


class IntakeAgent:
    def __init__(self, output_path: str | Path = "PROTOCOL.md", no_llm: bool = False) -> None:
        self.output_path = Path(output_path)
        self.no_llm = no_llm
        self.reco = RecommendationEngine()

    def run(self, resume_session: str | None = None) -> None:
        _ = resume_session
        print("Welcome to Paper-Forge. Tell me about your research idea.")
        lines = []
        while True:
            line = input("")
            if line.strip() == "END":
                break
            lines.append(line)
        idea = "\n".join(lines).strip()

        claim_type = input("Claim type? ").strip() or "predictability"
        sample_period = input("Time period? ").strip() or "2000-2024"
        source = input("Data source? ").strip() or "yfinance"

        if source.startswith("wrds"):
            ready = input("Type 'ready' to auth WRDS or 'skip': ").strip().lower()
            if ready == "ready":
                authenticate_wrds()
            else:
                source = "yfinance"

        rec = self.reco.recommend_tests(claim_type)
        _ = input("Press Enter to accept test recommendations or edit manually: ")

        mode = "confirmatory"
        hypothesis = f"{idea}"
        primary_metric = "Sharpe ratio differential"
        minimum_effect_size = "-0.15 Sharpe units"
        significance_threshold = "p < 0.05; Bonferroni p < 0.0083"

        stage5 = input("Type 'commit' to lock hypothesis or 'exploratory' to switch mode: ").strip().lower()
        if stage5 == "exploratory":
            mode = "exploratory"
            hypothesis = ""
            primary_metric = ""
            minimum_effect_size = ""
            significance_threshold = ""

        session = IntakeSession(
            research_question=idea,
            research_mode=mode,
            claim_type=claim_type,
            hypothesis=hypothesis,
            primary_metric=primary_metric,
            minimum_effect_size=minimum_effect_size,
            significance_threshold=significance_threshold,
            data_source=source,
            sample_period=sample_period,
            statistical_tests=rec,
        )

        ProtocolWriter().write(session, self.output_path)
        self._save_session(session)

    def _save_session(self, session: IntakeSession) -> None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        p = self.output_path.parent / f"intake_session_{stamp}.json"
        p.write_text(json.dumps(asdict(session), indent=2), encoding="utf-8")

    def upgrade_to_confirmatory(self, run_id: str) -> None:
        run_dir = Path("runs") / run_id
        if not run_dir.exists():
            raise FileNotFoundError(f"Exploratory run not found: {run_id}")
        raise ValueError("Upgrade flow not yet implemented for this run.")
