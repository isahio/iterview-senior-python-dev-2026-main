"""
BaseAgent - narrowed for the interview scaffolding.

This is a trimmed copy of shared/core/base_agent.py, keeping only the
streaming interface used by current agents in this codebase. Multi-skill
routing attributes, the legacy stream() interface, and logfire plumbing that
aren't needed for this exercise have been removed.
"""

import json
import uuid
from abc import ABC
from collections.abc import AsyncGenerator
from typing import Any

from .models import BaseAgentYield, StreamAgentRequest


class BaseAgent(ABC):
    """
    Base class every agent in this codebase implements.

    Subclasses implement `_stream()`, which receives a StreamAgentRequest and
    yields BaseAgentYield objects (see models.py). `stream_request()` wraps
    `_stream()` with error handling: if `_stream()` raises, `on_fail()` is
    called (an optional hook for cleanup/error-artifact yields), and then the
    exception is RE-RAISED so the executor can mark the task failed.

    IMPORTANT: do not catch exceptions inside `_stream()` yourself and turn
    them into a "successful" yield -- let them propagate. Errors are task
    *state changes* (failed), not deliverable content. See
    GenericAgentExecutor for how failures are turned into an error artifact
    + failed status on your behalf.
    """

    A2A_NAME: str = "Unnamed Agent"
    A2A_DESCRIPTION: str = ""
    A2A_SKILLS: list = []

    def _build_model_settings_with_trace(
        self,
        trace_context: dict[str, str] | None,
        operation_name: str,
    ) -> dict[str, Any] | None:
        """Build model_settings with Portkey trace headers, if a trace_context was provided."""
        if not trace_context:
            return None
        span_id = str(uuid.uuid4())
        extra_headers = {
            "x-portkey-trace-id": trace_context.get("trace_id", "a2a-agents"),
            "x-portkey-span-id": span_id,
            "x-portkey-span-name": operation_name,
        }
        if parent_span_id := trace_context.get("parent_span_id"):
            extra_headers["x-portkey-parent-span-id"] = parent_span_id
        extra_headers["x-portkey-metadata"] = json.dumps(
            {"agent": self.__class__.__name__}
        )
        return {"extra_headers": extra_headers}

    async def stream_request(
        self, request: StreamAgentRequest
    ) -> AsyncGenerator[BaseAgentYield, None]:
        try:
            async for item in self._stream(request):
                yield item
        except Exception as e:
            async for item in self.on_fail(request=request, exception=e):
                yield item
            raise

    async def on_fail(
        self, request: StreamAgentRequest, exception: Exception
    ) -> AsyncGenerator[BaseAgentYield, None]:
        """Optional hook to yield cleanup/error-artifact items before the exception re-raises. No-op by default."""
        return
        yield  # pragma: no cover

    async def _stream(
        self, request: StreamAgentRequest
    ) -> AsyncGenerator[BaseAgentYield, None]:
        raise NotImplementedError("Subclasses must implement _stream().")
        yield  # pragma: no cover
