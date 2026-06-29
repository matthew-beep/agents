# TODO

## Tool call streaming + history (high priority)

Buffer prose in `base.py`, stream typed tool events to the frontend, flush final response live. Gives responsive UX, no duplicated answers, and a foundation for tool history.

**Approach:**
- `base.py` — buffer content chunks, yield `{"type": "tool_call", "tool": fn_name, "args": fn_args}` and `{"type": "tool_result", "tool": fn_name}` around each tool execution. On final pass (no tool calls), flush buffer live.
- `orchestrator.py` — own run loop instead of using `base.py`'s `run_agent`, so it can iterate sub-agent stream directly, forward `type` chunks upstream, and collect content into the tool result string.
- Frontend — `type: tool_call` → add to tool history panel. `type: tool_result` → mark done. No `type` → stream into message bubble.

**Why:** Model sometimes starts responding mid-tool-loop causing duplicate/partial answers. Tool history lets users audit what the agent actually did.

---

## Filter binary files from get_repo_tree

Add `BINARY_EXTENSIONS` set in `tools/github.py` and skip those paths in `_build_tree`. Repos with large example image folders (e.g. `example/courthouse/000000.png x286`) bloat the tree and slow down Ollama's context processing.

---

## .env + GITHUB_TOKEN

Add `python-dotenv` to `requirements.txt`, load `.env` in `tools/github.py`. Bumps GitHub API rate limit from 10 to 30 req/min — needed for multi-repo research queries.
