# TODO(candidate): add tests for TicketTriageAgent here.

from app.agent import TicketTriageAgent
from app.models import TicketTriageOutput
from core.generic_executor import GenericAgentExecutor
from core.models import (
    ArtifactUpdateYield,
    StreamAgentRequest,
    TaskState,
    TaskStatusUpdateYield,
)


def test_agent_is_importable():
    assert TicketTriageAgent.A2A_NAME == "Ticket Triage Agent"


def _article(article_id: int) -> dict:
    return {"id": article_id, "title": "t", "body": "b", "product_area": "p"}


def _request(query: str = "customer reports 429 errors") -> StreamAgentRequest:
    return StreamAgentRequest(query=query, context_id="ctx-1")


async def test_stream_yields_status_updates_then_terminal_artifact():
    async def fake_llm(query, articles):
        return TicketTriageOutput(
            category="api",
            priority="high",
            summary="rate limited",
            cited_article_ids=[1, 2],
        )

    async def fake_kb(query):
        return [_article(1), _article(2)]

    agent = TicketTriageAgent(llm=fake_llm, kb_search=fake_kb)
    result = await GenericAgentExecutor(agent).execute(_request())

    assert result.status == TaskState.completed
    assert result.error is None

    status_events = [e for e in result.events if isinstance(e, TaskStatusUpdateYield)]
    assert len(status_events) == 2

    artifact = result.final_artifact
    assert isinstance(artifact, ArtifactUpdateYield)
    assert artifact.state == TaskState.completed
    assert artifact.last_chunk is True
    assert artifact.content[0].data == {
        "category": "api",
        "priority": "high",
        "summary": "rate limited",
        "cited_article_ids": [1, 2],
    }


async def test_cited_article_ids_are_filtered_to_retrieved():
    async def fake_llm(query, articles):
        return TicketTriageOutput(
            category="api",
            priority="low",
            summary="x",
            cited_article_ids=[1, 999],
        )

    async def fake_kb(query):
        return [_article(1)]

    agent = TicketTriageAgent(llm=fake_llm, kb_search=fake_kb)
    result = await GenericAgentExecutor(agent).execute(_request())

    assert result.final_artifact.content[0].data["cited_article_ids"] == [1]


async def test_llm_exception_propagates_and_fails_task():
    async def fake_llm(query, articles):
        raise RuntimeError("llm down")

    async def fake_kb(query):
        return []

    agent = TicketTriageAgent(llm=fake_llm, kb_search=fake_kb)
    result = await GenericAgentExecutor(agent).execute(_request())

    assert result.status == TaskState.failed
    assert isinstance(result.error, RuntimeError)


async def test_kb_exception_propagates_and_fails_task():
    async def fake_kb(query):
        raise RuntimeError("kb down")

    agent = TicketTriageAgent(kb_search=fake_kb)
    result = await GenericAgentExecutor(agent).execute(_request())

    assert result.status == TaskState.failed
    assert isinstance(result.error, RuntimeError)
