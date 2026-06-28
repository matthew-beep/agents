import json

from agents.base import run_agent
from agents import github_agent

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


async def _collect(agent_gen) -> str:
    content = ""
    async for line in agent_gen:
        chunk = json.loads(line)
        content += chunk.get("message", {}).get("content", "")
    return content


async def run(model: str, messages: list[dict], think: bool):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *messages]

    async def call_github_agent(query: str) -> str:
        return await _collect(github_agent.run(model, [{"role": "user", "content": query}], think))

    agent_map = {
        "github_agent": call_github_agent,
    }

    async for chunk in run_agent("orchestrator", model, messages, TOOLS, agent_map, think):
        yield chunk
