# Registry as Single Source of Truth

Plan for the agent-registry refactor and the newcomer documentation pass.

## Problem

An "agent" in this codebase is a system prompt plus a toolbox run through the generic
`run_agent` loop in `backend/agents/base.py` — there is no per-agent code. But the
knowledge of *what agents exist* lives in three places that must be edited in lockstep:

1. `backend/agents/registry.py` — the `AGENTS` dict (`AgentConfig` entries)
2. `backend/agents/orchestrator.py` — the hardcoded `TOOLS` list describing each agent
   as a callable function
3. `backend/agents/orchestrator.py` — the `SYSTEM_PROMPT` prose list
   ("- github_agent: use when…")

Adding a new agent (e.g. the planned web agent) requires all three edits. Forgetting
either orchestrator edit means the orchestrator silently can never route to the new
agent — nothing errors, nothing warns. The prompt and the schemas can also drift apart
over time since nothing ties them together.

There is also a documentation problem for anyone coming into the repo cold:

- No root README — no entry point explaining what this is, how to run it, or where
  things live.
- `docs/AGENTS.md` is stale: it lists a `get_readme` tool that doesn't exist and
  describes the deleted `github_agent.py` wrapper era.
- The extension path (add a tool, add an agent) exists only as convention in
  `tools/github.py` — nowhere written down.

## Approach

Make the registry the single source of truth. The orchestrator should *derive* its
view of the agents — both the tool schemas it hands to Ollama and the prose directory
in its system prompt — from `registry.AGENTS`, instead of duplicating it. After that,
adding an agent is exactly two things: **write a tool module, add a registry entry.**

This works because of a deliberate constraint worth keeping: every agent takes exactly
one `query: str` argument. That uniformity is what lets tool schemas be generated
mechanically and keeps agents swappable units. Don't generalize the signature until an
agent actually needs more.

What we're deliberately *not* building yet: base classes, schema-from-type-hints
decorators, plugin discovery. Two agents don't justify the machinery (see the
long-term section in `docs/TODO.md` — "don't build it yet, don't close the door").
The registry derivation is the one generalization that pays for itself immediately.

Documentation follows the same philosophy: written last, against the post-refactor
code, so it documents what actually exists.

## Solution

### 1. `backend/agents/registry.py`

Extend `AgentConfig` with a `description` field and add two derivation helpers:

```python
@dataclass(frozen=True)
class AgentConfig:
    name: str
    description: str      # one line: when the orchestrator should route here
    system_prompt: str
    tools: list
    tool_map: dict

AGENTS: dict[str, AgentConfig] = {
    "github_agent": AgentConfig(
        name="github_agent",
        description="Fetch live data from GitHub — repos, file trees, file contents, READMEs.",
        system_prompt=github.SYSTEM_PROMPT,
        tools=github.TOOLS,
        tool_map=github.TOOL_MAP,
    ),
}

def orchestrator_tools() -> list:
    """Ollama tool schemas exposing each registered agent as a callable function."""
    return [{
        "type": "function",
        "function": {
            "name": a.name,
            "description": a.description,
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "What you need from this agent"}},
                "required": ["query"],
            },
        },
    } for a in AGENTS.values()]

def agent_directory() -> str:
    """Prose list of agents for interpolation into the orchestrator system prompt."""
    return "\n".join(f"- {a.name}: {a.description}" for a in AGENTS.values())
```

The `description` does double duty: it's the routing hint the orchestrator model sees
in both the tool schema and the system prompt, so it should be written as steering
("use when…"), not documentation.

### 2. `backend/agents/orchestrator.py`

- Delete the hardcoded `TOOLS` list; use `registry.orchestrator_tools()` in the
  planner call. Compute once (module level or top of `run()`), not per round.
- Rebuild `SYSTEM_PROMPT` with the directory interpolated:

  ```python
  SYSTEM_PROMPT = f"""You are a helpful assistant. Be concise and direct.

  You have access to specialized agents that can fetch real data:
  {registry.agent_directory()}

  If you can answer from your own knowledge, do so. Only call an agent when you need live data."""
  ```

- Dead-code cleanup while rewriting this exact region (clears three TODO.md
  housekeeping items): `PLANNER_SYSTEM_PROMPT`, the stray session-notes docstring,
  the commented-out planner line and the `"""need to implement..."""` string inside
  `run()`, and the unused `OLLAMA_URL` constant.

### 3. `backend/agents/base.py` (comment-only)

- Fix the stale header comment ("Plain async function — not a generator";
  `run_agent` is an async generator now).
- Delete the unused `tool_history = []` — the orchestrator builds its own.

### 4. Tests — new `backend/tests/test_registry.py`

- `orchestrator_tools()` returns one schema per `AGENTS` entry, each with
  `type == "function"`, name matching its dict key, and a required `query` param.
- `agent_directory()` contains every agent name and description.
- Consistency check on each `AgentConfig`: every name in the `tools` schemas has a
  matching entry in `tool_map` and vice versa — catches the "added the function,
  forgot the schema" mistake for all current and future agents.

Run with `.venv/bin/python -m pytest -q` from `backend/`; the existing 14 tests must
stay green.

### 5. Documentation

**New root `README.md`** — the newcomer entry point, a screenful or two:

1. *What this is* — interactive multi-agent system on local hardware: FastAPI + Ollama
   backend, Next.js 15 frontend; an orchestrator routes chat queries to specialist
   sub-agents and streams structured activity (agents running, tools firing, timings)
   to the UI as NDJSON.
2. *Architecture in one diagram* — the two-layer tool model (orchestrator routes
   between **agents**; each agent runs its own **domain tool** loop), condensed from
   `docs/STREAMING.md`. State the two invariants: every tools-attached call is
   non-streaming; exactly one streaming call per run (final synthesis, tools stripped).
3. *Repo map* — `backend/main.py` (FastAPI, `/generate` NDJSON endpoint),
   `backend/agents/` (orchestrator, base loop, registry, events, ollama client),
   `backend/tools/` (one module per agent toolbox), `frontend/app/page.tsx`
   (event-driven chat UI), `docs/` (design deep-dives).
4. *Running it* — prerequisites (Ollama running locally, Python 3.13+, Node);
   backend: `cd backend && source .venv/bin/activate && fastapi dev main.py`;
   frontend: `cd frontend && npm install && npm run dev` (port 3000 — CORS is pinned
   to it in `main.py`). Optional `GITHUB_TOKEN` for higher GitHub rate limits.
   Tests: `.venv/bin/python -m pytest -q`.
5. *Event protocol at a glance* — compact table of the NDJSON event types from
   `backend/agents/events.py`, one line each; point to `docs/STREAMING.md` for depth.
6. *Extending* — two-line teaser pointing at `docs/EXTENDING.md`.

**New `docs/EXTENDING.md`** — the how-to guide, written against post-refactor code:

1. *Concepts* — an agent is `AgentConfig` = prompt + toolbox; the registry is the
   single source of truth; the orchestrator derives its routing tools and prompt
   directory from it; all agents share the `query: str` signature.
2. *Recipe: add a tool to an existing agent* — three edits in one tool module
   (implementation, `TOOLS` schema, `TOOL_MAP` entry), with a worked `list_issues`
   example for `tools/github.py`. House conventions:
   - return trimmed dicts, never raw API payloads
   - return `{"error": "..."}` for expected failures so the model can recover; let
     unexpected ones raise into `run_agent`'s per-tool try/except
   - return JSON-serializable values (results are `json.dumps`-ed into the transcript)
   - write schema descriptions as steering advice to the model (`search_repos`'s
     "Use simple keywords only…" is the exemplar)
3. *Recipe: add a new agent* — worked `web_agent` example: create `tools/web.py` with
   the four-piece pattern (`SYSTEM_PROMPT`, implementations, `TOOLS`, `TOOL_MAP`),
   add one `AgentConfig` entry to `registry.AGENTS`. Nothing else — the orchestrator
   picks it up automatically, and the frontend needs no changes (events carry the
   agent name).
4. *How to verify a new agent* — curl `/generate` and read the raw NDJSON (expected
   order: routing → `agent_start` → `tool_call`(s) → `agent_end` → `token`s → `done`),
   plus the registry consistency test.
5. *What not to do yet* — no base classes, decorators, or plugin systems; link to
   `docs/TODO.md`'s long-term section.

**Refresh `docs/AGENTS.md`**:

- Fix the GitHub agent's tool list to reality: `search_repos`, `get_repo`,
  `get_repo_tree`, `get_file` (no `get_readme`).
- Remove references to the deleted `github_agent.py` wrapper; agents are registry
  entries now.
- Keep the planned-agents roadmap (web search agent, frontend agent) — vision, not
  rot — with a pointer: "to build one of these, follow docs/EXTENDING.md".

**`TODO.md` bookkeeping** — move the cleared housekeeping items to Done; note the
registry is now the single source of truth.

### Execution order

1. Registry refactor (`registry.py` → `orchestrator.py` → `base.py` comments)
2. `test_registry.py`; run the full suite
3. Live smoke test
4. Docs (`README.md`, `docs/EXTENDING.md`, `docs/AGENTS.md`) — last, so they describe
   the code as it ends up
5. `TODO.md` bookkeeping

### Verification

1. `cd backend && .venv/bin/python -m pytest -q` — existing 14 tests plus new registry
   tests pass.
2. Static check:
   `.venv/bin/python -c "from agents import registry; print(registry.orchestrator_tools()); print(registry.agent_directory())"`
3. Live end-to-end (needs Ollama running): start the backend, then

   ```sh
   curl -N localhost:8000/generate -H 'content-type: application/json' \
     -d '{"model": "<local model>", "messages": [{"role": "user", "content": "what files are in vercel/next.js?"}], "think": false}'
   ```

   and confirm the NDJSON event order. Behavior must be identical to pre-refactor —
   the generated schema/prompt content matches what was hardcoded.
4. Docs check: follow README's "Running it" verbatim in a clean shell; walk the
   EXTENDING.md add-a-tool recipe against the real `tools/github.py` and confirm every
   referenced symbol exists.
