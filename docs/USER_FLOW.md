# Approaches to User Flow

Notes on candidate shapes for the frontend's user flow, written after reviewing the
design exploration already done in the "Virgil agent management interface" Claude
Design project (`Virgil Persona Flows`, `Virgil Chat Flow`, `Virgil Dashboard`,
`Virgil Flow Screens`, `Virgil Mission Control`, `Virgil Projects`, `Virgil
Wireframes`, `Virgil Wireframes v2`). This is a survey, not a decision — nothing here
is committed to. Companion to the visual designs themselves, which are the source of
truth for what each screen actually looks like; this doc is about the underlying
*mental model* each one assumes.

## Why this doc

The current built UI (per `docs/AGENTS.md`'s Design Brief) is a basic chat with an
agent activity panel — functional, unstyled, and hasn't committed to a broader
information architecture yet. The design project already contains eight explorations
of what the fuller product could look like. Rather than pick one by feel, it's worth
naming the actual philosophical differences between them, since several of them
aren't just visual variations — they imply different answers to "what is the unit of
the product" and "what does the user look at by default."

## Two philosophies, one emerging hybrid

### 1. Project-as-guided-workflow

The unit of the product is a **single project** moving through a phase pipeline —
Research → Planning → Design → Development — with a persistent phase checklist and
explicit approval gates between phases (the agent proposes, the user approves or
redirects, the agent proceeds). This is the dominant model across most of the design
project: `Persona Flows`, `Flow Screens` (a more polished, isolated pass on the exact
same pipeline), `Dashboard` (a hybrid that adds a permanent agent-monitoring grid
alongside the phase view), `Chat Flow` (the same model with everything — plans, tool
calls, artifacts — rendered as cards inline in one scrolling chat timeline, no
separate views at all), and most of `Projects`' six variations.

`Projects.dc.html` is worth calling out specifically: it's an explicit bake-off of
*presentation* choices within this same philosophy — chat-centric (persistent chat
alongside an overview), document-centric (the research doc itself is the main pane,
chat demoted to a tab, Virgil leaves inline margin comments), history-centric (a
vertical run-by-run audit trail is the primary view), and editor-centric (a
Google-Docs-style plan document with a phase-pill breadcrumb, no sidebar at all). Four
different answers to "what's the main pane," same underlying phase-pipeline model
underneath.

This philosophy matches where `docs/ROADMAP.md`'s "Future — Project builder mode"
section already pointed: "the conversation *is* the planning artifact, and the output
is a project, not an answer" — stateful, multi-turn, plan-then-execute. It's also the
closest match to the currently-built chat + agent-activity-panel UI, just with phases
and approval gates layered on top of what already exists.

### 2. Fleet / ops monitoring

The unit of the product is **the system as a whole** — potentially many concurrent
agents and runs across many projects — and the UI's job is triage and oversight, not
walking one project through phases. `Wireframes` (the roughest, earliest pass — three
distinct navigational metaphors tested side by side: a persistent sidebar rail, a
literal node-and-arrow DAG/pipeline diagram as the primary view, and a card-grid
"command center") and `Wireframes v2` (consolidated on the grid: global GPU/CPU/RAM
meters, a grid of agent cards with progress bars, an expandable live-log drawer, an
"Agent Roster" screen, a "Run History" audit table) both frame this as a literal ops
console — closer to an admin dashboard for a fleet of agents than a guided project
experience. `Mission Control`'s first screen (an attention-triage inbox — "Needs you /
Running now / Done while you were away" — as the *landing screen*, replacing a project
list) is a softer, more consumer-facing take on the same instinct: surface what needs
you across everything, rather than making you navigate into a project to find out.

This philosophy answers a real question the guided-workflow model doesn't: once
there's more than one project or more than one agent running concurrently, where do
you look first? None of the guided-workflow mockups have an answer for that — they all
assume you're already inside a project.

### 3. Unified timeline (emerging, not yet a full direction)

`Mission Control`'s second screen and `Chat Flow` both reach for something structurally
different from either philosophy above: chat messages, run cards, and artifact/diff
cards merged into **one interleaved chronological feed**, instead of chat, logs, and
files being separate surfaces you switch between. This is a smaller, more specific
idea than the two philosophies — it's about *how activity is rendered* more than
*what the product's home screen is* — but it cuts across both: you could build a
guided-workflow product or an ops-monitoring product and still choose interleaved-feed
vs. separate-panes as the rendering choice within it.

## Open questions this doc deliberately leaves open

- Is the product single-project-at-a-time (guided workflow) or multi-project-aware by
  default (fleet monitoring)? This is the biggest fork — it changes what the landing
  screen is.
- If multi-project, does oversight look like `Mission Control`'s attention-triage inbox
  or `Wireframes v2`'s literal ops-console grid? Those read as different target users
  (a person managing a few projects vs. someone operating many agents).
- Within guided-workflow, which of `Projects.dc.html`'s four presentation variants
  (chat / document / history / editor as the main pane) fits how a user actually wants
  to review Virgil's work — this probably depends on the phase (e.g. document-centric
  for reviewing a research doc, chat-centric for steering active development).
- Does the interleaved-timeline rendering idea (chat + runs + artifacts as one feed)
  get adopted regardless of which philosophy wins, or is it specific to one of them?
- The currently-built UI (chat + agent activity panel) is closest to `Chat Flow`'s
  pure-chat-timeline take on guided-workflow — worth deciding whether that's the
  intended direction or just where things happened to start.
