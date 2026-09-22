"""
TicketTriageAgent - triages a support ticket against the knowledge base.
"""

from collections.abc import Awaitable, Callable

from core.base_agent import BaseAgent
from core.models import (
    ArtifactUpdateYield,
    DataContent,
    StreamAgentRequest,
    TaskState,
    TaskStatusUpdateYield,
    TextContent,
)

from . import clients
from .models import TicketTriageOutput


class TicketTriageAgent(BaseAgent):
    A2A_NAME = "Ticket Triage Agent"
    A2A_DESCRIPTION = "Triages incoming support tickets against the knowledge base"

    def __init__(
        self,
        llm: Callable[[str, list[dict]], Awaitable[TicketTriageOutput]] | None = None,
        kb_search: Callable[[str], Awaitable[list[dict]]] | None = None,
    ):
        super().__init__()
        self._llm = llm or clients.triage_with_llm
        self._kb_search = kb_search or clients.search_kb

    async def _stream(self, request: StreamAgentRequest):
        yield TaskStatusUpdateYield(
            state=TaskState.working,
            content=[TextContent(text="Searching knowledge base…")],
        )
        articles = await self._kb_search(request.query)

        yield TaskStatusUpdateYield(
            state=TaskState.working,
            content=[TextContent(text="Triaging ticket…")],
        )

        output = await self._llm(request.query, articles)

        # If no articles were found, update the output to indicate this and yield it as an artifact.
        if not articles:
            data = output.model_dump(mode="json")
            data["summary"] = "No relevant articles found."

            yield ArtifactUpdateYield(
                state=TaskState.completed,
                last_chunk=True,
                name="ticket-triage",
                content=[DataContent(data=data)],
            )
            return

        valid_ids = {
            article["id"]
            for article in articles
            if isinstance(article, dict) and isinstance(article.get("id"), int)
        }
        output.cited_article_ids = [
            cited_id for cited_id in output.cited_article_ids if cited_id in valid_ids
        ]

        yield ArtifactUpdateYield(
            state=TaskState.completed,
            last_chunk=True,
            name="ticket-triage",
            content=[DataContent(data=output.model_dump(mode="json"))],
        )
