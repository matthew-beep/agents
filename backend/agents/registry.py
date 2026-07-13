from dataclasses import dataclass
from tools import github


@dataclass(frozen=True)
class AgentConfig:
    name: str
    description: str
    system_prompt: str
    tools: list
    tool_map: dict


AGENTS: dict[str, AgentConfig] = {
    "github_agent": AgentConfig(
        name="github_agent",
        description="Fetch live data from GitHub — repos, file trees, file contents, READMEs.",
        system_prompt=github.SYSTEM_PROMPT,
        tools=github.TOOLS,
        tool_map=github.TOOL_MAP,
    ),
}

# Every agent shares this call shape (query: str) — deliberate, not incidental.
# Kept as one named constant so orchestrator_tools() doesn't repeat the literal
# per agent, without promoting it to a per-AgentConfig field (which would invite
# per-agent divergence we don't need yet).
_AGENT_CALL_PARAMETERS = {
    "type": "object",
    "properties": {"query": {"type": "string", "description": "What you need from this agent"}},
    "required": ["query"],
}


def orchestrator_tools() -> list:
    """Ollama tool schemas exposing each registered agent as a callable function."""
    return [{
        "type": "function",
        "function": {
            "name": a.name,
            "description": a.description,
            "parameters": _AGENT_CALL_PARAMETERS,
        },
    } for a in AGENTS.values()]


def agent_directory() -> str:
    """Prose list of agents for interpolation into the orchestrator system prompt."""
    return "\n".join(f"- {a.name}: {a.description}" for a in AGENTS.values())