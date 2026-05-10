# Re-export shim — allows both import paths:
# from agents.specaudit_pass2 import *
# from agents.codeaudit.specaudit_pass2 import *
# Do not add logic here — canonical implementation is in agents/codeaudit/
from agents.codeaudit.specaudit_pass2 import *  # noqa: F401,F403
