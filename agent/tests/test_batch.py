"""Tests for the concurrent batch-triage path (run_batch + POST /batch)."""

import asyncio
import json

import app.clients as clients
from app.__main__ import create_app, run_batch
from app.models import TicketTriageOutput
from core.models import ArtifactUpdateYield, DataContent, StreamAgentRequest, TaskState
from starlette.requests import Request


class _StubResult:
    def __init__(self, status: TaskState, error: Exception | None = None):
        self.status = status
        self.error = error

    @property
    def final_artifact(self) -> ArtifactUpdateYield:
        return ArtifactUpdateYield(
            state=self.status,
            last_chunk=True,
            content=[DataContent(data={"ok": True})],
        )


class _StubExecutor:
    """Tracks concurrent calls; fails/sleeps based on the ticket query."""

    def __init__(self):
        self.active = 0
        self.max_active = 0

    async def execute(self, request: StreamAgentRequest) -> _StubResult:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.01)
            if request.query == "slow":
                await asyncio.sleep(1.0)
            if request.query == "boom":
                raise ValueError("boom")
            return _StubResult(TaskState.completed)
        finally:
            self.active -= 1


def _ticket(query: str, context_id: str) -> StreamAgentRequest:
    return StreamAgentRequest(query=query, context_id=context_id)


async def test_semaphore_bounds_concurrency():
    tickets = [_ticket("ok", f"c{i}") for i in range(10)]
    executor = _StubExecutor()
    results = await run_batch(executor, tickets, max_concurrency=3, timeout=5)

    assert 2 <= executor.max_active <= 3, executor.max_active
    assert all(r["status"] == "completed" for r in results)


async def test_timed_out_ticket_becomes_failed_item():
    tickets = [_ticket("slow", "c1"), _ticket("ok", "c2")]
    executor = _StubExecutor()
    results = await run_batch(executor, tickets, max_concurrency=2, timeout=0.05)

    assert results[0]["status"] == "failed"
    assert "timed out" in results[0]["error"]
    assert results[1]["status"] == "completed"


async def test_one_failing_ticket_leaves_others_completed():
    tickets = [_ticket("boom", "c1"), _ticket("ok", "c2"), _ticket("ok", "c3")]
    executor = _StubExecutor()
    results = await run_batch(executor, tickets, max_concurrency=3, timeout=5)

    assert results[0]["status"] == "failed"
    assert results[0]["error"] == "boom"
    assert results[1]["status"] == "completed"
    assert results[2]["status"] == "completed"


def _make_request(body: dict) -> Request:
    async def receive():
        return {
            "type": "http.request",
            "body": json.dumps(body).encode("utf-8"),
            "more_body": False,
        }

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/batch",
            "headers": [(b"content-type", b"application/json")],
            "query_string": b"",
        },
        receive=receive,
    )


def _batch_handler():
    application = create_app()
    return next(r.endpoint for r in application.routes if r.path == "/batch")


async def test_batch_triage_returns_400_on_bad_body():
    handler = _batch_handler()
    response = await handler(_make_request({"tickets": "not-a-list"}))

    assert response.status_code == 400


async def test_batch_triage_returns_200_with_results(monkeypatch):
    async def fake_search(query, max_results=3):
        return [{"id": 1, "title": "t", "body": "b", "product_area": "p"}]

    async def fake_llm(query, articles):
        return TicketTriageOutput(
            category="api", priority="high", summary="s", cited_article_ids=[1]
        )

    monkeypatch.setattr(clients, "search_kb", fake_search)
    monkeypatch.setattr(clients, "triage_with_llm", fake_llm)

    handler = _batch_handler()
    response = await handler(
        _make_request({"tickets": [{"query": "429", "context_id": "c1"}]})
    )

    assert response.status_code == 200
    payload = json.loads(response.body)
    assert payload["results"][0]["status"] == "completed"
