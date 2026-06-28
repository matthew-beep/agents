"use client";

import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const API_URL = "http://localhost:8000";
const GITHUB_URL = "https://api.github.com"

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

export default function Home() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streamingThink, setStreamingThink] = useState("");
  const [streamingContent, setStreamingContent] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingThink, streamingContent]);

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
          if (data.message?.thinking) {
            setStreamingThink((prev) => prev + data.message.thinking);
          }
          if (data.message?.content) {
            finalContent += data.message.content;
            setStreamingContent((prev) => prev + data.message.content);
          }
        }
      }

      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: finalContent },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Failed to reach server." },
      ]);
    } finally {
      setStreamingThink("");
      setStreamingContent("");
      setLoading(false);
    }
  }

  async function searchRepos() {
    try {
      const res = await fetch(`${API_URL}/search?q=local+LLM+agent+tool+use&sort=stars`);
      const data = await res.json();
      console.log(data);
    } catch (error) {
      console.error(error);
    }
  }

  return (
    <main style={s.main}>
      <button onClick={searchRepos} style={{ ...s.button, margin: "0.75rem 1rem 0" }}>
        Search repos
      </button>
      <div style={s.messageList}>
        {messages.map((msg, i) => (
          <div
            key={i}
            style={{
              ...s.row,
              justifyContent: msg.role === "user" ? "flex-end" : "flex-start",
            }}
          >
            <div
              className={msg.role === "assistant" ? "md" : undefined}
              style={{
                ...s.bubble,
                ...(msg.role === "user" ? s.userBubble : s.assistantBubble),
              }}
            >
              {msg.role === "user" ? msg.content : (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {msg.content}
                </ReactMarkdown>
              )}
            </div>
          </div>
        ))}
        {loading && <div style={{ ...s.row, justifyContent: "flex-start", color: "#999", fontSize: "0.85rem" }}>...</div>}

        {loading && streamingThink && !streamingContent && (
          <div style={{ ...s.row, justifyContent: "flex-start", color: "#999", fontSize: "0.85rem" }}>
              {streamingThink}
          </div>
        )}

        {loading && streamingContent && (
          <div style={{ ...s.row, justifyContent: "flex-start" }}>
            <div className="md" style={{ ...s.bubble, ...s.assistantBubble }}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {streamingContent}
              </ReactMarkdown>
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
          style={{
            ...s.button,
            opacity: loading || !input.trim() ? 0.5 : 1,
          }}
        >
          Send
        </button>
      </form>
    </main>
  );
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
  bubble: {
    maxWidth: "75%",
    padding: "0.6rem 0.9rem",
    borderRadius: "1rem",
    lineHeight: 1.5,
    fontSize: "0.95rem",
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
  },
  userBubble: {
    backgroundColor: "#0070f3",
    color: "#fff",
    borderBottomRightRadius: "0.25rem",
  },
  assistantBubble: {
    backgroundColor: "#f1f1f1",
    color: "#111",
    borderBottomLeftRadius: "0.25rem",
  },
  thinkBubble: {
    backgroundColor: "#fafafa",
    color: "#999",
    fontStyle: "italic",
    fontSize: "0.85rem",
    border: "1px solid #eee",
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
};
