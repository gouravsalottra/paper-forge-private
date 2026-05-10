#!/usr/bin/env python3
"""INTAKE: Paper-Forge research design wizard."""

from __future__ import annotations

from agents.intake.intake_agent import IntakeAgent


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", help="Resume an interrupted intake session")
    parser.add_argument("--output", default="PROTOCOL.md", help="Output path for generated PROTOCOL.md")
    parser.add_argument("--no-llm", action="store_true", help="Use simple prompting without LLM (for testing)")
    args = parser.parse_args()

    agent = IntakeAgent(output_path=args.output, no_llm=args.no_llm)
    agent.run(resume_session=args.resume)


if __name__ == "__main__":
    main()
