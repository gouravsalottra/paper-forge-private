# Re-export shim — allows both import paths:
# from agents.quill import WriterAgent
# from agents.quill.quill import WriterAgent
# Do not add logic here — all implementation is in agents/quill/
from agents.quill.quill import WriterAgent  # noqa: F401
