"use client";

import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ToolCall,  PlanEvent} from "../types";

const API_URL = "http://localhost:8000";

// type ToolCall = { tool: string; args: Record<string, unknown> };

type AgentActivity = {
  agent: string;
  status: "running" | "done";
  tools: ToolCall[];
  expanded: boolean;
};

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  // Attached after the response completes so the trace stays visible.
  agentHistory?: AgentActivity[];
};

export default function Home() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  // Live agent activity during the current streaming response.
  const [agentHistory, setAgentHistory] = useState<AgentActivity[]>([]);
  const [streamingThink, setStreamingThink] = useState("");
  const [streamingContent, setStreamingContent] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [plan, setPlan] = useState<PlanEvent | null>(null);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingThink, streamingContent, agentHistory]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMessage: ChatMessage = { role: "user", content: input };
    const history: ChatMessage[] = [...messages, userMessage];
    setMessages(history);
    setInput("");
    setLoading(true);
    setStreamingThink("");
    setStreamingContent("");
    setAgentHistory([]);

    // Local variable so we always read the latest value when attaching to the message,
    // avoiding stale closure issues with React state.
    let currentAgentHistory: AgentActivity[] = [];

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
          console.log("data", data);
          if (data.type === "agent_start") {
            // Sub-agent started — add a running entry to the live activity panel.
            const next = [...currentAgentHistory, {
              agent: data.agent,
              status: "running" as const,
              tools: [],
              expanded: false,
            }];
            currentAgentHistory = next;
            setAgentHistory(next);
          } else if (data.type === "agent_end") {
            // Sub-agent finished — mark done and attach its tool history.
            const next = currentAgentHistory.map((a) =>
              a.agent === data.agent
                ? { ...a, status: "done" as const, tools: data.tools }
                : a
            );
            currentAgentHistory = next;
            setAgentHistory(next);
          } else if (data.type === "plan") {
            setPlan(data);

          } else if (data.type === "token") {

            if (data?.content) {
              finalContent += data?.content;
              setStreamingContent((prev) => prev + data?.content);
            }
          } else {
            // Regular Ollama chunk — extract think/content as before.
            if (data.message?.thinking) {
              setStreamingThink((prev) => prev + data.message.thinking);
            }
            if (data.message?.content) {
              finalContent += data.message.content;
              setStreamingContent((prev) => prev + data.message.content);
            }
            setPlan(null);
          }
        }
      }

      // Attach the captured agent history to the message so the trace persists.
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: finalContent, agentHistory: currentAgentHistory },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Failed to reach server." },
      ]);
    } finally {
      setStreamingThink("");
      setStreamingContent("");
      // Clear live panel — the trace now lives on the message.
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

        {loading && !streamingContent && agentHistory.length === 0 && (
          <div style={{ ...s.row, justifyContent: "flex-start", color: "#999", fontSize: "0.85rem" }}>
            ...
          </div>
        )}

        {loading && streamingThink && !streamingContent && (
          <div style={{ ...s.row, justifyContent: "flex-start", color: "#999", fontSize: "0.85rem" }}>
            {streamingThink}
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
            <div className="md" style={{ ...s.bubble, ...s.assistantBubble }}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamingContent}</ReactMarkdown>
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
            <span style={{ color: activity.status === "running" ? "#999" : "#2a7a2a" }}>
              {activity.status === "running" ? "◌" : "✓"}{" "}
              {formatAgentName(activity.agent)}
              {activity.status === "done" &&
                ` (${activity.tools.length} tool${activity.tools.length !== 1 ? "s" : ""})`}
            </span>
            {activity.status === "done" && activity.tools.length > 0 && (
              <button style={s.expandBtn} onClick={() => onToggle(i)}>
                {activity.expanded ? "▼" : "▶"}
              </button>
            )}
          </div>
          {activity.expanded && (
            <div style={s.toolList}>
              {activity.tools.map((t, j) => (
                <div key={j} style={s.toolEntry}>
                  {t.tool}()
                </div>
              ))}
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
};
