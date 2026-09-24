"""
Structured output models for the ticket triage agent.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TicketTriageOutput(BaseModel):
    """The structured triage result the LLM must produce for a ticket."""

    model_config = ConfigDict(str_strip_whitespace=True)

    category: str
    priority: Literal["low", "medium", "high", "urgent"]
    summary: str = Field(min_length=1)
    cited_article_ids: list[int]
