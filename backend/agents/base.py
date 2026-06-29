import httpx
import json

OLLAMA_URL = "http://localhost:11434"


# Plain async function — not a generator. Sub-agents don't need to stream to the
# orchestrator; they just need to return their final content and what tools they called.
async def run_agent(
    name: str,
    model: str,
    messages: list[dict],
    tools: list,
    tool_map: dict,
    think: bool,
) -> tuple[str, list[dict]]:
    print(f"[{name}] starting")
    tool_history = []

    while True:
        tool_calls = []
        content_buffer = []

        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream(
                "POST",
                f"{OLLAMA_URL}/api/chat",
                json={"model": model, "messages": messages, "tools": tools, "stream": True, "think": think},
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    msg = chunk.get("message", {})

                    if msg.get("tool_calls"):
                        tool_calls.extend(msg["tool_calls"])
                        # Discard any prose from this pass — the model isn't done yet.
                        content_buffer.clear()
                    else:
                        content_buffer.append(line)

        # No tool calls means this is the final response — collect and return.
        if not tool_calls:
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
            result = await fn(**fn_args) if fn else f"unknown tool: {fn_name}"
            print(f"[{name}] {fn_name} result: {str(result)[:120]}")
            messages.append({"role": "tool", "content": str(result)})
