# TODO

Backend review pass — 2026-07-07. Ordered by priority.

## Quality

- [ ] **Trim `get_repo` response** — `backend/tools/github.py`. Returns the raw
      GitHub payload (~120 fields) straight into the sub-agent's context. Trim to
      `full_name`, `description`, `default_branch`, `stargazers_count`, `language`,
      `topics` — like `search_repos` already does.

## Housekeeping

- [ ] **Dead code in `backend/agents/orchestrator.py`**: planning-notes docstring
      (lines 34-58), `PLANNER_SYSTEM_PROMPT`, commented-out planner line (78), stray
      `"""need to implement..."""` string inside `run()` (81-83), unused `OLLAMA_URL` (6).
      Deferred out of the registry-refactor pass — see `docs/REGISTRY.md`.
- [ ] **Decide on `plan_event` vs `thinking_event`**: original plan called for
      renaming; if the frontend renders `plan` fine, keep the name and drop the
      plan item instead.

## Minor / fine to ignore

- [ ] Three layers of `httpx.AsyncClient` per request (orchestrator → `run_agent` →
      each github tool). Pass the orchestrator's client down to reuse connections.
- [ ] `base.py:48` drops any assistant `content` emitted alongside tool calls, and
      tool-result messages omit `tool_name` (used by models to match results to
      calls when one round has multiple).
- [ ] `AGENT_MAX_ROUNDS` cutoff feeds the literal string "max rounds reached" into
      the final answer; use something like "stopped after N rounds; partial results
      above".

## Done (from earlier passes)

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
