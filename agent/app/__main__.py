import asyncio
import os

import click
import uvicorn
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from core.generic_executor import ExecutionResult, GenericAgentExecutor
from core.models import StreamAgentRequest, TaskState

from .agent import TicketTriageAgent

load_dotenv()


class BatchTriageRequest(BaseModel):
    tickets: list[StreamAgentRequest]


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _result_to_item(result: ExecutionResult) -> dict:
    artifact = result.final_artifact
    return {
        "status": result.status.value,
        "artifact": artifact.model_dump(mode="json") if artifact else None,
        "error": str(result.error) if result.error else None,
    }


async def run_batch(
    executor: GenericAgentExecutor,
    tickets: list[StreamAgentRequest],
    max_concurrency: int,
    timeout: float,
) -> list[dict]:
    """Triage `tickets` concurrently, bounding parallelism and per-ticket time.

    A failing or timed-out ticket becomes a ``failed`` item; it never fails
    the whole batch.
    """
    semaphore = asyncio.Semaphore(max_concurrency)

    async def run_one(ticket: StreamAgentRequest) -> dict:
        async with semaphore:
            try:
                result = await asyncio.wait_for(executor.execute(ticket), timeout=timeout)
            except TimeoutError:
                return {
                    "status": TaskState.failed.value,
                    "artifact": None,
                    "error": f"timed out after {timeout}s",
                }
            except Exception as exc:
                return {
                    "status": TaskState.failed.value,
                    "artifact": None,
                    "error": str(exc),
                }
        return _result_to_item(result)

    outcomes = await asyncio.gather(
        *(run_one(ticket) for ticket in tickets), return_exceptions=True
    )
    return [
        {"status": TaskState.failed.value, "artifact": None, "error": str(outcome)}
        if isinstance(outcome, BaseException)
        else outcome
        for outcome in outcomes
    ]


def create_app() -> Starlette:
    executor = GenericAgentExecutor(agent=TicketTriageAgent())

    async def health(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    async def triage(request: Request) -> JSONResponse:
        try:
            agent_request = StreamAgentRequest(**await request.json())
        except ValidationError as exc:
            return JSONResponse({"errors": exc.errors()}, status_code=400)

        result = await executor.execute(agent_request)
        artifact = result.final_artifact
        return JSONResponse(
            {
                "status": result.status.value,
                "artifact": artifact.model_dump(mode="json") if artifact else None,
                "error": str(result.error) if result.error else None,
            },
            status_code=200 if result.status == TaskState.completed else 502,
        )

    async def batch_triage(request: Request) -> JSONResponse:
        try:
            batch = BatchTriageRequest(**await request.json())
        except ValidationError as exc:
            return JSONResponse({"errors": exc.errors()}, status_code=400)

        max_concurrency = max(1, _env_int("BATCH_MAX_CONCURRENCY", 5))
        timeout = _env_int("BATCH_TICKET_TIMEOUT_SECONDS", 30)
        results = await run_batch(executor, batch.tickets, max_concurrency, timeout)
        return JSONResponse({"results": results})

    return Starlette(
        routes=[
            Route("/health", health),
            Route("/triage", triage, methods=["POST"]),
            Route("/batch", batch_triage, methods=["POST"]),
        ]
    )


@click.command()
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", default=8000, help="Port to bind to")
@click.option("--reload", is_flag=True, default=False, help="Enable auto-reload") # for debugging
def main(host: str, port: int, reload: bool) -> None:
    """Run the Ticket Triage Agent behind a minimal HTTP server."""
    uvicorn.run(
        # create_app(),
         "agent.app.__main__:create_app",
        host=host,
        port=port,
        reload=reload)


if __name__ == "__main__":
    main()
