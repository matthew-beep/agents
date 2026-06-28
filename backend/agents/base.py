import httpx
import json

OLLAMA_URL = "http://localhost:11434"


async def run_agent(name: str, model: str, messages: list[dict], tools: list, tool_map: dict, think: bool):
    print(f"[{name}] starting")

    while True:
        tool_calls = []

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
                    else:
                        yield line + "\n"

        if not tool_calls:
            print(f"[{name}] done")
            break

        print(f"[{name}] tool calls: {[tc['function']['name'] for tc in tool_calls]}")
        messages.append({"role": "assistant", "tool_calls": tool_calls})
        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            fn_args = tc["function"]["arguments"]
            print(f"[{name}] calling {fn_name} with {fn_args}")
            fn = tool_map.get(fn_name)
            result = await fn(**fn_args) if fn else f"unknown tool: {fn_name}"
            print(f"[{name}] {fn_name} result: {str(result)[:120]}")
            messages.append({"role": "tool", "content": str(result)})
