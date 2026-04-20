from aria.aria import ARIA


def main() -> None:
    aria = ARIA("state.db")
    run_id = aria.start_run("PAPER.md")
    next_phase = aria.advance()
    print(next_phase)


if __name__ == "__main__":
    main()
