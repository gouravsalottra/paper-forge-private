"""Typed exceptions for ARIA pipeline orchestration."""

from __future__ import annotations


class ForgeGateError(RuntimeError):
    """Raised when FORGE gate preconditions fail."""


class ServerUnavailableError(RuntimeError):
    """Raised when a required server is unavailable."""

    def __init__(self, server_name: str, detail: str, latency_ms: float | None = None) -> None:
        self.server_name = server_name
        self.detail = detail
        self.latency_ms = latency_ms
        super().__init__(f"Server '{server_name}' unavailable: {detail} (latency_ms={latency_ms})")


class IntegrityViolationError(RuntimeError):
    """Raised when agent routing or artifact constraints are violated."""

    def __init__(self, artifact_name: str, agent_name: str) -> None:
        self.artifact_name = artifact_name
        self.agent_name = agent_name
        super().__init__(f"Integrity violation: {agent_name} accessed blocked artifact '{artifact_name}'")


class PipelineHaltError(RuntimeError):
    """Raised when the pipeline must halt without recovery."""


class PAPTamperError(RuntimeError):
    """Raised when PAPER.md hash no longer matches the locked PAP hash on resume."""


class TokenBudgetExceededError(RuntimeError):
    """Raised when a run exceeds its hard token budget limit."""

    def __init__(self, spent: float, limit: float) -> None:
        self.spent = spent
        self.limit = limit
        super().__init__(
            f"Token budget exceeded: ${spent:.4f} spent, "
            f"${limit:.2f} hard limit. Pipeline halted to prevent "
            f"runaway costs. Set a higher hard_limit_usd in token_limits "
            f"table if this was intentional."
        )


class StructuredOutputError(RuntimeError):
    """Raised when an LLM response cannot be parsed into required structured schema."""

    def __init__(self, source: str, raw_response: str) -> None:
        self.source = source
        self.raw_response = raw_response
        preview = (raw_response or "")[:500]
        super().__init__(f"{source} structured output parse failed. Raw response preview:\n{preview}")
