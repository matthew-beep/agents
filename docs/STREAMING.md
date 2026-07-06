# Streaming Architecture

## Problem

Two distinct issues, one fix.

1. The original orchestrator streamed tokens live from the model, then emitted a `reset` event if tool calls were detected mid-stream. The frontend discarded whatever was partially rendered — unstable UX, content appearing and disappearing.
2. Separately: Ollama's `stream: true` + `tools` combo is unreliable at the serving layer — reports of buffered (non-incremental) output and, in some cases, silently dropped tool calls when both are enabled together. This isn't model-specific; it affects any model served through Ollama with tools + streaming combined.

## Goal

Eliminate `reset` and the conditions that caused it, as hard rules at the serving-call level:

1. Every call that has `tools` attached is non-streaming (`stream: false`). Not an optimization — a correctness rule, because of the Ollama bug above.
2. Exactly one call per `run()` ever streams: the final synthesis call, made only once `tools` is stripped (`tools: null`) — a call that is structurally incapable of requesting a tool.
3. The tool-gathering phase loops until the model stops requesting tools or `MAX_ROUNDS` is hit. One round is not assumed sufficient — the continuation decision is made by the model itself on each call, not by a separate classifier.

## Decisions

### No `plan` event

We considered deriving a "plan" sentence from `message.thinking` (via `think: true` on the routing call). Verified live against `qwen3.5:9b`: `message.content` is always `""` when `tool_calls` is present, but `message.thinking` reliably contains real prose describing intent. It works technically — but we're not building it. The plan text isn't actionable by the user (no approve/deny, nothing to click), so it doesn't earn the complexity of parsing and cleaning raw chain-of-thought output for display. `think` is dropped entirely from the routing call as a result — there's no reason to pay for it if nothing consumes the output.

### `thinking` event (spinner only)

A content-free status signal — `{"type": "thinking"}` — emitted exactly once, immediately before the first non-streaming routing call in `run()`. Purpose: give the frontend something to render (a spinner) before any other event exists, since that first call has non-trivial latency. It does not re-fire between tool rounds. The frontend clears it the moment the first `agent_start` or `token` event arrives.

### Round loop, not a classifier

Every `tools`-attached call happens inside a `while True` loop bounded by `MAX_ROUNDS`, re-invoked with growing `messages` context each time. `resp.tool_calls` truthiness on that call *is* the continuation decision — there's no `{"mode": "direct" | "agentic"}` JSON-mode classifier making that call separately. The old `PLANNER_SYSTEM_PROMPT` approach is dead and should be deleted, not reused, when this is implemented.

## Core Loop

```python
async def run(messages):
    round = 0
    tools = TOOLS

    yield events.thinking_event()  # once, before anything else exists

    while True:
        resp = await ollama.chat(messages, tools=tools, think=False, stream=False)

        if not resp.tool_calls:
            break

        round += 1
        if round > MAX_ROUNDS:
            tools = None  # force-terminate: next call structurally cannot request a tool
            break

        for call in resp.tool_calls:
            yield events.agent_start_event(call.name)
            start = now()
            result_content, tool_history = None, []

            try:
                async for ev in run_agent(call):
                    if ev["type"] == "tool_call":
                        yield events.emit(ev)
                        tool_history.append(ev)
                    elif ev["type"] == "agent_result":
                        result_content = ev["content"]
                    elif ev["type"] == "agent_error":
                        yield events.emit(ev)
            except Exception as e:
                # run_agent should not raise — see Error Handling — but don't let a
                # bug there take down the whole run() if it does.
                yield events.agent_error_event(call.name, str(e))
                result_content = f"Tool failed: {e}"

            yield events.agent_end_event(call.name, tool_history, duration_ms=now() - start)
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result_content})

    # only call that streams — tools stripped, model cannot request one
    async for line in ollama.emit_token_stream(messages, tools=None, stream=True):
        yield line
```

**Direct path** (no tools ever needed): `thinking` → one non-streaming routing call → straight to the final streaming call. **Agentic path**: `thinking` → N non-streaming rounds (bounded by `MAX_ROUNDS`) → one streaming call. No `reset`, ever — the only call that streams to the user is the one where the model has no mechanism to request a tool mid-generation.

## `base.py` — `run_agent` as a generator

Current bug: `run_agent()` calls Ollama with `tools` **and** `stream: True` together — the exact combination banned everywhere else, and the one directly implicated in Ollama's serving-layer reliability issues. It happens to not leak partial content to the frontend today (the function isn't a generator, so nothing is forwarded live), but the underlying reliability risk — buffered or dropped `tool_calls` — is exactly what this doc exists to eliminate, and it doesn't matter whether the *frontend* sees the corruption if the *tool call itself* gets dropped.

Fix: convert `run_agent` into an async generator whose internal tool-calling loop is entirely non-streaming, yielding `tool_call` live as each tool actually fires (not after the whole agent resolves), and a final `agent_result` yield the orchestrator captures (not forwarded to the frontend):

```python
async def run_agent(call):
    messages = [agent_system_prompt, {"role": "user", "content": call.args["query"]}]
    inner_round = 0

    while True:
        resp = await ollama.chat(messages, tools=AGENT_TOOLS, think=False, stream=False)

        if not resp.tool_calls:
            yield {"type": "agent_result", "content": resp.content}
            return

        inner_round += 1
        if inner_round > AGENT_MAX_ROUNDS:
            yield {"type": "agent_result", "content": resp.content or "Gave up after too many tool rounds."}
            return

        messages.append({"role": "assistant", "tool_calls": resp.tool_calls})
        for tc in resp.tool_calls:
            start = now()
            try:
                result = await TOOL_MAP[tc.name](**tc.args)
            except Exception as e:
                yield {"type": "agent_error", "agent": tc.name, "error": str(e)}
                result = f"Tool failed: {e}"
            yield {"type": "tool_call", "tool": tc.name, "args": tc.args, "duration_ms": now() - start}
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": str(result)})
```

Every call inside this loop is non-streaming — no exception. `AGENT_MAX_ROUNDS` can share the outer `MAX_ROUNDS` constant or be its own (smaller) cap; either way, a single agent cannot loop unbounded independent of the orchestrator's own cap.

## Error Handling

Tool invocation (`TOOL_MAP[tc.name](**tc.args)`) is wrapped in try/except inside `run_agent`'s loop:

- On failure, yield `{"type": "agent_error", "agent": str, "error": str}` — kept minimal, no `agent_id` (see Deferred).
- Feed `"Tool failed: {error}"` back into `messages` as the tool result, so the loop continues and the model can route around the failure (retry, different tool, or answer without it) on the next round.
- Do not abort `run()` on a single tool failure.

## Event Schema

| Event | When | Payload |
|---|---|---|
| `thinking` | Once, before the first routing call | `{}` |
| `agent_start` | Agent begins | `{ agent: string }` |
| `tool_call` | Each tool invocation, live from inside `run_agent` | `{ tool: string, args: object, duration_ms: number }` |
| `agent_end` | Agent finishes | `{ agent: string, tools: ToolCall[], duration_ms: number }` |
| `agent_error` | A tool call fails | `{ agent: string, error: string }` |
| `token` | Final synthesis | `{ content: string }` |
| `done` | Stream complete | `{ tokens: number, tokens_per_sec: number, duration_ms: number, total_ms: number }` |

No `plan`. No `mode`. No `reset`.

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
| Total end-to-end | `done` event — `total_ms` (computed backend-side, not reconstructed by the frontend) |

## Backend Changes

**`orchestrator.py`**
- Replace the routing call with the `run()` loop above.
- Every call that includes `tools` is non-streaming.
- Only the final call, made once `tools: null`, is streaming.
- Track `round`, enforce `MAX_ROUNDS`.
- Delete `PLANNER_SYSTEM_PROMPT` and the JSON-mode `{"mode": ...}` classifier — dead code, superseded by branching on `resp.tool_calls`.

**`base.py`**
- `run_agent()` becomes an async generator per the section above.
- Its own tool-calling loop is non-streaming throughout; it has its own round cap.
- Emits `tool_call` live and a final `agent_result` (captured by the orchestrator, not forwarded).

**`ollama.py`**
- `chat()` — non-streaming, used for every `tools`-attached call.
- `emit_token_stream()` — streaming, used only for the final synthesis call (`tools=None`).

**`events.py`**
- Add `thinking_event()` and `agent_error_event()`.
- Remove `PlanEvent` / `plan_event()`.
- Wire up `duration_ms` at every call site that currently leaves it unset (`agent_end`, `tool_call`).

## Frontend Changes

**`page.tsx`**
- `phase`: `"idle" | "executing" | "synthesizing"` — no `"planning"` phase.
- `thinking` is a spinner sub-state within `idle` (shown once, cleared on the first `agent_start` or `token`), not a phase transition of its own.
- Agent activity panel renders live from `agent_start` / `tool_call` / `agent_end` as they arrive.
- Handle `agent_error`: mark the relevant agent's panel as failed rather than falling through to the unhandled-event branch.
- Remove `plan` state, the `PlanEvent` type, and any leftover `reset` handling.
- Render based on `phase` rather than inferring it from which state vars are populated.

### Phase Rendering

```
idle (thinking spinner) → nothing but a spinner, cleared on first agent_start/token
executing               → agent activity panel(s), live tool_call/agent_start/agent_end
synthesizing            → streaming final answer
```

## Deferred (considered, intentionally scoped out)

- **`agent_id` on events.** There is currently exactly one agent (`github_agent`) and no concurrent dispatch — agents execute sequentially within a round, so the `agent` name alone is an unambiguous key today. Add `agent_id` when a second concurrent agent path actually exists, not preemptively.
- **Multi-agent concurrency.** Same reasoning as above — nothing in the current design dispatches agents in parallel within a round.
- **Reconnection / durability** (Celery worker, Redis pub/sub, a durable event log, `GET /stream/{run_id}`, `GET /conversations/{id}/active_run`). A real need for surviving a page refresh mid-stream, but `/generate` currently runs `run()` synchronously inside the FastAPI request handler. This is a separate infrastructure project, not a change to `run()`'s internal logic — scope it once the rest of this doc is actually implemented.

These are noted here so they're visible as intentional scope decisions, not gaps nobody noticed.
