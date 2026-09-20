"""Tests for core executor and base-agent contract."""

import pytest

from core.base_agent import BaseAgent
from core.generic_executor import GenericAgentExecutor
from core.models import ArtifactUpdateYield, StreamAgentRequest, TaskState, TextContent


class _EchoAgent(BaseAgent):
    A2A_NAME = "Echo"

    async def _stream(self, request: StreamAgentRequest):
        yield ArtifactUpdateYield(
            state=TaskState.completed,
            content=[TextContent(text=request.query)],
            last_chunk=True,
        )


class _ChattyAgent(BaseAgent):
    """Misbehaves on purpose: keeps yielding after its terminal artifact."""

    A2A_NAME = "Chatty"

    async def _stream(self, request: StreamAgentRequest):
        yield ArtifactUpdateYield(
            state=TaskState.completed,
            content=[TextContent(text="done")],
            last_chunk=True,
        )
        yield ArtifactUpdateYield(
            state=TaskState.completed,
            content=[TextContent(text="oops, still going")],
            last_chunk=True,
        )


class _BoomAgent(BaseAgent):
    A2A_NAME = "Boom"

    async def _stream(self, request: StreamAgentRequest):
        raise ValueError("boom")
        yield  # pragma: no cover


@pytest.mark.asyncio
async def test_executor_completes_on_terminal_artifact():
    executor = GenericAgentExecutor(_EchoAgent())
    result = await executor.execute(StreamAgentRequest(query="hello", context_id="ctx-1"))
    assert result.status == TaskState.completed
    assert result.final_artifact.content[0].text == "hello"


@pytest.mark.asyncio
async def test_executor_stops_at_first_terminal_yield():
    executor = GenericAgentExecutor(_ChattyAgent())
    result = await executor.execute(StreamAgentRequest(query="hello", context_id="ctx-1"))
    assert len(result.events) == 1, (
        "executor should stop consuming the agent's generator at the first "
        f"terminal yield, not drain it -- got {len(result.events)} events"
    )
    assert result.final_artifact.content[0].text == "done"


@pytest.mark.asyncio
async def test_executor_fails_on_exception_instead_of_swallowing_it():
    executor = GenericAgentExecutor(_BoomAgent())
    result = await executor.execute(StreamAgentRequest(query="hello", context_id="ctx-1"))
    assert result.status == TaskState.failed
    assert isinstance(result.error, ValueError)
