import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TaskState(str, Enum):
    working = "working"
    completed = "completed"
    input_required = "input_required"
    canceled = "canceled"
    failed = "failed"
    rejected = "rejected"


TERMINAL_TASK_STATES = {
    TaskState.completed,
    TaskState.input_required,
    TaskState.canceled,
    TaskState.failed,
    TaskState.rejected,
}


class TextContent(BaseModel):
    type: Literal["text"] = "text"
    text: str


class DataContent(BaseModel):
    type: Literal["data"] = "data"
    data: dict[str, Any]


class BaseAgentYield(ABC, BaseModel):
    content: list[TextContent | DataContent] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        self.metadata.setdefault("timestamp", datetime.now(timezone.utc).isoformat())

    @property
    @abstractmethod
    def is_terminal(self) -> bool: ...


class ArtifactUpdateYield(BaseAgentYield):
    """The (partial or final) result of a task. This is your agent's actual output."""

    state: Literal[TaskState.working, TaskState.completed, TaskState.input_required]
    artifact_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str | None = None
    last_chunk: bool = False

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_TASK_STATES and self.last_chunk


class TaskStatusUpdateYield(BaseAgentYield):
    """A progress/status message (e.g. "Searching knowledge base..."). NOT a deliverable."""

    state: Literal[TaskState.working, TaskState.input_required, TaskState.failed] = (
        TaskState.working
    )

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_TASK_STATES


class StreamAgentRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(min_length=1)
    context_id: str = Field(min_length=1)
    task_id: str | None = None
    skill_id: str | None = None
    metadata: dict[str, Any] | None = None
