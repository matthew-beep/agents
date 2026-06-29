import httpx
import json

from agents import github_agent

OLLAMA_URL = "http://localhost:11434"

SYSTEM_PROMPT = """You are a helpful assistant. Be concise and direct.

You have access to specialized agents that can fetch real data:
- github_agent: use when the user asks about a GitHub repository, file, or code

If you can answer from your own knowledge, do so. Only call an agent when you need live data."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "github_agent",
            "description": "Fetch data from GitHub — repos, file trees, file contents, READMEs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What you need from GitHub"}
                },
                "required": ["query"],
            },
        },
    }
]

# Maps agent tool names to their run functions.
AGENT_MAP = {
    "github_agent": github_agent.run,
}


async def run(model: str, messages: list[dict], think: bool):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *messages]

    while True:
        tool_calls = []
        content_buffer = []

        # Stream one pass from Ollama. Buffer everything — we don't know yet if this
        # is a tool-calling pass or the final response.
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream(
                "POST",
                f"{OLLAMA_URL}/api/chat",
                json={"model": model, "messages": messages, "tools": TOOLS, "stream": True, "think": think},
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    msg = chunk.get("message", {})

                    if msg.get("tool_calls"):
                        tool_calls.extend(msg["tool_calls"])
                        content_buffer.clear()
                    else:
                        content_buffer.append(line)

        # No tool calls — this is the final response. Stream it live to the frontend.
        if not tool_calls:
            for line in content_buffer:
                yield line + "\n"
            break

        # For each agent call: emit start event, run the agent (fire-and-collect),
        # emit end event with its tool history, then feed its response back to Ollama.
        messages.append({"role": "assistant", "tool_calls": tool_calls})
        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            fn_args = tc["function"]["arguments"]

            yield json.dumps({"type": "agent_start", "agent": fn_name}) + "\n"

            agent_fn = AGENT_MAP.get(fn_name)
            if agent_fn:
                content, tool_history = await agent_fn(
                    model, [{"role": "user", "content": fn_args["query"]}], think
                )
            else:
                content, tool_history = f"unknown agent: {fn_name}", []

            yield json.dumps({"type": "agent_end", "agent": fn_name, "tools": tool_history}) + "\n"

            messages.append({"role": "tool", "content": content})
