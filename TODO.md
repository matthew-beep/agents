# TODO

Backend review pass — 2026-07-07. Ordered by priority.

## Quality

- [ ] **Trim `get_repo` response** — `backend/tools/github.py`. Returns the raw
      GitHub payload (~120 fields) straight into the sub-agent's context. Trim to
      `full_name`, `description`, `default_branch`, `stargazers_count`, `language`,
      `topics` — like `search_repos` already does.

## Housekeeping

(nothing currently)

## Minor / fine to ignore

(nothing currently)

## Done (from earlier passes)

- [x] **`plan_event` renamed to `thinking_event`** — matches `docs/STREAMING.md`'s
      original design: a content-free `{"type": "thinking"}` signal (no `content`/
      `duration_ms`), emitted once before the routing call, purely to give the
      frontend something to render before any other event exists. Backend:
      `events.py` (`ThinkingEvent`, `thinking_event()`), `orchestrator.py`'s call
      site, `test_events.py`. Frontend: `types/index.ts` (`ThinkingEvent`),
      `page.tsx` — the `plan` object state and its markdown bubble are gone,
      replaced by a `thinking: boolean` that drives the existing "..." loading
      indicator; set immediately on submit (not just on receipt of the wire event)
      so the UI has feedback before the first NDJSON line even arrives. README's
      event table updated to match.
- [x] **Dead code in `backend/agents/orchestrator.py` removed**: unused `OLLAMA_URL`
      constant and the stray `"""need to implement our own streaming responses
      here"""` docstring. (`PLANNER_SYSTEM_PROMPT` and the commented-out planner
      line were already gone by the time this was picked up.)
- [x] **HTTP client threading** — one `httpx.AsyncClient`, created once in
      `orchestrator.run()`, now threaded down through `run_agent()` (`base.py`) and
      into every `tools/github.py` function (`search_repos`, `get_repo`,
      `get_repo_tree`, `get_file`), instead of each layer opening its own. Each
      GitHub call keeps its original per-call timeout via `client.get(..., timeout=X)`
      rather than collapsing onto the Ollama layer's 300s default. `main.py`'s
      standalone `/search` endpoint (outside the orchestrator flow) opens its own
      short-lived client since it isn't part of that shared request lifecycle.
- [x] `AGENT_MAX_ROUNDS` cutoff no longer feeds the literal string "max rounds
      reached" into the final answer — `base.py` now yields "Stopped after N tool
      rounds without a final answer" plus any partial model content.
- [x] `base.py` preserves assistant `content` emitted alongside tool_calls instead of
      dropping it; tool-result messages in both `base.py` and `orchestrator.py` now
      carry `tool_name` so multi-tool-call rounds can be matched back to their call.
- [x] **Registry is now the single source of truth for agents** — `registry.py`
      gained `AgentConfig.description`, `orchestrator_tools()`, and
      `agent_directory()`; `orchestrator.py`'s hardcoded `TOOLS` list and
      `SYSTEM_PROMPT` agent list are now derived from the registry instead of
      hand-duplicated. Adding an agent is now one tool module + one registry
      entry — see `docs/REGISTRY.md` and `README.md`. Added
      `backend/tests/test_registry.py` (schema shape, directory contents,
      tools/tool_map consistency).
- [x] Stale bits in `backend/agents/base.py` fixed: header comment now describes
      `run_agent` as the generator it is; unused `tool_history` removed.
- [x] Tool-arg `json.loads` moved inside try in `base.py`; malformed planner args in
      `orchestrator.py` now skip just that agent call instead of aborting the round
- [x] Tool results serialized with `json.dumps` instead of Python repr in `base.py`
- [x] `get_repo_tree` ignored its `branch` param and masked repo-not-found errors
- [x] `tool_call` events fired after tool execution instead of before
- [x] `agent_error_event` had the tool name in the `agent` field
- [x] Broken dead `github_agent.py` deleted
- [x] Unknown agent / missing `query` silently dropped from history (planner loop risk)
- [x] No error containment — stream died silently when Ollama was down
