# Welcome

Thanks for taking the time to work on this take-home exercise! It's designed
to take a few hours, not a few days — we're far more interested in how you
think about structure, validation, and error handling than in a
feature-complete product.

## What this is

This repo is a **simplified scaffolding for an agent**, modeled on the
shape of our real production setup: a `BaseAgent` base class, a
`GenericAgentExecutor` that drives it, shared request/response `models`,
and an `mcp_server` exposing a tool over MCP. It's not a copy of our
production code, but the interfaces and conventions (streaming yields,
terminal artifacts, error handling via exceptions rather than swallowed
try/except blocks) are the real ones we use day to day.

Treat this folder as if it were the entire repo you were handed — it's
standalone and doesn't depend on anything else.

For context, our production stack for agents like this one is built on
three libraries: **a2a** (the agent-to-agent protocol `BaseAgent`/
`GenericAgentExecutor` are modeled on — not needed for this exercise,
since we've stripped it down to a plain streaming interface),
**pydantic-ai** (for the LLM agent itself), and **fastmcp** (for the
knowledge-base tool server). You're welcome to lean on them or not — use
whatever you're most comfortable with — but that's the stack this
scaffolding reflects, in case it's useful context for how to approach it.

## Your task

Implement a `TicketTriageAgent` that triages incoming support tickets
against a knowledge base. Concretely:

- `_stream()` receives a `StreamAgentRequest` whose `query` is a raw
  support ticket description (e.g. "customer says their API calls started
  returning 429s an hour ago").
- Call the `search_kb` tool on the MCP server to retrieve candidate
  knowledge-base articles for the ticket. The MCP server runs as a
  separate service — your agent should connect to it over the network
  using `MCP_SERVER_URL` from the environment, not import it directly.
- Feed the ticket and the retrieved articles to an LLM, and make sure
  it returns:
  - `category`
  - `priority`
  - a short triage summary
  - which KB article ids were actually cited
- (optional) Consider validating that output before treating it as final.
- Implement `POST /batch` in `agent/app/__main__.py` to triage a list of tickets
  concurrently. Consider how to bound parallelism, enforce per-ticket timeouts,
  and handle partial failures gracefully.

You're filling in `agent/app/agent.py` (the agent itself), `agent/app/models.py`
(the structured output model(s) the LLM should produce), and the `POST /batch`
handler in `agent/app/__main__.py`. Everything under `core/` and `mcp_server/`
is provided infrastructure — you're welcome to read it (you'll need to, to use
it correctly), but you shouldn't need to modify it.

## What we're looking for

This is intentionally light on implementation instructions. We're far more
interested in the engineering judgment and practices you bring to it than
in any particular technique — use whatever patterns, libraries, or
structure you'd normally reach for to demonstrate:

- Solid validation and error handling.
- Clean, well-decomposed, readable code.
- Tests that give confidence in the behavior, including failure paths.
- Sensible scope — a working, well-considered solution beats a
  half-finished attempt at everything.

If anything in the spec feels ambiguous, write down the assumption you
made (and why) rather than silently guessing — a short `NOTES.md` is a
fine place for that.

# Setup

```bash
cd task-build-agent
cp .env.example .env             # fill in your LLM API key if you want to run with a real model
uv sync
uv run pytest                    # scaffolding tests should pass out of the box
```

The scaffolding tests in `core/tests/` and `mcp_server/tests/` test the
provided infrastructure, not your agent — they confirm your environment
is set up correctly before you start. Your own tests go in `agent/tests/`.

# Running

## 1. Tests (required)

We will run your tests to evaluate your submission:

```bash
uv run pytest agent/tests/
```

Your tests must pass without a live API key or running services.

## 2. Run locally (optional)

Start each service in a separate terminal:

```bash
# Terminal 1 — MCP server
uv run python -m mcp_server.app.main

# Terminal 2 — Agent
uv run python -m agent.app
```

Then call the agent:

```bash
curl -X POST localhost:8000/triage \
    -H "content-type: application/json" \
    -d '{"query": "customer says their API calls started returning 429s", "context_id": "demo"}'
```

## 3. Run with Docker Compose (optional)

```bash
docker compose up --build
```

This starts both services on a shared network with `MCP_SERVER_URL` wired
automatically. The agent is available on port `8000`.

## Do I need a real API key?

No. It's possible to write deterministic unit tests without calling a
real LLM — this is exactly how tests in the real codebase work. We'll grade your submission primarily by reading the code and running your tests, not by plugging in a real
LLM key.

If you *want* to see it run end-to-end with a real model, that's a
nice-to-have, not a requirement.

## Services and containers

The agent and the MCP server are designed to run as **separate containers**:

| Service | Dockerfile | Default port |
|---------|-----------|-------------|
| Agent HTTP server | `agent/Dockerfile` | `8000` |
| MCP knowledge-base server | `mcp_server/Dockerfile` | `8001` |

In production these two services communicate over the network via the MCP
protocol. Your agent design should reflect that boundary: the agent should
talk to the MCP server as a remote tool, not import and call `search_kb`
as a local function. How you wire that up (pydantic-ai's MCP client,
fastmcp's client, raw HTTP) is up to you.

## What's next — live coding session

After the take-home, we'll have a live coding session where you'll review and
fix a pull request containing someone else's implementation of this same agent.

**Before the session, make sure you're on the original scaffolding** (not your
own implementation) — the diff we send will be applied on top of it, so starting
from a modified repo will cause conflicts.

**To prepare:**
- Have your IDE ready and your environment set up (`uv sync` passing, tests green).
- Familiarise yourself with the scaffolding in `core/` and `mcp_server/` — you'll
  be reasoning about code that uses it, so understanding the contracts
  (`BaseAgent._stream`, `GenericAgentExecutor`, the yield/state model) will save
  you time.
- AI assistants are welcome and encouraged during the session. That said, we're
  interested in your own understanding of good software practices — lean on
  tooling to move fast, not to substitute for judgment.

We'll send you the diff to apply at the start of the session.