## Data loading robustness
- Extracted loading into `load_articles()` — a pure, unit-testable function.
- Structured exception (`KnowledgeBaseError`) with chained causes (`raise ... from exc`)
  instead of raw `json`/OS errors leaking to callers.
- Fail-fast schema validation: every article must have id:int and
  title/body/product_area:str. Malformed data surfaces at startup, not mid-request.
- Used `logging` (not `print`) so the host application controls output/levels.
- Known tradeoff: module-level call preserves startup fail-fast semantics but keeps
  an import-time side effect. In production I'd load via a FastMCP lifespan handler
  with a cached accessor.

## Ticket triage agent assumptions
- **stdlib HTTP, no new deps.** Neither an LLM SDK nor an HTTP client is declared
  anywhere in the workspace, so `clients.py` uses `urllib.request` for both the MCP
  call and the LLM call, pushed onto worker threads via `asyncio.to_thread`.
- **LLM endpoint assumption.** The real LLM path targets an OpenAI-compatible
  `{LLM_BASE_URL}/chat/completions` endpoint (`LLM_API_KEY`/`LLM_BASE_URL`/`LLM_MODEL`,
  defaults `https://api.openai.com/v1` and `gpt-4o-mini`), with a `json_schema`
  `response_format` derived from `TicketTriageOutput.model_json_schema()`. A
  `LLM_TIMEOUT_SECONDS` env (default 60) was added for the HTTP call. If you'd rather
  use pydantic-ai or another SDK, only `clients.triage_with_llm` changes.
- **LLM retry/backoff.** Transient LLM failures (HTTP 429/5xx, network errors, and
  timeouts) are retried with exponential backoff up to `LLM_MAX_RETRIES` (default 2)
  attempts, sleeping `LLM_RETRY_BACKOFF_SECONDS * 2**(attempt-1)` (default 1.0s)
  between tries. Non-transient failures — 4xx validation/auth errors and malformed or
  schema-invalid responses — are *not* retried, since replaying them won't help.
- **MCP handshake.** `search_kb` speaks raw streamable-http JSON-RPC over
  `{MCP_SERVER_URL}/mcp`: `initialize` → capture `mcp-session-id` header →
  `notifications/initialized` → `tools/call`, parsing JSON and SSE (`data:`) bodies.
  `MCP_TIMEOUT_SECONDS`/`MCP_MAX_RETRIES` are honored; exhaustion raises
  `AgentError(user_facing=False)`.
- **Injection seams for testability.** `TicketTriageAgent(llm=..., kb_search=...)`
  defaults to the client callables so tests inject fakes and run with no live LLM
  key or MCP server. `_stream` never catches exceptions — failures propagate and the
  executor marks the task `failed`.
- **Citation filtering.** `cited_article_ids` from the LLM are intersected with the
  ids actually returned by the KB search before the artifact is emitted.
- **Batch semantics.** `POST /batch` bounds parallelism with a semaphore
  (`BATCH_MAX_CONCURRENCY`, default 5) and enforces per-ticket timeouts
  (`BATCH_TICKET_TIMEOUT_SECONDS`, default 30). A failed/timed-out ticket becomes a
  per-ticket `failed` item; the batch itself always returns 200 with partial results.
- **`app` name collision.** Both `agent/` and `mcp_server/` install a package named
  `app`. `agent/tests/conftest.py` prepends `agent/` to `sys.path` so test imports
  resolve to the agent package.
- **dotenv.** `agent/app/__main__.py` calls `load_dotenv()` (via the `python-dotenv`
  dependency on the agent package) so a local `.env` supplies `LLM_API_KEY`,
  `LLM_BASE_URL`, `LLM_MODEL`, etc. for `python -m agent.app`. Tests don't rely on
  it — they inject fakes. Gemini works through its OpenAI-compatible endpoint:
  `LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai`,
  `LLM_MODEL=gemini-3.8-flash`.

## Beyond the baseline spec

The README asks only for `_stream`, the output model, and `POST /batch`. The
following go beyond that minimum and are documented so their scope is explicit:

- **LLM retry/backoff** (`LLM_MAX_RETRIES` / `LLM_RETRY_BACKOFF_SECONDS`) — not
  requested; added for resilience on transient 429/5xx/timeout failures. Kept as an
  additive, env-gated behavior (defaults match the previous no-retry-ish behavior).
- **Empty-KB short-circuit** — when `search_kb` returns no articles, `_stream` emits
  a deterministic `TicketTriageOutput` (`"No relevant articles found."`, priority
  `low`) and skips the LLM call entirely, rather than paying for a call that has
  nothing to triage against.
- **`python-dotenv` + `.env` auto-loading** — the spec describes env coming from the
  process environment (and `AGENTS.md` notes nothing auto-loads `.env`); we added
  `load_dotenv()` at the agent entrypoint for local-dev convenience. Tests are
  unaffected (they inject fakes).
- **`_to_strict_json_schema`** — strips pydantic-only keywords and adds
  `additionalProperties: false` so the `json_schema` `response_format` is accepted
  under OpenAI `strict: true`. This is an implementation detail beyond the "just
  return JSON" minimum.
- **`agent/README.md`** — a separate implementation README; the root `README.md` is
  left untouched as the original spec.
- **Logging config in the entrypoint** — `logging.basicConfig` lives in
  `main()` (`__main__.py`), not in the `clients` library module, so importing the
  client doesn't mutate the root logger; `clients` only obtains a module `logger`.

## Running locally (curl)

Start both services first (separate terminals):

```bash
uv run python -m mcp_server.app.main   # MCP server on 8001
uv run python -m agent.app             # agent on 8000
```

Then:

```bash
# health
curl http://127.0.0.1:8000/health

# /triage
curl -X POST http://127.0.0.1:8000/triage -H "Content-Type: application/json" -d "{\"query\":\"API calls returning 429s\",\"context_id\":\"c1\"}"

# /batch
curl -X POST http://127.0.0.1:8000/batch -H "Content-Type: application/json" -d "{\"tickets\":[{\"query\":\"429 errors\",\"context_id\":\"c1\"},{\"query\":\"login broken\",\"context_id\":\"c2\"}]}"
```

The `\"` escapes are for Windows `cmd.exe`, which treats single quotes as literal
characters. On bash/zsh use single quotes instead, e.g.
`-d '{"query":"API calls returning 429s","context_id":"c1"}'`.