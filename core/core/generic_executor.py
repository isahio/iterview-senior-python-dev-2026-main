"""
GenericAgentExecutor - narrowed for the interview scaffolding.

In production this bridges BaseAgent yields to the real A2A protocol. 
We don't need the full A2A server for this exercise -- this version 
just drives an agent's `stream_request()` and allow to inspect the yields 
and final artifact.
"""

import logging
from dataclasses import dataclass, field

from .base_agent import BaseAgent
from .models import (
    ArtifactUpdateYield,
    BaseAgentYield,
    StreamAgentRequest,
    TaskState,
    TaskStatusUpdateYield,
)

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    status: TaskState 
    events: list[BaseAgentYield] = field(default_factory=list)
    error: Exception | None = None

    @property
    def final_artifact(self) -> ArtifactUpdateYield | None:
        for item in reversed(self.events):
            if isinstance(item, ArtifactUpdateYield):
                return item
        return None


class GenericAgentExecutor:
    def __init__(self, agent: BaseAgent):
        self.agent = agent

    async def execute(self, request: StreamAgentRequest) -> ExecutionResult:
        events: list[BaseAgentYield] = []
        try:
            async for item in self.agent.stream_request(request):
                events.append(item)
                if isinstance(item, TaskStatusUpdateYield):
                    logger.info("status: %s", item.content)
                if item.is_terminal:
                    break
            return ExecutionResult(status=TaskState.completed, events=events)
        except Exception as e:
            logger.error(
                "Agent %s failed: %s", self.agent.__class__.__name__, e, exc_info=True
            )
            return ExecutionResult(status=TaskState.failed, events=events, error=e)
