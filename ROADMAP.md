# Agent Chat — Roadmap

## Current state

- **Backend** (`backend/main.py`): FastAPI app proxying to local Ollama. System prompt tells the model it has access to agents and how to signal a call via JSON. Routing detection logs agent calls to console but doesn't execute anything yet.
- **Frontend** (`frontend/app/page.tsx`): Chat UI with message bubbles, markdown rendering via `react-markdown` + `remark-gfm`, think bubble that disappears once content starts streaming.

---

## Phase 1 — GitHub agent

Wire up the first real agent so the routing detection actually does something.

- [ ] `backend/agents/github_agent.py` — agent entry point, owns its own system prompt and tool loop
- [ ] `backend/tools/github.py` — tool functions + schemas
  - `search_repos(query, sort)` → list of repos from GitHub search API
  - `get_repo_tree(owner, repo)` → all file paths
  - `get_file(owner, repo, path)` → raw file content
  - `get_readme(owner, repo)` → raw README text
- [ ] `AGENT_MAP` in `main.py` — maps agent name strings to agent functions
- [ ] Execute the agent in the routing block and stream its response back
- [ ] `.env` + `python-dotenv` for `GITHUB_TOKEN`

**Milestone:** "what files are in owner/repo?" triggers the github agent, fetches the tree, and streams a real answer.

---

## Phase 2 — Frontend status indicator

The blocking routing call + agent execution creates a silent gap. Make it visible.

- [ ] Backend sends a `{"type": "status", "message": "..."}` chunk before running the agent
- [ ] Frontend detects `type: "status"` chunks and shows a status line below the last message
- [ ] Status line disappears once content starts streaming

---

## Phase 3 — Multi-agent foundation

Make it easy to add new agents without touching `main.py`.

- [ ] Each agent is a self-contained module: system prompt, tools, and tool loop in one place
- [ ] Auto-discovery or explicit registry so adding an agent is just adding a file + one entry
- [ ] Add a second agent (e.g. general web search or a local file reader) to prove the pattern works

---

## Phase 4 — GitHub Trend Watcher (digest mode)

The original concept — a scheduled agent that surfaces trending repos.

- [ ] `backend/agents/trend_agent.py` — fetches trending repos by topic, summarizes with LLM, writes digest
- [ ] `data/digest.json` output
- [ ] `run.py` entry point to trigger manually
- [ ] `data/user_prefs.json` for topic preferences
- [ ] Cron job or launchd plist for nightly runs

**Milestone:** `python run.py` produces a valid `digest.json`.

---

## Phase 5 — Digest frontend

- [ ] `app/digest/page.tsx` — separate route from the chat UI
- [ ] `app/api/digest/route.ts` — reads `data/digest.json`
- [ ] `components/DigestCard.tsx` — repo card (name, stars, summary, link)
- [ ] `components/SynthesisPanel.tsx` — cross-repo patterns banner

---

## Phase 6 — Persistence & scheduling

- [ ] Swap `digest.json` for Postgres
- [ ] SQLAlchemy models: `DigestRun`, `RepoSummary`
- [ ] Alembic migrations
- [ ] Celery Beat for scheduled runs
- [ ] Frontend polls for new digests instead of reading a static file
