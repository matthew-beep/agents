export type ToolCall = {
    tool: string
    args: Record<string, unknown>
    error?: string
    duration_ms?: number
}

export type PlanEvent = {
    type: "plan"
    content: string
    duration_ms?: number
}

export type AgentStartEvent = {
    type: "agent_start"
    agent: string
}

export type ToolCallEvent = {
    type: "tool_call"
    tool: string
    args: Record<string, unknown>
    duration_ms?: number
}

export type AgentEndEvent = {
    type: "agent_end"
    agent: string
    tools: ToolCall[]
    duration_ms?: number
}

export type TokenEvent = {
    type: "token"
    content: string
}

export type DoneEvent = {
    type: "done"
    tokens?: number
    tokens_per_sec?: number
    duration_ms?: number
    total_ms?: number
}

export type AgentErrorEvent = {
    type: "agent_error"
    agent: string
    error: string
    tool?: string
}

export type AgentResultEvent = {
    type: "agent_result"
    content: string
}

export type Event =
    | PlanEvent
    | AgentStartEvent
    | ToolCallEvent
    | AgentEndEvent
    | TokenEvent
    | DoneEvent
    | AgentErrorEvent
    | AgentResultEvent
