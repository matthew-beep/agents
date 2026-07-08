"use client";

import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { DoneEvent, PlanEvent, ToolCall } from "../types";

const API_URL = "http://localhost:8000";

type AgentActivity = {
  agent: string;
  status: "running" | "done" | "error";
  tools: ToolCall[];
  expanded: boolean;
  error?: string;
  duration_ms?: number;
};

type StreamStats = Pick<DoneEvent, "tokens" | "tokens_per_sec" | "duration_ms">;

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  agentHistory?: AgentActivity[];
  stats?: StreamStats;
};

function findLastRunningIndex(history: AgentActivity[], agent?: string): number {
  for (let i = history.length - 1; i >= 0; i--) {
    if (history[i].status !== "running") continue;
    if (agent && history[i].agent !== agent) continue;
    return i;
  }
  return -1;
}

function formatToolCall(t: ToolCall): string {
  const argStr = Object.entries(t.args)
    .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
    .join(", ");
  return argStr ? `${t.tool}(${argStr})` : `${t.tool}()`;
}

function formatStats(stats: StreamStats): string {
  const parts: string[] = [];
  if (stats.tokens_per_sec != null) parts.push(`${stats.tokens_per_sec} tok/s`);
  if (stats.duration_ms != null) parts.push(`${(stats.duration_ms / 1000).toFixed(1)}s`);
  if (stats.tokens != null) parts.push(`${stats.tokens} tokens`);
  return parts.join(" · ");
}

export default function Home() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  // Live agent activity during the current streaming response.
  const [agentHistory, setAgentHistory] = useState<AgentActivity[]>([]);
  const [streamingContent, setStreamingContent] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [plan, setPlan] = useState<PlanEvent | null>(null);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent, agentHistory]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMessage: ChatMessage = { role: "user", content: input };
    const history: ChatMessage[] = [...messages, userMessage];
    setMessages(history);
    setInput("");
    setLoading(true);
    setStreamingContent("");
    setAgentHistory([]);

    // Local variable so we always read the latest value when attaching to the message,
    // avoiding stale closure issues with React state.
    let currentAgentHistory: AgentActivity[] = [];
    let streamStats: StreamStats | undefined;

    try {
      const res = await fetch(`${API_URL}/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "qwen3.5:9b",
          messages: history.map((m) => ({ role: m.role, content: m.content })),
          stream: true,
          think: false,
        }),
      });

      if (!res.ok) throw new Error(`Server error: ${res.status}`);

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) throw new Error("No reader");

      let buffer = "";
      let finalContent = "";

      while (true) {
        const { done, value } = await reader.read();

        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.trim()) continue;
          const data = JSON.parse(line);

          if (data.type === "agent_start") {
            setPlan(null);
            const next = [...currentAgentHistory, {
              agent: data.agent,
              status: "running" as const,
              tools: [],
              expanded: false,
            }];
            currentAgentHistory = next;
            setAgentHistory(next);
          } else if (data.type === "tool_call") {
            const idx = findLastRunningIndex(currentAgentHistory);
            if (idx >= 0) {
              const next = [...currentAgentHistory];
              next[idx] = {
                ...next[idx],
                expanded: true,
                tools: [
                  ...next[idx].tools,
                  {
                    tool: data.tool,
                    args: data.args ?? {},
                    duration_ms: data.duration_ms,
                  },
                ],
              };
              currentAgentHistory = next;
              setAgentHistory(next);
            }
          } else if (data.type === "agent_error") {
            const idx = findLastRunningIndex(currentAgentHistory, data.agent);
            if (idx >= 0) {
              const next = [...currentAgentHistory];
              const entry = next[idx];
              next[idx] = {
                ...entry,
                error: data.error,
                tools: data.tool
                  ? [...entry.tools, { tool: data.tool, args: {}, error: data.error }]
                  : entry.tools,
              };
              currentAgentHistory = next;
              setAgentHistory(next);
            } else {
              const next = [...currentAgentHistory, {
                agent: data.agent,
                status: "error" as const,
                tools: data.tool
                  ? [{ tool: data.tool, args: {}, error: data.error }]
                  : [],
                expanded: true,
                error: data.error,
              }];
              currentAgentHistory = next;
              setAgentHistory(next);
            }
          } else if (data.type === "agent_end") {
            const idx = findLastRunningIndex(currentAgentHistory, data.agent);
            if (idx >= 0) {
              const next = [...currentAgentHistory];
              next[idx] = {
                ...next[idx],
                status: next[idx].error ? "error" as const : "done" as const,
                tools: data.tools ?? next[idx].tools,
                duration_ms: data.duration_ms,
              };
              currentAgentHistory = next;
              setAgentHistory(next);
            }
          } else if (data.type === "plan") {
            setPlan(data);
          } else if (data.type === "token") {
            setPlan(null);
            if (data.content) {
              finalContent += data.content;
              setStreamingContent((prev) => prev + data.content);
            }
          } else if (data.type === "done") {
            setPlan(null);
            streamStats = {
              tokens: data.tokens,
              tokens_per_sec: data.tokens_per_sec,
              duration_ms: data.duration_ms,
            };
          }
        }
      }

      // Attach the captured agent history to the message so the trace persists.
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: finalContent,
          agentHistory: currentAgentHistory.length > 0 ? currentAgentHistory : undefined,
          stats: streamStats,
        },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Failed to reach server." },
      ]);
    } finally {
      setStreamingContent("");
      setAgentHistory([]);
      setLoading(false);
    }
  }

  // Toggle expand/collapse on a completed message's agent panel.
  function toggleMessageAgent(msgIndex: number, agentIndex: number) {
    setMessages((prev) =>
      prev.map((msg, i) => {
        if (i !== msgIndex || !msg.agentHistory) return msg;
        return {
          ...msg,
          agentHistory: msg.agentHistory.map((a, j) =>
            j === agentIndex ? { ...a, expanded: !a.expanded } : a
          ),
        };
      })
    );
  }

  // Toggle expand/collapse on the live streaming panel.
  function toggleLiveAgent(index: number) {
    setAgentHistory((prev) =>
      prev.map((a, i) => (i === index ? { ...a, expanded: !a.expanded } : a))
    );
  }

  return (
    <main style={s.main}>

      <div style={s.messageList}>
        {messages.map((msg, i) => (
          <div
            key={i}
            style={{ ...s.row, justifyContent: msg.role === "user" ? "flex-end" : "flex-start" }}
          >
            {msg.role === "user" ? (
              <div style={{ ...s.bubble, ...s.userBubble }}>{msg.content}</div>
            ) : (
              <div style={s.assistantGroup}>
                {msg.agentHistory && msg.agentHistory.length > 0 && (
                  <AgentPanel
                    history={msg.agentHistory}
                    onToggle={(agentIndex) => toggleMessageAgent(i, agentIndex)}
                  />
                )}
                <div className="md" style={{ ...s.bubble, ...s.assistantBubble }}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                </div>
                {msg.stats && (
                  <div style={s.stats}>{formatStats(msg.stats)}</div>
                )}
              </div>
            )}
          </div>
        ))}

        {plan && (
          <div style={{ ...s.row, justifyContent: "flex-start" }}>
            <div className="md" style={{ ...s.bubble, ...s.assistantBubble }}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{plan.content}</ReactMarkdown>
            </div>
          </div>
        )}

        {loading && !streamingContent && agentHistory.length === 0 && !plan && (
          <div style={{ ...s.row, justifyContent: "flex-start", color: "#999", fontSize: "0.85rem" }}>
            ...
          </div>
        )}

        {/* Live agent panel shown while a response is in progress. */}
        {loading && agentHistory.length > 0 && (
          <div style={{ ...s.row, justifyContent: "flex-start" }}>
            <AgentPanel history={agentHistory} onToggle={toggleLiveAgent} />
          </div>
        )}

        {loading && streamingContent && (
          <div style={{ ...s.row, justifyContent: "flex-start" }}>
            <div style={s.assistantGroup}>
              <div className="md" style={{ ...s.bubble, ...s.assistantBubble }}>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamingContent}</ReactMarkdown>
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <form onSubmit={handleSubmit} style={s.form}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Message..."
          disabled={loading}
          style={s.input}
          autoFocus
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          style={{ ...s.button, opacity: loading || !input.trim() ? 0.5 : 1 }}
        >
          Send
        </button>
      </form>
    </main>
  );
}

function AgentPanel({
  history,
  onToggle,
}: {
  history: AgentActivity[];
  onToggle: (index: number) => void;
}) {
  return (
    <div style={s.agentPanel}>
      {history.map((activity, i) => (
        <div key={i} style={s.agentEntry}>
          <div style={s.agentRow}>
            <span
              style={{
                color:
                  activity.status === "running"
                    ? "#999"
                    : activity.status === "error"
                      ? "#c0392b"
                      : "#2a7a2a",
              }}
            >
              {activity.status === "running" ? "◌" : activity.status === "error" ? "✗" : "✓"}{" "}
              {formatAgentName(activity.agent)}
              {activity.tools.length > 0 &&
                ` (${activity.tools.length} tool${activity.tools.length !== 1 ? "s" : ""})`}
              {activity.status === "done" && activity.duration_ms != null &&
                ` · ${(activity.duration_ms / 1000).toFixed(1)}s`}
            </span>
            {activity.tools.length > 0 && (
              <button style={s.expandBtn} onClick={() => onToggle(i)}>
                {activity.expanded ? "▼" : "▶"}
              </button>
            )}
          </div>
          {activity.error && !activity.expanded && (
            <div style={s.agentError}>{activity.error}</div>
          )}
          {activity.expanded && (
            <div style={s.toolList}>
              {activity.tools.map((t, j) => (
                <div
                  key={j}
                  style={{
                    ...s.toolEntry,
                    ...(t.error ? { color: "#c0392b", borderLeftColor: "#e8b4b4" } : {}),
                  }}
                >
                  {formatToolCall(t)}
                  {t.error && ` — ${t.error}`}
                </div>
              ))}
              {activity.error && (
                <div style={{ ...s.toolEntry, color: "#c0392b", borderLeftColor: "#e8b4b4" }}>
                  {activity.error}
                </div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function formatAgentName(agent: string): string {
  return agent.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

const s: Record<string, React.CSSProperties> = {
  main: {
    display: "flex",
    flexDirection: "column",
    height: "100vh",
    maxWidth: "720px",
    margin: "0 auto",
    fontFamily: "system-ui, -apple-system, sans-serif",
  },
  messageList: {
    flex: 1,
    overflowY: "auto",
    padding: "1.5rem 1rem",
    display: "flex",
    flexDirection: "column",
    gap: "0.75rem",
  },
  row: {
    display: "flex",
  },
  assistantGroup: {
    display: "flex",
    flexDirection: "column",
    gap: "0.4rem",
    maxWidth: "75%",
  },
  bubble: {
    padding: "0.6rem 0.9rem",
    borderRadius: "1rem",
    lineHeight: 1.5,
    fontSize: "0.95rem",
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
  },
  userBubble: {
    maxWidth: "75%",
    backgroundColor: "#0070f3",
    color: "#fff",
    borderBottomRightRadius: "0.25rem",
  },
  assistantBubble: {
    backgroundColor: "#f1f1f1",
    color: "#111",
    borderBottomLeftRadius: "0.25rem",
  },
  form: {
    display: "flex",
    gap: "0.5rem",
    padding: "1rem",
    borderTop: "1px solid #eee",
  },
  input: {
    flex: 1,
    padding: "0.65rem 0.9rem",
    borderRadius: "0.5rem",
    border: "1px solid #ddd",
    fontSize: "0.95rem",
    outline: "none",
  },
  button: {
    padding: "0.65rem 1.2rem",
    borderRadius: "0.5rem",
    border: "none",
    backgroundColor: "#0070f3",
    color: "#fff",
    fontSize: "0.95rem",
    cursor: "pointer",
    transition: "opacity 0.15s",
  },
  agentPanel: {
    display: "flex",
    flexDirection: "column",
    gap: "0.3rem",
    padding: "0.5rem 0.75rem",
    backgroundColor: "#fafafa",
    border: "1px solid #eee",
    borderRadius: "0.5rem",
    fontSize: "0.85rem",
  },
  agentEntry: {
    display: "flex",
    flexDirection: "column",
    gap: "0.2rem",
  },
  agentRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "0.5rem",
  },
  expandBtn: {
    background: "none",
    border: "none",
    cursor: "pointer",
    fontSize: "0.7rem",
    color: "#aaa",
    padding: "0 0.2rem",
  },
  toolList: {
    paddingLeft: "1rem",
    display: "flex",
    flexDirection: "column",
    gap: "0.15rem",
    color: "#666",
    fontFamily: "monospace",
    fontSize: "0.8rem",
  },
  toolEntry: {
    paddingLeft: "0.5rem",
    borderLeft: "2px solid #e0e0e0",
  },
  agentError: {
    paddingLeft: "1rem",
    color: "#c0392b",
    fontSize: "0.8rem",
  },
  stats: {
    fontSize: "0.75rem",
    color: "#aaa",
    paddingLeft: "0.25rem",
  },
};
