class PaperForgeError(Exception):
    """Base error for control-plane violations."""


class PhaseTransitionError(PaperForgeError):
    """Illegal or mismatched phase transition."""


class PapGateError(PaperForgeError):
    """Operation blocked until PAP is committed and sealed."""


class LaneViolationError(PaperForgeError):
    """Agent attempted to write outside its lane."""

