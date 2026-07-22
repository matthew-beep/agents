# GitHub Agent

What `github_agent` can do today, and what's planned next. Companion to
`docs/WEB_AGENT.md` — same idea, one doc per agent, kept current as the tool list
grows instead of letting `docs/AGENTS.md`'s summary table drift out of sync with the
code (which is what happened before this doc existed).

## Current state

**Status:** Built. Registered in `backend/agents/registry.py`; implementation in
`backend/tools/github.py`.

**Purpose** (`SYSTEM_PROMPT`): a GitHub research assistant — fetch real data rather
than guess, never infer or invent file paths/structure, say so explicitly when a
result is truncated.

**Tools:**

| Tool | Signature | Endpoint | Returns |
|---|---|---|---|
| `search_repos` | `(client, query, sort="stars")` | `GET /search/repositories` | Trimmed list: `full_name`, `description`, `stars`, `language`, `topics`, `url` |
| `get_repo` | `(client, owner, repo)` | `GET /repos/{owner}/{repo}` | Raw API response (untrimmed — see Known gap below) |
| `get_repo_tree` | `(client, owner, repo, branch=None)` | `GET /repos/{owner}/{repo}/git/trees/{branch}?recursive=1` | `{truncated, tree}` — nested path tree; resolves `default_branch` via `get_repo` when `branch` is omitted |
| `get_file` | `(client, owner, repo, path)` | `GET /repos/{owner}/{repo}/contents/{path}` | Raw file text (base64-decoded); `path="README.md"` gets the README — there's no separate `get_readme` tool |
| `search_code` | `(client, query, owner=None, repo=None)` | `GET /search/code` | Trimmed list: `path`, `repo`, `url`, `score`. Requires `GITHUB_TOKEN` — unauthenticated calls return `{"error": "...requires authentication..."}` (empirically confirmed: 401, no anonymous fallback) |
| `list_issues` | `(client, owner, repo, state="open")` | `GET /repos/{owner}/{repo}/issues` | Trimmed list: `number`, `title`, `state`, `comments`, `labels`; pull requests filtered out of results |

**Conventions this agent follows** (the general versions are documented in
`docs/REGISTRY.md`'s "Extending" section):

- Every function takes `client: httpx.AsyncClient` as its first argument — no
  function opens its own connection (see the HTTP client threading work in `TODO.md`).
- Expected failures (404s, invalid search syntax) return `{"error": "..."}` so the
  model can recover; only unexpected failures raise, caught by `run_agent`'s per-tool
  `try/except`.
- Per-function timeouts are preserved individually (`search_repos`/`get_file`/
  `search_code`/`list_issues` at 30s, `get_repo`/`get_repo_tree` at 120s) rather than
  collapsing onto one shared value.
- Auth via `GITHUB_TOKEN` env var (optional for read endpoints — unauthenticated
  requests work but hit GitHub's lower rate limit; required for `search_code`, which
  has no anonymous fallback); not yet loaded from `.env` (`docs/TODO.md`).
- The GET → status-check → `raise_for_status()` → `.json()` boilerplate common to
  every tool is centralized in `backend/tools/api.py`'s `get_json()` — a generic,
  GitHub-agnostic helper (no base URL/auth baked in) that each function calls with its
  own `error_map: dict[int, str]` mapping expected status codes to recoverable error
  messages. Available for reuse by future agents (e.g. the planned web agent).

**Known gap:** `get_repo` still returns GitHub's raw ~120-field payload instead of a
trimmed dict like `search_repos` produces. Tracked in `TODO.md`; deliberately not
addressed here since it's a fix to an existing tool, not new capability.

## Planned / future tools

Grouped by what kind of question they answer — not all are equal priority.
`search_code` and `list_issues` have shipped (see Current state above); what's left
below is lower priority.

### Collaboration & activity (the agent has zero visibility into this today)

- **`list_pull_requests(owner, repo, state="open")`** / **`get_pr(owner, repo, number)`**
  — `GET /repos/{owner}/{repo}/pulls` and `.../pulls/{number}`. What's in flight and
  why, not just what the code currently looks like.

### History & versioning

- **`list_commits(owner, repo, path=None)`** / **`get_commit(owner, repo, sha)`** —
  `GET /repos/{owner}/{repo}/commits`. "What changed recently," "who touched this
  file."
- **`get_latest_release(owner, repo)`** — `GET /repos/{owner}/{repo}/releases/latest`.
  "What version should I use," "what's new."

All four of the above follow the exact same shape as `list_issues` — trimmed dict/list
response, `{"error": ...}` on 404, `client` threaded in, one schema entry, one
`TOOL_MAP` entry. No new architectural decision needed to add any of them.

### Explicit fork, not a default: read vs. write

Everything above — current and planned — is read-only, matching the agent's current
framing ("fetch real data... never infer or invent"). GitHub's API also supports
writes: creating issues, posting comments, opening PRs. That's a different trust
posture — the agent taking actions on your behalf rather than only reading — and
should be a deliberate, separately-scoped decision if it's ever wanted, not something
that gets folded in incrementally alongside read tools.

## Recommended build order

1. ~~`search_code` and `list_issues`~~ — done.
2. `list_pull_requests` / `get_pr`, `list_commits`, `get_latest_release` — same shape
   as `list_issues`, add as needed rather than all at once.
