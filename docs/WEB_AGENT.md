# Web Search Agent

Plan for the second agent: search the web and read real page content, not just
snippets — including following a link found on a fetched page.

## Problem

`docs/AGENTS.md` has flagged a Web Search Agent as "next to build" since early
planning, and the registry refactor (`docs/REGISTRY.md`) was explicitly designed so
this would be a low-friction second agent: one tool module + one registry entry,
nothing else touched. This is also the first real test that the registry pattern
generalizes past the one agent it was built around.

The brief: search the web *and* be able to open a result and read its actual
content — not just snippets — with the ability to follow a link found on a fetched
page ("click further"). Two open design questions had to be resolved before this was
buildable:

- **How does "clicking" work** — a dedicated interactive tool, or something simpler?
- **Dev environment mismatch** — the natural local-only search backend (self-hosted
  SearXNG) is realistic once the server is up, but development is happening on a
  MacBook right now. Building against SearXNG first would block on infra that isn't
  there yet.

## Approach

Resolved in discussion, in order of how much they shape the design:

- **No dedicated "click" tool.** `fetch_page(url)` returns cleaned text plus the links
  found on that page; "clicking" is just the model calling `fetch_page` again on one
  of those URLs. Same shape as `search`/`fetch_page`, no new tool type, no session or
  navigation state to manage.
- **Plain HTTP + extraction for now, not a headless browser.** Playwright would handle
  JS-rendered pages and real click/scroll interaction, but it's real infra (browser
  binaries, heavier runtime, competes for RAM/CPU with local LLM inference per
  `docs/virgil_model_reference_2026.md`'s hardware notes). Reach for it later only if
  JS-walled sites actually become a problem in practice — at that point it doubles as
  the future Frontend Agent's `screenshot()` dependency rather than being paid for
  twice.
- **Brave Search API now, SearXNG later.** `search()`'s signature and return shape
  (`title`, `url`, `snippet`) stay fixed regardless of backend — only the
  implementation inside that one function changes when the server's up and SearXNG is
  realistic. No speculative backend-switching code now; that's a documented future
  swap, not built ahead of need, matching how this codebase already treats
  `GITHUB_TOKEN` (env var in, no fallback abstraction until a second backend
  actually exists).

New `backend/tools/web.py`, following `tools/github.py`'s exact four-piece shape
(system prompt, tool functions, `TOOLS` schemas, `TOOL_MAP`) plus one registry entry —
nothing else in the orchestrator, frontend, or event schema changes, since the
orchestrator already derives its routing tools and prompt directory from the registry.

## Solution

### `search(client, query, count=10)`

Calls Brave's Web Search API (`GET https://api.search.brave.com/res/v1/web/search`,
auth via `X-Subscription-Token` header). Mirrors `tools/github.py`'s `_headers()` /
`os.getenv("GITHUB_TOKEN")` pattern with a new `BRAVE_API_KEY` env var. Returns a
trimmed list — `title`, `url`, `snippet` (Brave's `description` field) — never the raw
API response, matching `search_repos`'s existing convention. Expected-failure paths
(missing/invalid key, rate limit) return `{"error": "..."}` rather than raising, same
as `get_repo`'s 404 handling.

### `fetch_page(client, url)`

Plain `httpx.get(url)`, then extract with **trafilatura** (new dependency) rather than
hand-rolled BeautifulSoup stripping — it's built specifically for clean article-text
extraction and produces meaningfully better output for an LLM to read than naive
tag-stripping. Extract in markdown mode (`output_format="markdown"`,
`include_links=True`) so the returned text keeps inline links the model can act on —
this is what makes "click" work without a separate tool.

Returned shape mirrors `get_repo_tree`'s existing `{"truncated": bool, ...}`
convention (reuse the pattern, don't invent a new one):

```python
{"url": url, "text": "...", "truncated": bool}
```

Cap extracted text at a fixed character budget (~8000 chars, roughly 2000 tokens) to
avoid the exact context-bloat problem already flagged for `get_repo_tree` in
`docs/TODO.md` — a full article can otherwise dominate a sub-agent's context on its
own. `{"error": "..."}` for unreachable URLs / non-HTML content (PDF, images) /
timeouts, not a raised exception.

### `SYSTEM_PROMPT`

Same voice as `github.SYSTEM_PROMPT`: instruct the model to search first rather than
inventing URLs, use `fetch_page` to read real content before answering, cite the URLs
it actually drew from, and treat links found in a fetched page as candidates for a
further `fetch_page` call if the current page doesn't have the answer.

### `backend/agents/registry.py`

One new entry:

```python
"web_agent": AgentConfig(
    name="web_agent",
    description="Search the web and read real page content — use for current events, documentation, or anything outside GitHub.",
    system_prompt=web.SYSTEM_PROMPT,
    tools=web.TOOLS,
    tool_map=web.TOOL_MAP,
),
```

Nothing else changes — `orchestrator.py` derives its routing schema and prompt
directory from the registry already, so `web_agent` becomes callable automatically.

### Dependencies (`backend/requirements.txt`)

Add `trafilatura`. No new dependency needed for `search()` — Brave's API is JSON over
`httpx`, already a dependency.

### `README.md`

Add `BRAVE_API_KEY` alongside the existing `GITHUB_TOKEN` line in "Running it" —
required (not optional like the GitHub token) since `search()` has no unauthenticated
fallback. Note in the architecture section that a second agent now exists, proving the
registry pattern generalizes.

### Tests

No dedicated `test_web.py` — matches current project convention (`tools/github.py` has
no unit tests either; HTTP-calling tool functions are verified live, not mocked).
`backend/tests/test_registry.py`'s existing checks (schema shape, directory contents,
tools/tool_map consistency) automatically cover `web_agent` once it's registered — no
test file changes needed, just confirm the suite still passes with the new entry.

### Verification

1. `export BRAVE_API_KEY=...` (free-tier key from Brave's API dashboard).
2. `cd backend && .venv/bin/python -m pytest -q` — all existing + registry tests
   green with `web_agent` now in `AGENTS`.
3. Static check:
   `.venv/bin/python -c "from agents import registry; print(registry.orchestrator_tools())"`
   — confirms `web_agent` appears alongside `github_agent`.
4. Live end-to-end (needs Ollama + `BRAVE_API_KEY` running): start the backend, then

   ```sh
   curl -N localhost:8000/generate -H 'content-type: application/json' \
     -d '{"model": "<local model>", "messages": [{"role": "user", "content": "what does the latest Next.js release notes say about caching?"}], "think": false}'
   ```

   and confirm NDJSON shows routing → `agent_start: web_agent` → `tool_call: search` →
   `tool_call: fetch_page` (possibly more than one, if the model follows a link) →
   `agent_end` → `token`s → `done`.
5. Sanity-check `fetch_page` truncation: fetch a known long article and confirm
   `truncated: true` at the ~8000-char cap.
