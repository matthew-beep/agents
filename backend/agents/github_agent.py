from agents.base import run_agent
from tools import github

SYSTEM_PROMPT = """You are a GitHub assistant. Be concise and direct.

You have access to tools that can fetch real data from GitHub.
If you can answer from your own knowledge, do so. Only call a tool when you actually need live data.

When reporting tool results, always use the exact data returned — never infer, summarize, or invent file paths or structure. If the tree is truncated, say so."""


async def run(model: str, messages: list[dict], think: bool) -> tuple[str, list[dict]]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *messages]
    return await run_agent("github_agent", model, messages, github.TOOLS, github.TOOL_MAP, think)
