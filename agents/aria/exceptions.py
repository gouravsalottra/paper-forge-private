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
