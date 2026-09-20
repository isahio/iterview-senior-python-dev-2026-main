"""
HTTP clients for the ticket triage agent.

Both the MCP knowledge-base lookup and the LLM call use the standard
library (`urllib.request`) rather than a third-party SDK — neither an LLM
SDK nor an HTTP client is declared anywhere in the workspace. The blocking
HTTP work is pushed onto a worker thread via `asyncio.to_thread` so the
async agent loop is never blocked.

The public functions here are the defaults wired into `TicketTriageAgent`;
tests inject fakes so they never need a live MCP server or LLM key.
"""

import asyncio
import json
import os
import urllib.error
import urllib.request
from typing import Any

from pydantic import ValidationError

from core.exceptions import AgentError

from .models import TicketTriageOutput


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value is not None else default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# MCP knowledge-base client (streamable-http JSON-RPC over urllib)
# ---------------------------------------------------------------------------

_MCP_PROTOCOL_VERSION = "2025-06-18"


def _post(
    url: str,
    payload: dict[str, Any],
    session_id: str | None,
    timeout: int,
) -> tuple[int, dict[str, str], str]:
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id

    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
            response_headers = {k.lower(): v for k, v in response.getheaders()}
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"POST {url} failed ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"POST {url} failed: {exc.reason}") from exc
    return status, response_headers, raw


def _parse_sse(raw: str) -> Any | None:
    """Parse a Server-Sent Events body, returning the last JSON payload."""
    data_lines: list[str] = []
    messages: list[Any] = []
    for line in raw.splitlines():
        if line.startswith("data:"):
            data_lines.append(line[len("data:"):].lstrip())
        elif line == "" and data_lines:
            payload = "\n".join(data_lines).strip()
            if payload:
                messages.append(json.loads(payload))
            data_lines = []
    if data_lines:
        payload = "\n".join(data_lines).strip()
        if payload:
            messages.append(json.loads(payload))
    return messages[-1] if messages else None


def _parse_body(raw: str, content_type: str) -> Any | None:
    if not raw.strip():
        return None
    if "text/event-stream" in content_type.lower():
        return _parse_sse(raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return _parse_sse(raw)


def _extract_articles(content: Any) -> list[dict]:
    articles: list[dict] = []
    for block in content or []:
        if not isinstance(block, dict) or block.get("type") != "text":
            continue
        text = block.get("text")
        if not isinstance(text, str):
            continue
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, list):
            articles.extend(item for item in parsed if isinstance(item, dict))
    return articles


def _run_mcp_session(
    base_url: str,
    query: str,
    max_results: int,
    timeout: int,
) -> list[dict]:
    mcp_url = f"{base_url}/mcp"

    _, headers, raw = _post(
        mcp_url,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": _MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "ticket-triage-agent", "version": "0.1.0"},
            },
        },
        None,
        timeout,
    )
    init_response = _parse_body(raw, headers.get("content-type", ""))
    if init_response is None:
        raise RuntimeError("empty initialize response from MCP server")
    if "error" in init_response:
        raise RuntimeError(f"MCP initialize error: {init_response['error']}")
    session_id = headers.get("mcp-session-id")

    _post(
        mcp_url,
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        session_id,
        timeout,
    )

    _, headers, raw = _post(
        mcp_url,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "search_kb",
                "arguments": {"query": query, "max_results": max_results},
            },
        },
        session_id,
        timeout,
    )
    call_response = _parse_body(raw, headers.get("content-type", ""))
    if call_response is None:
        raise RuntimeError("empty tools/call response from MCP server")
    if "error" in call_response:
        raise RuntimeError(f"MCP tools/call error: {call_response['error']}")
    content = (call_response.get("result") or {}).get("content", [])
    return _extract_articles(content)


def _search_kb_sync(
    base_url: str,
    query: str,
    max_results: int,
    timeout: int,
    max_retries: int,
) -> list[dict]:
    attempts = max_retries + 1
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return _run_mcp_session(base_url, query, max_results, timeout)
        except Exception as exc:
            last_exc = exc
            if attempt < attempts:
                continue
    raise AgentError(
        f"search_kb failed after {attempts} attempt(s): {last_exc}",
        user_facing=False,
    ) from last_exc


async def search_kb(query: str, max_results: int = 3) -> list[dict]:
    """Search the knowledge base over MCP (streamable-http), with retries."""
    base_url = _env_str("MCP_SERVER_URL", "http://localhost:8001").rstrip("/")
    timeout = _env_int("MCP_TIMEOUT_SECONDS", 5)
    max_retries = _env_int("MCP_MAX_RETRIES", 2)
    return await asyncio.to_thread(
        _search_kb_sync, base_url, query, max_results, timeout, max_retries
    )


# ---------------------------------------------------------------------------
# LLM client (OpenAI-compatible chat completions over urllib)
# ---------------------------------------------------------------------------

_DEFAULT_LLM_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_LLM_MODEL = "gpt-4o-mini"

_SYSTEM_PROMPT = (
    "You are a support-ticket triage assistant. Classify the ticket into a "
    "short category, assign a priority (low, medium, high, or urgent), write "
    "a brief triage summary, and list the knowledge-base article ids you "
    "actually cite."
)


def _to_strict_json_schema(schema: Any) -> Any:
    """Recursively strip pydantic-only keywords and enforce strict-schema rules."""
    if isinstance(schema, dict):
        cleaned: dict[str, Any] = {}
        for key, value in schema.items():
            if key in ("title", "default", "examples"):
                continue
            cleaned[key] = _to_strict_json_schema(value)
        if cleaned.get("type") == "object" and "additionalProperties" not in cleaned:
            cleaned["additionalProperties"] = False
        return cleaned
    if isinstance(schema, list):
        return [_to_strict_json_schema(item) for item in schema]
    return schema


def _build_llm_payload(model: str, query: str, articles: list[dict]) -> dict[str, Any]:
    user_content = (
        f"Ticket description:\n{query}\n\n"
        f"Knowledge-base articles (JSON):\n"
        f"{json.dumps(articles, ensure_ascii=False)}"
    )
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "ticket_triage_output",
                "schema": _to_strict_json_schema(TicketTriageOutput.model_json_schema()),
                "strict": True,
            },
        },
    }


def _call_llm_sync(
    base_url: str,
    api_key: str,
    model: str,
    query: str,
    articles: list[dict],
    timeout: int,
) -> TicketTriageOutput:
    payload = _build_llm_payload(model, query, articles)
    url = f"{base_url.rstrip('/')}/chat/completions"
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM call failed ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"LLM call failed: {exc.reason}") from exc

    try:
        data = json.loads(raw)
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"could not parse LLM response: {raw[:500]}") from exc

    try:
        if isinstance(content, str):
            return TicketTriageOutput.model_validate_json(content)
        return TicketTriageOutput.model_validate(content)
    except ValidationError as exc:
        raise RuntimeError(f"LLM returned invalid output: {exc}") from exc


async def triage_with_llm(query: str, articles: list[dict]) -> TicketTriageOutput:
    """Call an OpenAI-compatible chat-completions endpoint and validate its output."""
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        raise AgentError("LLM_API_KEY is not set", user_facing=False)

    base_url = _env_str("LLM_BASE_URL", _DEFAULT_LLM_BASE_URL)
    model = _env_str("LLM_MODEL", _DEFAULT_LLM_MODEL)
    timeout = _env_int("LLM_TIMEOUT_SECONDS", 60)
    try:
        return await asyncio.to_thread(
            _call_llm_sync, base_url, api_key, model, query, articles, timeout
        )
    except AgentError:
        raise
    except Exception as exc:
        raise AgentError(f"LLM triage failed: {exc}", user_facing=False) from exc
