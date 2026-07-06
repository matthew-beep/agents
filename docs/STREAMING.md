# Streaming Architecture

## Problem

The current orchestrator streams tokens live from the model, then emits a `reset` event if tool calls are detected mid-stream. The frontend discards whatever was partially rendered. This creates an unstable UX — the user sees content appear and disappear.

## Goal

Eliminate `reset`. Give the user continuous, meaningful feedback at every stage without mid-stream corrections.

## Two Paths

```
User Query
    ↓
Orchestrator (non-streaming routing call, tools=TOOLS, think=True)
    ↓
    ├── No tool_calls → stream answer immediately
    │
    └── tool_calls present
            ↓
        Agent execution (base.py — async generator)
        emit: { type: "agent_start", agent: "..." }
        emit: { type: "tool_call", tool: "...", args: {...} }   ← from base.py
        emit: { type: "agent_end", agent: "...", tools: [...] }
            ↓
        Append agent result to messages
            ↓
        Final synthesis (streaming)
        emit: { type: "token", ... }
```

## Event Types

| Event | When | Emitted by | Payload |
|---|---|---|---|
| `agent_start` | Agent begins | orchestrator | `{ agent: string }` |
| `tool_call` | Each tool invocation | base.py | `{ tool: string, args: object, duration_ms: number }` |
| `agent_end` | Agent finishes | orchestrator | `{ agent: string, tools: ToolCall[], duration_ms: number }` |
| `token` | Final synthesis | ollama.py | `{ content: string }` |
| `done` | Stream complete | ollama.py | `{ tokens: number, tokens_per_sec: number, duration_ms: number, total_ms: number }` |

No `reset` event. No `plan` event (deferred — native tool_calls doesn't reliably produce content alongside tool_calls).

## Routing Call

The first LLM call is non-streaming with `tools=TOOLS` and `think=True`. The model reasons through whether tools are needed and which ones to call before anything reaches the frontend.

- `think=True` — routing is real planning work (which agents, what to ask them)
- `tools=TOOLS` — native Ollama tool schema, single source of truth for agent definitions
- Non-streaming — model's full decision is made before any tokens hit the frontend

Branch on `response["message"].get("tool_calls")`:
- Empty → direct path, stream answer
- Present → agentic path, run agents then stream synthesis

## Agent Execution

`base.py` becomes an async generator. It owns its own state and emits `tool_call` events in real time as tools execute. The final yield is an `agent_result` carrying the synthesized content back to the orchestrator.

```
base.py yields:
  tool_call event     ← as each tool fires
  tool_call event
  agent_result        ← final content (not forwarded to frontend)
```

Orchestrator wraps the boundary:

```
emit agent_start
async for event in base.run_agent(...):
    if agent_result: capture content
    else: forward event to frontend
emit agent_end
messages.append({"role": "tool", "content": content})
```

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

| Phase | Tracked on |
|---|---|
| Per-tool call | `tool_call` event — `duration_ms` |
| Per-agent execution | `agent_end` event — `duration_ms` |
| Final synthesis | `done` event — `tokens`, `tokens_per_sec`, `duration_ms` |
| Total end-to-end | `done` event — `total_ms` |

## Backend Changes

**orchestrator.py**

- First LLM call: non-streaming, `tools=TOOLS`, `think=True`
- Branch on `tool_calls` presence — no mode field, no JSON schema
- Direct path: `emit_token_stream()` immediately
- Agentic path: iterate agent generator, forward events, append result, then `emit_token_stream()` for synthesis
- Single `httpx.AsyncClient` for the lifetime of `run()`

**base.py**

- `run_agent()` becomes an async generator
- Yields `tool_call_event` for each tool as it fires (with `duration_ms`)
- Final yield: `{"type": "agent_result", "content": "..."}` — captured by orchestrator, not forwarded

**ollama.py**

- `chat()` already exists — used for the non-streaming routing call
- `emit_token_stream()` already exists — used for direct and synthesis streaming

## Frontend Changes

**page.tsx**

- Add explicit `phase` state: `"idle" | "executing" | "synthesizing"`
- Remove `reset` event handler
- Render based on phase

### Phase Rendering

```
idle         → nothing
executing    → agent activity panel (tool_call events stream in live)
synthesizing → streaming final answer
```

## UX Flow Example

```
User: How does auth work in this repo?

→ [agent activity]
  ◌ Github Agent
    ✓ search_repo()       12ms
    ✓ get_file(auth.ts)   38ms
    ✓ get_file(middleware.ts) 31ms
  ✓ Github Agent (3 tools) — 1.2s

→ [final answer streams]
  Authentication is implemented using JWT cookies...

→ [stats appear after done]
  48 tok/s · 3.4s total
```
