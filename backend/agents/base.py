import httpx
import json
from agents import ollama, events
from collections.abc import AsyncIterator

# Plain async function — not a generator. Sub-agents don't need to stream to the
# orchestrator; they just need to return their final content and what tools they called.
async def run_agent(
    name: str,
    model: str,
    messages: list[dict],
    tools: list,
    tool_map: dict,
    think: bool,
) -> AsyncIterator[dict]:

    print(f"[{name}] starting")
    tool_history = []
    async with httpx.AsyncClient(timeout=300.0) as client:
        while True:
            tool_calls = []


            resp = await ollama.chat(client, model, messages, think=think, tools=tools)
            msg = resp.get("message", {})
            # No tool calls means this is the final response — collect and return.
            if not msg.get("tool_calls"):
                content = "".join(
                    json.loads(line).get("message", {}).get("content", "")
                    for line in content_buffer
                )
                print(f"[{name}] done")
                return content, tool_history

            print(f"[{name}] tool calls: {[tc['function']['name'] for tc in tool_calls]}")

            messages.append({"role": "assistant", "tool_calls": tool_calls})
            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                fn_args = tc["function"]["arguments"]
                # Record before executing so the orchestrator can surface this to the frontend.
                tool_history.append({"tool": fn_name, "args": fn_args})
                print(f"[{name}] calling {fn_name} with {fn_args}")
                fn = tool_map.get(fn_name)

                yield events.emit(events.tool_call_event(fn_name, fn_args))

                result = await fn(**fn_args) if fn else f"unknown tool: {fn_name}"
                print(f"[{name}] {fn_name} result: {str(result)[:120]}")
                messages.append({"role": "tool", "content": str(result)})
