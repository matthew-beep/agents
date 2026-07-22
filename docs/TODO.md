# TODO

## Planner-based routing (high priority)

Replace the current streaming-then-reset pattern with a two-step routing approach:

### 1. Add `format` param to `ollama.chat()` (`ollama.py`)
Pass `"format": "json"` through `_chat_payload` so the planner call gets structured output.

### 2. Rewrite `orchestrator.run()` (`orchestrator.py`)

**Planner call** — non-streaming, JSON mode, new system prompt:
- Returns `{"mode": "direct"}` or `{"mode": "agentic", "plan": "...", "agents": [{"name": "github_agent", "query": "..."}]}`
- Use a single `httpx.AsyncClient` for the whole `run()` lifetime

**Direct path** — pipe straight into `ollama.emit_token_stream()`

**Agentic path:**
1. Emit `plan_event` (with `duration_ms` from planner call)
2. For each agent in the planner response: emit `agent_start_event`, run `agent.run()`, emit `agent_end_event` with `tool_history`
3. Append agent results to messages, emit `emit_token_stream()` for synthesis

No `reset` event.

---

## Streaming + agent events (high priority)

Three things to fix, in order:

### 1. Fix burst streaming (orchestrator.py)
Remove `content_buffer`. Yield content chunks live inside the `async for` loop while the stream is open. If tool_calls appear after content has already been yielded, emit `{"type": "reset"}` so the frontend discards the partial content.

### 2. Clean sub-agent boundary (already done)
Sub-agents are non-streaming reasoning units — they run a tool loop, synthesize a result, and return `(content, tool_history)`. No streaming, no UI assumptions. Keep it this way.

### 3. Minimal orchestration events (UI signals only, already done)
`agent_start` and `agent_end` are emitted by the orchestrator as UI signals only — they are not part of streaming logic. Frontend renders them as the agent activity panel.

---

## Long-term: streaming multi-agent runtime

The end goal is a system where multiple agents can run concurrently and the user sees their state as it evolves — not just a final answer.

**What this looks like:**
- Orchestrator fans out to multiple agents in parallel (GitHub agent + search agent + code agent, etc.)
- Each agent emits a continuous stream of events (`agent_start`, `tool_call`, `tool_result`, `text_delta`)
- Frontend renders a live timeline of agent activity — ongoing reasoning made visible, not just results
- Orchestrator becomes a scheduler that routes tools and merges agent streams, not a sequential caller

**Evolution path from current system:**
1. Fix streaming + agent events (current priority)
2. Add more sequential agents
3. Run agents in parallel, merge event streams
4. Full observable runtime with live agent panels

The decisions made now (streaming orchestrator, event-based frontend, fire-and-collect sub-agents) open the door to this without a rewrite. Don't build it yet — but don't close the door either.

---

## Agents-listing endpoint

Add a `GET /agents` (or similar) endpoint in `main.py` that exposes `registry.AGENTS`
metadata (name, description, tool count) to the frontend — currently nothing surfaces
this outside the backend; the frontend only ever learns an agent exists when it
happens to fire during a chat run.

Needed for any "see the existing agents" screen — the Agent Roster concept from the
`Wireframes`/`Wireframes v2` designs surveyed in `docs/USER_FLOW.md`, and relevant to
either candidate philosophy there (guided-workflow or fleet-monitoring): both need
some way to list what agents exist independent of a specific chat run. Low-effort
since `registry.py` already derives `orchestrator_tools()`/`agent_directory()` from
`AGENTS` — this is the same derivation, exposed as an HTTP response instead of prompt
text.

---

## Filter binary files from get_repo_tree

Add `BINARY_EXTENSIONS` set in `tools/github.py` and skip those paths in `_build_tree`. Repos with large example image folders (e.g. `example/courthouse/000000.png x286`) bloat the tree and slow down Ollama's context processing.

---

## .env + GITHUB_TOKEN

Add `python-dotenv` to `requirements.txt`, load `.env` in `tools/github.py`. Bumps GitHub API rate limit from 10 to 30 req/min — needed for multi-repo research queries.

---

## Done

### GitHub agent: search_code, list_issues, shared request helper ✓
- `tools/api.py` — new `get_json()`: generic GET → status-check → `raise_for_status()`
  → `.json()` helper, GitHub-agnostic (no base URL/auth), reusable by future agents.
- `tools/github.py` — existing 4 tools refactored to use it (behavior-identical); added
  `search_code` (requires `GITHUB_TOKEN`, no anonymous fallback) and `list_issues`.
- `tests/test_api.py` — dependency-free unit tests for `get_json` (no mocking lib
  needed). No unit tests for the GitHub-specific tools themselves — matches this
  project's live-verification convention (see `docs/WEB_AGENT.md`).
- Found via live testing: `facebook/react` has been renamed at the org level (now
  canonically `react/react`), so GitHub 301-redirects requests to the old owner/repo
  path. `httpx.AsyncClient` doesn't follow redirects by default, so every GitHub tool
  was silently failing on any renamed repo — `get_json` now passes
  `follow_redirects=True`, fixing it for all 6 tools at once.

### Agent activity panel ✓
- `base.py` — plain `async def run_agent(...)` returning `tuple[str, list[dict]]`. Accumulates `tool_history` across loop iterations.
- `github_agent.py` — drops the generator, returns `await run_agent(...)` directly.
- `orchestrator.py` — owns the Ollama loop. Yields `{"type": "agent_start"}` before each sub-agent call, `{"type": "agent_end", "tools": tool_history}` after. Sub-agents are fire-and-collect.
- Frontend — `AgentActivity[]` state. `agent_start` pushes a running entry; `agent_end` marks it done and attaches tools. Panel shows `GitHub Agent ✓ (2 tools)` with click-to-expand tool list. Trace persists on the message after streaming ends.
