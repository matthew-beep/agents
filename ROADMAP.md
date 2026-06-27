# GitHub Trend Watcher — Roadmap

## Current state

The repo has a minimal scaffold:

- **Backend** (`backend/main.py`): FastAPI app that proxies streaming chat requests to a local Ollama instance. No agent logic, no GitHub tooling.
- **Frontend** (`frontend/app/page.tsx`): Basic chat UI that streams Ollama responses token-by-token. No digest feed, no topic tabs, no cards.

Everything below is not yet built.

---

## Phase 1 — Core agent (backend)

The deterministic loop that fetches trending repos and writes a digest.

- [ ] Restructure backend into `agent/` package
  - `agent/tools/github.py` — `get_trending_repos(language, since)`, `get_readme(owner, repo)`
  - `agent/tools/user_prefs.py` — `get_user_topics(mode)` with modes A / B / C
  - `agent/tools/llm.py` — `summarize_repo(name, description, readme)`, `synthesize_digest(summaries)`
  - `agent/tools/storage.py` — `write_digest(digest)`, `read_digest()`
  - `agent/agent.py` — orchestration loop
  - `agent/config.py` — env-based config (`GITHUB_TOKEN`, `OLLAMA_URL`, `OLLAMA_MODEL`, `SINCE`, `MAX_REPOS`)
- [ ] `run.py` entry point at repo root
- [ ] `.env` + `python-dotenv` wired up
- [ ] `data/` directory with `digest.json` output target
- [ ] `data/user_prefs.json` and `data/topics_from_convos.json` stubs for modes A/B
- [ ] Update `requirements.txt` (`httpx`, `ollama`, `python-dotenv`, `fastapi[standard]`)

**Milestone:** `python run.py` produces a valid `digest.json`.

---

## Phase 2 — Frontend digest feed

Replace the chat UI with a digest reader.

- [ ] `types/digest.ts` — `Repo`, `Topic`, `Digest` types matching `digest.json` shape
- [ ] `app/api/digest/route.ts` — reads `data/digest.json`, returns JSON
- [ ] `components/SynthesisPanel.tsx` — cross-repo patterns banner at top
- [ ] `components/DigestCard.tsx` — single repo card (name, stars, summary, GitHub link)
- [ ] `app/page.tsx` — topic tabs + card list, fetches from `/api/digest`

**Milestone:** `npm run dev` shows a populated digest feed when `digest.json` exists.

---

## Phase 3 — Polish & reliability

- [ ] Error states in the frontend (no digest yet, stale digest warning)
- [ ] Rate-limit handling in `github.py` (respect `Retry-After`, backoff)
- [ ] README trimming + token budget guard in `llm.py` (cap at 3000 chars)
- [ ] Cron job or launchd plist to run `python run.py` nightly
- [ ] `.env.example` documenting all required vars

---

## Phase 4 — LLM-driven loop

The agent decides which repos to dig into rather than processing everything.

- [ ] Model evaluates repo metadata (name, description, stars delta) before fetching README
- [ ] Skip/dig scoring prompt — model returns `{action: "skip" | "dig", reason: string}`
- [ ] `agent.py` branches on score; only fetches READMEs for "dig" repos
- [ ] Log skipped repos + reasons to `data/skipped.json` for inspection

---

## Phase 5 — Persistence & scheduling

- [ ] Swap `digest.json` for Postgres (store digest runs, repo snapshots, summaries)
- [ ] SQLAlchemy models: `DigestRun`, `RepoSummary`
- [ ] Alembic migrations
- [ ] Celery + Celery Beat for nightly scheduled runs
- [ ] Frontend polls for new digests (SSE or short-poll) instead of reading a static file

---

## Phase 6 — Mode A (Virgil integration)

- [ ] Pipeline to pull topics from Virgil conversation history into `data/topics_from_convos.json`
- [ ] Mode A in `user_prefs.py` reads and ranks that list
- [ ] Feedback loop: user marks repos as interesting → influences future topic weights
