# Re-export shim — allows both import paths:
# from agents.scout import LiteratureAgent
# from agents.scout.scout import LiteratureAgent
# Do not add logic here — all implementation is in agents/scout/
from agents.scout.scout import LiteratureAgent  # noqa: F401
