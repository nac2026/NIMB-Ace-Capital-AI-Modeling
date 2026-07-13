"use client";

// Postgres-persistent chat drawer scoped to one speculative-analysis session.
// History loads from /api/speculative/sessions/{id} on mount and survives
// across days. Each message is appended via the SSE stream endpoint, which
// writes user + assistant turns to analysis_chat_turns server-side.

import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquare, ArrowUp, X, Loader2, PanelRightOpen } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, type SpeculativeChatTurn } from "@/lib/api";
import { useCollapseState } from "@/lib/use-collapse-state";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8080";

export function SpeculativeChatDrawer({ sessionId }: { sessionId: string }) {
  const qc = useQueryClient();
  const [collapsed, setCollapsed] = useCollapseState("nrc.spec_drawer_collapsed", false);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const messagesRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const detailQ = useQuery({
    queryKey: ["speculative", "session", sessionId],
    queryFn: () => api.speculative.getSession(sessionId),
    refetchOnWindowFocus: false,
  });

  const turns: SpeculativeChatTurn[] = detailQ.data?.chat ?? [];

  // Auto-scroll on new messages
  useEffect(() => {
    if (messagesRef.current) {
      messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
    }
  }, [turns.length, streamingText]);

  async function send() {
    const query = input.trim();
    if (!query || streaming) return;
    setInput("");
    setStreaming(true);
    setStreamingText("");

    try {
      const res = await fetch(
        `${BACKEND}/api/speculative/sessions/${sessionId}/chat/stream`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query }),
        },
      );
      if (!res.ok || !res.body) {
        throw new Error(`Stream failed: ${res.status}`);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let accumulated = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(line.slice(6));
            if (event.type === "token") {
              accumulated += event.text;
              setStreamingText(accumulated);
            } else if (event.type === "done" || event.type === "error") {
              // refresh persisted history
              qc.invalidateQueries({ queryKey: ["speculative", "session", sessionId] });
            }
          } catch {
            // ignore malformed
          }
        }
      }
    } catch (e) {
      console.error(e);
    } finally {
      setStreaming(false);
      setStreamingText("");
    }
  }

  if (collapsed) {
    return (
      <button
        onClick={() => setCollapsed(false)}
        className="flex h-full w-[44px] shrink-0 flex-col items-center justify-start gap-3 border-l bg-bg-subtle py-4 transition-colors hover:bg-bg-hover"
        style={{ borderColor: "var(--border-subtle)" }}
        title="Open analysis chat"
      >
        <PanelRightOpen className="h-4 w-4 text-fg-muted" strokeWidth={1.75} />
        <div
          className="flex h-7 w-7 items-center justify-center rounded-md"
          style={{ background: "var(--brand-soft)", color: "var(--brand)" }}
        >
          <MessageSquare className="h-3.5 w-3.5" strokeWidth={1.75} />
        </div>
        <span className="rotate-180 whitespace-nowrap text-[10.5px] font-semibold uppercase tracking-widest text-fg-muted [writing-mode:vertical-rl]">
          Chat about this analysis
        </span>
      </button>
    );
  }

  return (
    <aside
      className="flex h-full w-[380px] shrink-0 flex-col border-l bg-bg-subtle"
      style={{ borderColor: "var(--border-subtle)" }}
    >
      {/* Header */}
      <div
        className="flex h-[52px] shrink-0 items-center justify-between border-b px-4"
        style={{ borderColor: "var(--border-subtle)" }}
      >
        <div className="flex items-center gap-2">
          <div
            className="flex h-7 w-7 items-center justify-center rounded-md"
            style={{ background: "var(--brand-soft)", color: "var(--brand)" }}
          >
            <MessageSquare className="h-3.5 w-3.5" strokeWidth={1.75} />
          </div>
          <div>
            <div className="text-[12.5px] font-semibold tracking-tight text-fg">Analysis chat</div>
            <div className="text-[10.5px] text-fg-muted">Persistent · scoped to this analysis</div>
          </div>
        </div>
        <button
          onClick={() => setCollapsed(true)}
          className="flex h-7 w-7 items-center justify-center rounded-md text-fg-muted transition-colors hover:bg-bg-hover hover:text-fg"
          title="Collapse"
        >
          <X className="h-3.5 w-3.5" strokeWidth={1.75} />
        </button>
      </div>

      {/* Messages */}
      <div ref={messagesRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {turns.length === 0 && !streaming && (
          <div className="rounded-md p-3 text-[12px] text-fg-muted" style={{ background: "var(--bg-panel)" }}>
            Ask anything about this analysis. The AI has the full ticker list and flag summary as context — questions like
            <em> &quot;why is NABIL red?&quot;</em> or <em>&quot;which RED names share weak capital?&quot;</em> work without restating the ticker.
          </div>
        )}

        {turns.map((t) => (
          <MessageRow key={t.turn_id} role={t.role} text={t.content} />
        ))}

        {streaming && streamingText && (
          <MessageRow role="assistant" text={streamingText} />
        )}
        {streaming && !streamingText && (
          <div className="flex items-center gap-2 text-[12px] text-fg-muted">
            <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={2} />
            Thinking…
          </div>
        )}
      </div>

      {/* Input */}
      <div className="border-t p-3" style={{ borderColor: "var(--border-subtle)" }}>
        <div
          className="relative flex items-end rounded-xl px-3 py-2 transition-all"
          style={{ background: "var(--bg-panel)", border: "1.5px solid var(--border)" }}
        >
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            rows={1}
            placeholder="Ask about this analysis…"
            disabled={streaming}
            className="max-h-[120px] w-full resize-none bg-transparent pr-10 text-[13px] leading-relaxed text-fg outline-none placeholder:text-fg-muted disabled:opacity-50"
          />
          <button
            onClick={send}
            disabled={streaming || input.trim().length === 0}
            className="absolute bottom-2 right-2 flex h-7 w-7 items-center justify-center rounded-lg transition-opacity disabled:opacity-30 hover:opacity-90"
            style={{ background: "var(--brand)" }}
          >
            <ArrowUp className="h-3.5 w-3.5 text-white" strokeWidth={2.5} />
          </button>
        </div>
      </div>
    </aside>
  );
}

function MessageRow({ role, text }: { role: "user" | "assistant"; text: string }) {
  if (role === "user") {
    return (
      <div className="flex justify-end">
        <div
          className="max-w-[85%] rounded-2xl px-3.5 py-2 text-[12.5px]"
          style={{ background: "var(--brand)", color: "#ffffff" }}
        >
          {text}
        </div>
      </div>
    );
  }
  return (
    <div className="text-[12.5px] markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  );
}
