from dataclasses import dataclass
from tools import github


@dataclass(frozen=True)
class AgentConfig:
    name: str
    system_prompt: str
    tools: list
    tool_map: dict


AGENTS: dict[str, AgentConfig] = {
    "github_agent": AgentConfig(
        name="github_agent",
        system_prompt=github.SYSTEM_PROMPT,
        tools=github.TOOLS,
        tool_map=github.TOOL_MAP,
    ),
}