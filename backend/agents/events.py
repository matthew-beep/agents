import json
from typing import Any, Literal, TypedDict


class ToolCall(TypedDict):
    tool: str
    args: dict[str, Any]


class PlanEvent(TypedDict, total=False):
    type: Literal["plan"]
    content: str
    duration_ms: int


class AgentStartEvent(TypedDict):
    type: Literal["agent_start"]
    agent: str


class ToolCallEvent(TypedDict, total=False):
    type: Literal["tool_call"]
    tool: str
    args: dict[str, Any]
    duration_ms: int


class AgentEndEvent(TypedDict, total=False):
    type: Literal["agent_end"]
    agent: str
    tools: list[ToolCall]
    duration_ms: int


class TokenEvent(TypedDict):
    type: Literal["token"]
    content: str


class DoneEvent(TypedDict, total=False):
    type: Literal["done"]
    tokens: int
    tokens_per_sec: float
    duration_ms: int
    total_ms: int


Event = (
    PlanEvent
    | AgentStartEvent
    | ToolCallEvent
    | AgentEndEvent
    | TokenEvent
    | DoneEvent
)


def emit(event: Event) -> str:
    if "type" not in event:
        raise KeyError("Event must have a 'type' field")
    return json.dumps(event) + "\n"


def plan_event(content: str, *, duration_ms: int | None = None) -> PlanEvent:
    event: PlanEvent = {"type": "plan", "content": content}
    if duration_ms is not None:
        event["duration_ms"] = duration_ms
    return event


def agent_start_event(agent: str) -> AgentStartEvent:
    return {"type": "agent_start", "agent": agent}


def tool_call_event(
    tool: str, args: dict[str, Any], *, duration_ms: int | None = None
) -> ToolCallEvent:
    event: ToolCallEvent = {"type": "tool_call", "tool": tool, "args": args}
    if duration_ms is not None:
        event["duration_ms"] = duration_ms
    return event


def agent_end_event(
    agent: str,
    tools: list[ToolCall],
    *,
    duration_ms: int | None = None,
) -> AgentEndEvent:
    event: AgentEndEvent = {"type": "agent_end", "agent": agent, "tools": tools}
    if duration_ms is not None:
        event["duration_ms"] = duration_ms
    return event


def token_event(content: str) -> TokenEvent:
    return {"type": "token", "content": content}


def done_event(
    *,
    tokens: int | None = None,
    tokens_per_sec: float | None = None,
    duration_ms: int | None = None,
    total_ms: int | None = None,
) -> DoneEvent:
    event: DoneEvent = {"type": "done"}
    if tokens is not None:
        event["tokens"] = tokens
    if tokens_per_sec is not None:
        event["tokens_per_sec"] = tokens_per_sec
    if duration_ms is not None:
        event["duration_ms"] = duration_ms
    if total_ms is not None:
        event["total_ms"] = total_ms
    return event
