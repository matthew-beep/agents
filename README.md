# Agents

An interactive multi-agent system running on local hardware: a chat interface backed
by an orchestrator that routes queries to specialist sub-agents, each with their own
tool loop, and streams structured activity (which agent is running, what tools it's
calling, how long each step takes) back to the UI in real time.

**Stack:** FastAPI + Ollama backend, Next.js 15 frontend. All local, no cloud
dependencies.

## Architecture

Two layers, each with its own tool loop:

| Layer | Module | Tools it sees | Job |
|---|---|---|---|
| Orchestrator | `agents/orchestrator.py` | Agents (`github_agent`, …) | Decide *which agent* to invoke |
| Sub-agent | `agents/base.py` (`run_agent`) | Domain tools (`search_repos`, `get_file`, …) | Execute the agent's multi-step work |

The orchestrator doesn't know GitHub's API exists — it only knows `github_agent` is
callable. When the routing model calls it, the orchestrator hands off to `run_agent()`
with that agent's own tools:

```
User query
    │
    ▼
orchestrator.run()
    │  tools = [github_agent, …]     ← agent-level routing, stream: false
    │
    ├─► agent_start → github_agent
    │       │
    │       ▼
    │   run_agent(name, …, github.TOOLS, github.TOOL_MAP)
    │       │  stream: false on every round
    │       ├─► tool_call: get_repo_tree(…)
    │       ├─► tool_call: get_file(…)
    │       └─► agent_result: "Here's what I found…"
    │
    └─► final synthesis to user
        tools = null, stream: true   ← the only call that streams to the frontend
```

Two invariants hold everywhere in this system: every call with `tools` attached is
non-streaming (an Ollama serving-layer reliability rule, not a preference), and
exactly one call per request ever streams — the final synthesis, made only once
`tools` is stripped. Full rationale in `docs/STREAMING.md`.

**Agents are configuration, not code.** An agent is a system prompt plus a toolbox,
run through the one generic `run_agent` loop — there's no per-agent Python class.
`agents/registry.py` is the single source of truth for which agents exist; the
orchestrator derives its routing tool schemas and system prompt from it. See
"Extending" below.

## Repo map

```
backend/
  main.py                — FastAPI app. POST /generate streams NDJSON; GET /search proxies GitHub search.
  agents/
    orchestrator.py       — routes queries to agents, runs the routing loop, streams final synthesis
    base.py                — run_agent(): the shared async-generator tool loop every agent runs through
    registry.py             — AgentConfig registry; single source of truth for which agents exist
    ollama.py                — Ollama /api/chat client: non-streaming chat(), streaming emit_token_stream()
    events.py                 — NDJSON event schema + emit()
  tools/
    github.py              — GitHub agent's toolbox: system prompt, tool functions, schemas, TOOL_MAP
  tests/
frontend/
  app/page.tsx            — chat UI; consumes the NDJSON event stream, renders the agent activity panel
  types/index.ts            — event/message TypeScript types
docs/
  STREAMING.md             — event/streaming design deep-dive (why non-streaming tool calls, event schema)
  REGISTRY.md              — agent-registry design: why it's the source of truth, how to extend it
  ROADMAP.md, TODO.md, AGENTS.md, ...
```

## Running it

**Prerequisites:** [Ollama](https://ollama.com) running locally with at least one
tool-capable model pulled (e.g. `ollama pull qwen3.5:9b`); Python 3.13+; Node.

```sh
# Backend — serves on :8000
cd backend
source .venv/bin/activate
fastapi dev main.py

# Frontend — serves on :3000 (CORS in main.py is pinned to this origin)
cd frontend
npm install
npm run dev
```

Optional: `export GITHUB_TOKEN=...` before starting the backend to raise the GitHub
API rate limit from 10 to 30 req/min. Not yet loaded from a `.env` file — that's a
pending TODO item, so export it in your shell for now.

**Tests:**

```sh
cd backend && .venv/bin/python -m pytest -q
```

## Event protocol at a glance

The `/generate` endpoint streams newline-delimited JSON. One event per line:

| Event | When | Payload |
|---|---|---|
| `thinking` | Once, before the routing call | `{}` |
| `agent_start` | Orchestrator dispatches a sub-agent | `{ agent }` |
| `tool_call` | Each domain-tool invocation, live | `{ tool, args, duration_ms }` |
| `agent_end` | Sub-agent finishes | `{ agent, tools: ToolCall[], duration_ms }` |
| `agent_error` | A tool or agent call fails | `{ agent, error, tool? }` |
| `token` | Final synthesis, streamed | `{ content }` |
| `done` | Stream complete | `{ tokens, tokens_per_sec, duration_ms, total_ms }` |

Full schema and design rationale in `docs/STREAMING.md`.

## Extending

Adding a **tool to an existing agent** — e.g. `list_issues` on the GitHub agent — is
three edits in one file (`backend/tools/github.py`): the `async def` implementation,
a schema entry in `TOOLS`, and a `TOOL_MAP` entry. House conventions: return trimmed,
JSON-serializable data (never a raw API payload); return `{"error": "..."}` for
expected failures so the model can recover, and let unexpected ones raise; write
schema descriptions as steering advice to the model, not documentation.

Adding a **new agent** — e.g. a web-search agent — is a new tool module following the
same four-piece shape (`SYSTEM_PROMPT`, tool functions, `TOOLS`, `TOOL_MAP`) plus one
`AgentConfig` entry in `backend/agents/registry.py`. Nothing else: the orchestrator
picks it up automatically, and the frontend needs no changes since events carry the
agent name generically.

Design rationale and worked examples: `docs/REGISTRY.md`.
