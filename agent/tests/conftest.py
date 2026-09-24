"""Ensure `import app` resolves to the agent package, not mcp_server/app.

In the shared workspace venv both `agent/` and `mcp_server/` install a
top-level package literally named `app`. Prepend the `agent/` directory to
sys.path so test imports (e.g. `from app.agent import TicketTriageAgent`)
target this workspace member.
"""

import sys
from pathlib import Path

_AGENT_DIR = Path(__file__).resolve().parents[1]
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))
