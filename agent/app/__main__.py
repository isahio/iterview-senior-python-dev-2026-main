import click
import uvicorn
from pydantic import BaseModel, ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from core.generic_executor import GenericAgentExecutor
from core.models import StreamAgentRequest, TaskState

from .agent import TicketTriageAgent


class BatchTriageRequest(BaseModel):
    tickets: list[StreamAgentRequest]


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
        """
        TODO(candidate): triage a batch of tickets concurrently and return all results.

        Things to consider:
        - How do you bound the number of simultaneous LLM calls?
        - What happens when one ticket fails — does the whole batch fail, or do you
          return partial results?
        - How do you enforce a per-ticket timeout?
        """
        return JSONResponse({"error": "not implemented"}, status_code=501)

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
def main(host: str, port: int) -> None:
    """Run the Ticket Triage Agent behind a minimal HTTP server."""
    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":
    main()
