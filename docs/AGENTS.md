# Agents

## Project

This project is pivoting from the original Virgil vision (background push intelligence) to focus first on an interactive multi-agent workflow system. The core idea: a chat interface backed by an orchestrator that routes queries to specialist sub-agents, each with their own tool loop, and streams structured activity back to the user in real time.

The streaming architecture (see STREAMING.md) is the foundation. Agents plug into it as execution units — the orchestrator decides which ones to invoke, runs them, and synthesizes their output into a final streamed response.

---

## Claude Design Brief

**Project:** Virgil — Multi-Agent Workflow System

**What it is:** An interactive multi-agent AI system running on local hardware. A chat interface backed by an orchestrator that routes queries to specialist agents — each with their own tools and reasoning loop. The user sees the system's activity in real time: what agents are running, what tools they're calling, how long each step takes.

**Stack:** FastAPI + Ollama backend, Next.js 15 frontend. All local, no cloud dependencies.

**Design system:** "Structural Glass" — dark base, monochrome with a single blue accent (`#0070f3`), Inter + JetBrains Mono, Apple-level restraint. Typography carries hierarchy; color only when it communicates meaning. Think visionOS meets Swiss editorial.

**Current UI:** Basic chat with agent activity panel (agent name, tool calls, expand/collapse). Functional but unstyled.

**What needs designing:** The agent activity panel and performance stats display — how tool calls, timing (`48 tok/s · 3.4s`), and agent state (running / done) look within the chat flow. Also the overall chat shell: message bubbles, plan statement display, and the input area.

---

## Agent Registry

### 1. GitHub Agent
**Status:** Built

**Purpose:** Fetch live data from GitHub — repos, file trees, file contents, READMEs.

**Tools:**
- `search_repos(query, sort)` — GitHub search API
- `get_repo_tree(owner, repo)` — full file path list
- `get_file(owner, repo, path)` — raw file content
- `get_readme(owner, repo)` — README text

**Example triggers:**
- "What files are in owner/repo?"
- "How does auth work in this codebase?"
- "Find repos related to X"

---

### 2. Web Search Agent
**Status:** Planned — next to build

**Purpose:** Search the web and return synthesized results. Feeds into other agents (frontend agent uses it for research, discovery agent uses it for trend monitoring).

**Tools:**
- `search(query)` — SearXNG (self-hosted)
- `fetch_page(url)` — Crawl4AI for clean text extraction
- `summarize(content)` — internal LLM step

**Example triggers:**
- "What's the latest on X?"
- "Find documentation for Y"
- "Research competitors for Z"

---

### 3. Frontend Agent
**Status:** Planned

**Purpose:** End-to-end frontend generation. Takes a goal, researches references, captures visuals, generates assets, writes code, and self-evaluates via a vision model feedback loop.

**Tools:**
- `search(query)` — web search for references and inspiration (via Web Search Agent)
- `screenshot(url)` — Playwright headless browser capture
- `describe_image(image)` — vision model (Qwen2-VL or LLaVA) to extract layout, palette, component structure
- `generate_image(prompt)` — FLUX.1 for hero images, icons, assets
- `generate_code(prompt, context)` — Qwen2.5-Coder
- `render_preview(code)` — headless render of generated output
- `evaluate(reference, output)` — vision model diff: "does this match the reference?"

**Loop:**
```
Goal
  ↓
Research → screenshot reference sites
  ↓
Vision model: describe layout + components
  ↓
Generate code (informed by description)
  ↓
Render output → screenshot
  ↓
Vision model: evaluate against reference
  ↓
Iterate or done
```

**Example triggers:**
- "Build a landing page for X"
- "Recreate this layout"
- "Generate a component that looks like Y"
