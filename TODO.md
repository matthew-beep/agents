# TODO

## Live streaming of final response (orchestrator)

The orchestrator currently buffers the entire final response before yielding it — it collects into `content_buffer` and then does `for line in content_buffer: yield line + "\n"` after the stream closes. This means the user sees nothing until Ollama finishes generating.

**Fix:**
- Inside the `async for line in resp.aiter_lines()` loop, yield content chunks immediately when there are no tool calls in the current chunk.
- Problem: we don't know if a tool-call chunk is coming later in the same pass. Ollama sends tool calls as a single chunk, so if content has already been yielded and then a tool-call chunk arrives, the frontend has stale partial content.
- Solution: emit `{"type": "reset"}` before any `agent_start` event. The frontend discards `streamingContent` on receipt. This lets us stream content live and still handle the tool-call-after-content case cleanly.

**Frontend change needed:** handle `data.type === "reset"` by setting `streamingContent` and `streamingThink` back to `""`.

---

## Filter binary files from get_repo_tree

Add `BINARY_EXTENSIONS` set in `tools/github.py` and skip those paths in `_build_tree`. Repos with large example image folders (e.g. `example/courthouse/000000.png x286`) bloat the tree and slow down Ollama's context processing.

---

## .env + GITHUB_TOKEN

Add `python-dotenv` to `requirements.txt`, load `.env` in `tools/github.py`. Bumps GitHub API rate limit from 10 to 30 req/min — needed for multi-repo research queries.

---

## Done

### Agent activity panel ✓
- `base.py` — plain `async def run_agent(...)` returning `tuple[str, list[dict]]`. Accumulates `tool_history` across loop iterations.
- `github_agent.py` — drops the generator, returns `await run_agent(...)` directly.
- `orchestrator.py` — owns the Ollama loop. Yields `{"type": "agent_start"}` before each sub-agent call, `{"type": "agent_end", "tools": tool_history}` after. Sub-agents are fire-and-collect.
- Frontend — `AgentActivity[]` state. `agent_start` pushes a running entry; `agent_end` marks it done and attaches tools. Panel shows `GitHub Agent ✓ (2 tools)` with click-to-expand tool list. Trace persists on the message after streaming ends.
