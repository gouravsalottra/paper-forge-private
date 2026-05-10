# Re-export shim — allows both import paths:
# from agents.hawk import ReviewerAgent
# from agents.hawk.hawk import ReviewerAgent
# Do not add logic here — all implementation is in agents/hawk/
from agents.hawk.hawk import ReviewerAgent  # noqa: F401
