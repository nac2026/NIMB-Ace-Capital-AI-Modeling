"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { Sparkles } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { Message, MessageBubble, extractVisuals, VisualBlock } from "@/components/chat/message-bubble";
import { VisualPanel } from "@/components/chat/visual-panel";
import { ChatInput } from "@/components/chat/chat-input";
import { Suggestions } from "@/components/chat/suggestions";
import { HistorySidebar, ConversationMeta } from "@/components/chat/history-sidebar";
import { useCollapseState } from "@/lib/use-collapse-state";

const STORE_KEY = "nrc.conversations";
const ACTIVE_KEY = "nrc.session_id";

type Conversation = ConversationMeta & { messages: Message[] };

function newId() {
  return "s-" + Math.random().toString(36).slice(2, 10);
}

function loadConversations(): Conversation[] {
  if (typeof window === "undefined") return [];
  try { return JSON.parse(localStorage.getItem(STORE_KEY) || "[]"); }
  catch { return []; }
}

function persist(convos: Conversation[]) {
  localStorage.setItem(STORE_KEY, JSON.stringify(convos));
}

// ── Typing indicator ──────────────────────────────────────────────────
const THINKING_PHRASES = [
  "Thinking…",
  "Planning the approach…",
  "Reviewing your question…",
  "Checking context…",
  "Gathering data…",
  "Preparing answer…",
];

function TypingIndicator({ status }: { status: string }) {
  const [phraseIdx, setPhraseIdx] = useState(0);

  useEffect(() => {
    if (status) return;
    const t = setInterval(() => {
      setPhraseIdx((i) => (i + 1) % THINKING_PHRASES.length);
    }, 2400);
    return () => clearInterval(t);
  }, [status]);

  const displayText = status || THINKING_PHRASES[phraseIdx];

  return (
    <div className="flex justify-start items-start gap-2.5 py-1">
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg mt-0.5"
           style={{ background: "color-mix(in oklab, var(--accent) 18%, var(--panel-3))", color: "var(--accent)" }}>
        <Sparkles className="h-4 w-4" strokeWidth={2.2} />
      </div>
      <div
        className="rounded-2xl rounded-tl-sm px-4 py-2.5 text-[13px] text-fg-muted"
        style={{ background: "var(--panel-3)", border: "1px solid var(--line)" }}
      >
        <div className="flex items-center gap-2">
          <span className="thinking-dot" style={{ animationDelay: "0ms" }} />
          <span className="thinking-dot" style={{ animationDelay: "160ms" }} />
          <span className="thinking-dot" style={{ animationDelay: "320ms" }} />
          <span key={displayText} className="animate-fade-in">{displayText}</span>
        </div>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────
function ChatPageInner() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [statusText, setStatusText] = useState<string>("");

  // Visual panel state
  const [panelWidth, setPanelWidth] = useState(380);
  const [panelClosed, setPanelClosed] = useState(false);
  // null = always track the latest message with visuals
  const [pinnedMsgIdx, setPinnedMsgIdx] = useState<number | null>(null);

  // History sidebar collapsed state (persisted).
  const [historyCollapsed, setHistoryCollapsed] = useCollapseState("nrc.chat_history_collapsed", false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const wasSendingRef = useRef(false);
  const dragRef = useRef({ active: false, startX: 0, startWidth: 0 });
  const params = useSearchParams();

  useEffect(() => {
    const stored = loadConversations();
    setConversations(stored);
    const lastId = localStorage.getItem(ACTIVE_KEY);
    if (lastId && stored.some((c) => c.id === lastId)) {
      setActiveId(lastId);
    }
  }, []);

  useEffect(() => {
    if (activeId) localStorage.setItem(ACTIVE_KEY, activeId);
    // Reset panel pin when switching conversations
    setPinnedMsgIdx(null);
  }, [activeId]);

  const messages = conversations.find((c) => c.id === activeId)?.messages ?? [];

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, sending]);

  // When a new response finishes: unpin + auto-open panel if it has visuals
  useEffect(() => {
    if (wasSendingRef.current && !sending) {
      const last = messages[messages.length - 1];
      if (last?.role === "assistant") {
        const { visuals } = extractVisuals(last.content);
        if (visuals.length > 0) {
          setPinnedMsgIdx(null);
          setPanelClosed(false); // always surface new charts
        }
      }
    }
    wasSendingRef.current = sending;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sending]);

  // All assistant messages that have visuals, in order
  const visualMessages = useMemo(() => {
    const result: Array<{ idx: number; visuals: VisualBlock[] }> = [];
    for (let i = 0; i < messages.length; i++) {
      if (messages[i].role === "assistant") {
        const { visuals } = extractVisuals(messages[i].content);
        if (visuals.length > 0) result.push({ idx: i, visuals });
      }
    }
    return result;
  }, [messages]);

  const lastVisualMsgIdx = visualMessages.length > 0
    ? visualMessages[visualMessages.length - 1].idx
    : null;

  const effectiveIdx = pinnedMsgIdx ?? lastVisualMsgIdx;

  const activeVisuals: VisualBlock[] = effectiveIdx !== null
    ? (visualMessages.find((v) => v.idx === effectiveIdx)?.visuals ?? [])
    : [];

  const isHistorical = effectiveIdx !== null && effectiveIdx !== lastVisualMsgIdx;

  // Index set for O(1) badge lookup
  const visualMsgIdxSet = useMemo(
    () => new Set(visualMessages.map((v) => v.idx)),
    [visualMessages],
  );

  // ── Drag to resize panel ──────────────────────────────────────────
  function handleDragStart(e: React.MouseEvent) {
    dragRef.current = { active: true, startX: e.clientX, startWidth: panelWidth };
    e.preventDefault();

    function onMove(ev: MouseEvent) {
      if (!dragRef.current.active) return;
      // Dragging left (smaller clientX) widens the panel
      const delta = dragRef.current.startX - ev.clientX;
      const newW = Math.max(260, Math.min(640, dragRef.current.startWidth + delta));
      setPanelWidth(newW);
    }

    function onUp() {
      dragRef.current.active = false;
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    }

    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }

  // ── Send ──────────────────────────────────────────────────────────
  function send(query: string) {
    if (sending) return;
    setSending(true);

    let sid = activeId;
    const isNew = !sid;
    if (isNew) sid = newId();

    const userMsg: Message = { role: "user", content: query };
    setConversations((prev) => {
      const next: Conversation[] = isNew
        ? [{ id: sid!, title: query.length > 52 ? query.slice(0, 49) + "…" : query, createdAt: Date.now(), messages: [userMsg] }, ...prev]
        : prev.map((c) => c.id === sid ? { ...c, messages: [...c.messages, userMsg] } : c);
      persist(next);
      return next;
    });
    if (isNew) setActiveId(sid);

    setStatusText("Thinking…");

    const ctrl = api.chatStream(
      query,
      sid!,
      (token) => {
        flushSync(() => {
          setConversations((prev) => prev.map((c) => {
            if (c.id !== sid) return c;
            const msgs = [...c.messages];
            const last = msgs[msgs.length - 1];
            if (last?.role === "assistant") {
              msgs[msgs.length - 1] = { ...last, content: last.content + token };
            } else {
              msgs.push({ role: "assistant", content: token });
            }
            return { ...c, messages: msgs };
          }));
        });
      },
      () => {
        setConversations((prev) => { persist(prev); return prev; });
        setSending(false);
        setStatusText("");
        abortRef.current = null;
      },
      (err) => {
        setConversations((prev) => {
          const next = prev.map((c) => {
            if (c.id !== sid) return c;
            const msgs = [...c.messages];
            const last = msgs[msgs.length - 1];
            if (last?.role === "assistant" && last.content.length > 0) return c;
            if (last?.role === "assistant") {
              msgs[msgs.length - 1] = { role: "assistant", content: `_Error: ${err.message}_` };
            } else {
              msgs.push({ role: "assistant", content: `_Error: ${err.message}_` });
            }
            return { ...c, messages: msgs };
          });
          persist(next);
          return next;
        });
        setSending(false);
        setStatusText("");
        abortRef.current = null;
      },
      (status) => setStatusText(status),
    );
    abortRef.current = ctrl;
  }

  function handleNew() {
    abortRef.current?.abort();
    abortRef.current = null;
    setSending(false);
    setActiveId(null);
  }

  function handleSelect(id: string) { setActiveId(id); }

  function handleDelete(id: string) {
    setConversations((prev) => {
      const next = prev.filter((c) => c.id !== id);
      persist(next);
      return next;
    });
    if (activeId === id) setActiveId(null);
    api.clearSession(id).catch(() => {});
  }

  function handleClearAll() {
    abortRef.current?.abort();
    abortRef.current = null;
    setSending(false);
    conversations.forEach((c) => api.clearSession(c.id).catch(() => {}));
    setConversations([]);
    persist([]);
    localStorage.removeItem(ACTIVE_KEY);
    setActiveId(null);
  }

  useEffect(() => {
    const q = params.get("q");
    if (q && !sending && messages.length === 0) void send(q);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  const metas: ConversationMeta[] = conversations.map(({ id, title, createdAt }) => ({
    id, title, createdAt,
  }));

  const panelOpen = activeVisuals.length > 0 && !panelClosed;

  return (
    <div className="flex h-full w-full overflow-hidden bg-bg">
      <HistorySidebar
        conversations={metas}
        activeId={activeId}
        onNew={handleNew}
        onSelect={handleSelect}
        onDelete={handleDelete}
        onClearAll={handleClearAll}
        collapsed={historyCollapsed}
        onToggleCollapse={() => setHistoryCollapsed((p) => !p)}
      />

      <div className="flex flex-1 overflow-hidden min-w-0">

        {/* ── Chat column ──────────────────────────────────────────── */}
        <div className="flex flex-1 flex-col overflow-hidden min-w-0">

          <div ref={scrollRef} className="flex-1 overflow-y-auto">
            {messages.length === 0 && !sending ? (
              <div className="flex h-full items-center justify-center px-8 py-16">
                <div className="w-full max-w-2xl">
                  <Suggestions onPick={send} />
                </div>
              </div>
            ) : (
              <div className="px-8 py-8 space-y-3">
                {messages.map((m, i) => {
                  const hasV = visualMsgIdxSet.has(i);
                  // This message's visuals are "active" when panel is open and pinned here
                  const isActive = hasV && panelOpen && effectiveIdx === i;
                  return (
                    <MessageBubble
                      key={i}
                      message={m}
                      visualsActive={isActive}
                      onShowVisuals={hasV ? () => {
                        if (isActive) {
                          // Toggle off — close panel
                          setPanelClosed(true);
                        } else {
                          // Open panel with this message's snapshot
                          setPinnedMsgIdx(i);
                          setPanelClosed(false);
                        }
                      } : undefined}
                    />
                  );
                })}
                {sending && messages[messages.length - 1]?.role !== "assistant" && (
                  <TypingIndicator status={statusText} />
                )}
              </div>
            )}
          </div>

          <div className="px-8 py-4" style={{ borderTop: "1px solid var(--border-subtle)", background: "var(--bg)" }}>
            <ChatInput
              onSubmit={send}
              disabled={sending}
              onFocus={() => {
                setHistoryCollapsed(true);
                setPanelClosed(true);
                window.dispatchEvent(new CustomEvent("nrc:chat-focus"));
              }}
            />
            <p className="mt-2 text-center text-[11px] text-fg-dim">
              Enter to send · Shift+Enter for newline · Answers grounded in the serving database
            </p>
          </div>
        </div>

        {/* ── Drag handle + Visual panel ────────────────────────── */}
        {panelOpen && (
          <>
            {/* Drag handle — grab and pull to resize the panel */}
            <div
              className="shrink-0 cursor-col-resize select-none group flex items-center justify-center"
              style={{ width: "8px", background: "var(--border-subtle)" }}
              onMouseDown={handleDragStart}
            >
              <div
                className="w-0.5 h-8 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
                style={{ background: "var(--border)" }}
              />
            </div>

            <VisualPanel
              visuals={activeVisuals}
              width={panelWidth}
              isHistorical={isHistorical}
              onClose={() => setPanelClosed(true)}
            />
          </>
        )}
      </div>
    </div>
  );
}

export default function ChatPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-full w-full items-center justify-center text-[13px] text-fg-muted">
          Loading…
        </div>
      }
    >
      <ChatPageInner />
    </Suspense>
  );
}
