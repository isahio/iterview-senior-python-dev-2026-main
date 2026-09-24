"""Tests for the LLM client's retry/backoff behavior."""

import pytest

import app.clients as clients
from app.models import TicketTriageOutput
from core.exceptions import AgentError


def _output() -> TicketTriageOutput:
    return TicketTriageOutput(
        category="api",
        priority="high",
        summary="rate limited",
        cited_article_ids=[1],
    )


async def test_transient_errors_are_retried_then_succeed(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MAX_RETRIES", "2")
    monkeypatch.setenv("LLM_RETRY_BACKOFF_SECONDS", "0")

    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise clients._TransientError("temporary outage")
        return _output()

    monkeypatch.setattr(clients, "_call_llm_sync", flaky)

    output = await clients.triage_with_llm("429 errors", [{"id": 1}])

    assert output.summary == "rate limited"
    assert calls["n"] == 3


async def test_non_transient_errors_are_not_retried(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MAX_RETRIES", "2")
    monkeypatch.setenv("LLM_RETRY_BACKOFF_SECONDS", "0")

    calls = {"n": 0}

    def failing(*args, **kwargs):
        calls["n"] += 1
        raise RuntimeError("bad request")

    monkeypatch.setattr(clients, "_call_llm_sync", failing)

    with pytest.raises(AgentError):
        await clients.triage_with_llm("429 errors", [{"id": 1}])

    assert calls["n"] == 1


async def test_retries_are_exhausted_then_fail(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MAX_RETRIES", "1")
    monkeypatch.setenv("LLM_RETRY_BACKOFF_SECONDS", "0")

    calls = {"n": 0}

    def always_transient(*args, **kwargs):
        calls["n"] += 1
        raise clients._TransientError("still down")

    monkeypatch.setattr(clients, "_call_llm_sync", always_transient)

    with pytest.raises(AgentError):
        await clients.triage_with_llm("429 errors", [{"id": 1}])

    assert calls["n"] == 2
