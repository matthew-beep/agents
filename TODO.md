# TODO

Backend review pass — 2026-07-07. Ordered by priority.

## Correctness

- [ ] **Move tool-arg `json.loads` inside the try block** — `backend/agents/base.py:52-53`.
      Malformed JSON arguments from the model raise before the try, unwind `run_agent`
      entirely, and kill the whole sub-agent run over one bad tool call. Should degrade
      to a per-tool error like other tool failures. Same unguarded pattern in
      `backend/agents/orchestrator.py:114-115` (blast radius caught by outer try, but
      still turns one bad arg into a dead round).

## Quality

- [ ] **Serialize tool results as JSON, not Python repr** — `backend/agents/base.py:67`.
      `str(result)` gives single quotes / `None` / `True`; models parse JSON more
      reliably. Use `json.dumps(result) if not isinstance(result, str) else result`.
      Same for the tool-result append in `orchestrator.py`.
- [ ] **Trim `get_repo` response** — `backend/tools/github.py`. Returns the raw
      GitHub payload (~120 fields) straight into the sub-agent's context. Trim to
      `full_name`, `description`, `default_branch`, `stargazers_count`, `language`,
      `topics` — like `search_repos` already does.

## Housekeeping

- [ ] **Dead code in `backend/agents/orchestrator.py`**: planning-notes docstring
      (lines 34-58), `PLANNER_SYSTEM_PROMPT`, commented-out planner line (78), stray
      `"""need to implement..."""` string inside `run()` (81-83), unused `OLLAMA_URL` (6).
- [ ] **Stale bits in `backend/agents/base.py`**: header comment says "Plain async
      function — not a generator" (it is a generator now); `tool_history` (line 23)
      is unused.
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

- [x] `get_repo_tree` ignored its `branch` param and masked repo-not-found errors
- [x] `tool_call` events fired after tool execution instead of before
- [x] `agent_error_event` had the tool name in the `agent` field
- [x] Broken dead `github_agent.py` deleted
- [x] Unknown agent / missing `query` silently dropped from history (planner loop risk)
- [x] No error containment — stream died silently when Ollama was down
