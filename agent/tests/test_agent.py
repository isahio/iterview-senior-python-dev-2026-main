# TODO(candidate): add tests for TicketTriageAgent here.

from app.agent import TicketTriageAgent


def test_agent_is_importable():
    assert TicketTriageAgent.A2A_NAME == "Ticket Triage Agent"
