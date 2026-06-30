# Streaming Architecture

## Problem

The current orchestrator streams tokens live from the model, then emits a `reset` event if tool calls are detected mid-stream. The frontend discards whatever was partially rendered. This creates an unstable UX — the user sees content appear and disappear.

## Goal

Eliminate `reset`. Give the user continuous, meaningful feedback at every stage without mid-stream corrections.

## Two Paths

```
User Query
    ↓
Orchestrator (non-streaming routing call)
    ↓
    ├── Direct → stream answer immediately
    │
    └── Agentic
            ↓
        emit: { type: "plan", content: "..." }
            ↓
        Agent execution
        emit: { type: "agent_start", agent: "..." }
        emit: { type: "tool_call", tool: "..." }
        emit: { type: "agent_end", agent: "...", tools: [...] }
            ↓
        Final synthesis (streaming)
        emit: { type: "token", ... }
```

## Event Types

| Event | When | Payload |
|---|---|---|
| `plan` | Before agent execution | `{ content: string }` |
| `agent_start` | Agent begins | `{ agent: string }` |
| `tool_call` | Each tool invocation | `{ tool: string, args: object }` |
| `agent_end` | Agent finishes | `{ agent: string, tools: ToolCall[], duration_ms: number }` |
| `token` | Final synthesis | `{ content: string }` |
| `done` | Stream complete | `{ tokens: number, tokens_per_sec: number, duration_ms: number }` |

No `reset` event.

## Timing and Performance

Ollama returns token counts and durations in the final chunk of each response:

```json
{
  "eval_count": 128,
  "eval_duration": 4200000000,
  "prompt_eval_count": 42,
  "prompt_eval_duration": 800000000
}
```

`tokens/sec = eval_count / (eval_duration / 1e9)`

The backend tracks wall-clock time for each phase and attaches it to the relevant event:

| Phase | Tracked on |
|---|---|
| Planning pass | `plan` event — `duration_ms` |
| Per-agent execution | `agent_end` event — `duration_ms` |
| Per-tool call | `tool_call` event — `duration_ms` |
| Final synthesis | `done` event — `tokens`, `tokens_per_sec`, `duration_ms` |
| Total end-to-end | `done` event — `total_ms` |

## Backend Changes

**orchestrator.py**

- First LLM call is non-streaming — used only to detect whether tool calls are needed
- If no tool calls: switch to streaming, yield tokens directly (direct path)
- If tool calls: emit `plan`, run agents, then make a final streaming LLM call for synthesis

## Frontend Changes

**page.tsx**

- Add explicit `phase` state: `"idle" | "planning" | "executing" | "synthesizing"`
- Add `plan` string state for the intent statement
- Render based on phase rather than inferring from which state vars are populated
- Remove `reset` event handler

### Phase Rendering

```
idle        → nothing
planning    → plan text (stable, no streaming cursor)
executing   → agent activity panel
synthesizing → streaming final answer
```

## UX Flow Example

```
User: How does auth work in this repo?

→ [plan appears instantly]
  "I'll inspect the repository structure and trace the authentication flow."

→ [agent activity]
  ◌ Github Agent
    ✓ search_repo()
    ✓ get_file(auth.ts)
    ✓ get_file(middleware.ts)
  ✓ Github Agent (3 tools)

→ [final answer streams]
  Authentication is implemented using JWT cookies...

→ [stats appear after done]
  48 tok/s · 3.4s
```

### Timing Display

Stats are shown inline — attached to the agent panel and the final answer bubble:

```
✓ Github Agent (3 tools) — 1.2s
  ✓ search_repo()         12ms
  ✓ get_file(auth.ts)     38ms
  ✓ get_file(middleware.ts) 31ms

Authentication is implemented using...    48 tok/s · 3.4s total
```
