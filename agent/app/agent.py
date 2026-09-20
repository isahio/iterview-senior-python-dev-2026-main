"""
TODO(candidate): implement TicketTriageAgent here.
"""

from core.base_agent import BaseAgent
from core.models import StreamAgentRequest


class TicketTriageAgent(BaseAgent):
    A2A_NAME = "Ticket Triage Agent"
    A2A_DESCRIPTION = "Triages incoming support tickets against the knowledge base"

    def __init__(self):
        raise NotImplementedError("TODO(candidate)")

    async def _stream(self, request: StreamAgentRequest):
        raise NotImplementedError("TODO(candidate)")
        yield  # pragma: no cover
