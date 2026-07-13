"use client";

// Persistent right-side chat drawer mounted inside (main)/layout.tsx.
// Shares localStorage with /chat history page (same STORE_KEY) so opening
// the drawer on /scrip/NABIL continues the same session the user started on
// the full chat page.
//
// Width + collapsed state persist per-user; context (current scrip / scrips /
// screen) flows from usePageContext() into every chatStream request so the
// agent prepends a "user is viewing NABIL" line to its system prompt.

import { useEffect, useMemo, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { usePathname, useRouter } from "next/navigation";
import { MessageSquare, Plus, X, ExternalLink } from "lucide-react";
import { api, type PageContext } from "@/lib/api";
import { usePageContext } from "@/lib/use-page-context";
import { Message, MessageBubble, extractVisuals } from "@/components/chat/message-bubble";
import { ChatInput } from "@/components/chat/chat-input";

const STORE_KEY = "nrc.conversations";
const ACTIVE_KEY = "nrc.session_id";
const DRAWER_OPEN_KEY = "nrc.drawer_open";

const PANEL_WIDTH = 400;

type Conversation = {
  id: string;
  title: string;
  createdAt: number;
  messages: Message[];
};

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

function contextLabel(ctx: PageContext | null): string | null {
  if (!ctx) return null;
  if (ctx.current_scrip) return `Viewing ${ctx.current_scrip}`;
  if (ctx.current_scrips?.length) return `Comparing ${ctx.current_scrips.join(" · ")}`;
  if (ctx.current_screen) return `Screen: ${ctx.current_screen.replace(/-/g, " ")}`;
  return null;
}

export function ChatDrawer() {
  const ctx = usePageContext();
  const pathname = usePathname();
  const router = useRouter();
  // /chat is the full-page chat viewer; the drawer would be a duplicate there.
  const hidden = pathname === "/chat";

  const [open, setOpen] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [statusText, setStatusText] = useState("");

  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Hydrate drawer state + conversations from localStorage
  useEffect(() => {
    const o = localStorage.getItem(DRAWER_OPEN_KEY);
    if (o !== null) setOpen(o === "1");

    const stored = loadConversations();
    setConversations(stored);
    const lastId = localStorage.getItem(ACTIVE_KEY);
    if (lastId && stored.some((c) => c.id === lastId)) setActiveId(lastId);

    setHydrated(true);
  }, []);

  useEffect(() => {
    if (hydrated) localStorage.setItem(DRAWER_OPEN_KEY, open ? "1" : "0");
  }, [open, hydrated]);

  useEffect(() => {
    if (activeId) localStorage.setItem(ACTIVE_KEY, activeId);
  }, [activeId]);

  const messages = useMemo(
    () => conversations.find((c) => c.id === activeId)?.messages ?? [],
    [conversations, activeId],
  );

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, sending]);

  // Cmd+/ focuses drawer input (and opens drawer if closed)
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "/") {
        e.preventDefault();
        setOpen(true);
        // Defer until after state flush so the textarea is actually mounted
        requestAnimationFrame(() => {
          const ta = document.querySelector<HTMLTextAreaElement>('[data-drawer-input] textarea');
          ta?.focus();
        });
      }
      if (e.key === "Escape" && open && !sending) {
        const active = document.activeElement as HTMLElement | null;
        if (active?.tagName === "TEXTAREA" || active?.tagName === "INPUT") return;
        setOpen(false);
      }
    }
    // "Ask Copilot" buttons (e.g. the company hero) dispatch this event.
    function onOpenCopilot() {
      setOpen(true);
      requestAnimationFrame(() => {
        const ta = document.querySelector<HTMLTextAreaElement>('[data-drawer-input] textarea');
        ta?.focus();
      });
    }
    window.addEventListener("keydown", onKey);
    window.addEventListener("nrc:open-copilot", onOpenCopilot);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("nrc:open-copilot", onOpenCopilot);
    };
  }, [open, sending]);

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
      ctx,
    );
    abortRef.current = ctrl;
  }

  function handleNew() {
    abortRef.current?.abort();
    abortRef.current = null;
    setSending(false);
    setActiveId(null);
  }

  const label = contextLabel(ctx);

  // On /chat the drawer would be a duplicate of the page itself.
  if (hidden) return null;

  // Floating launcher — a little copilot button pinned to the bottom-right.
  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-5 right-5 z-40 flex h-14 w-14 items-center justify-center rounded-full transition-transform hover:scale-105"
        style={{ background: "var(--accent)", color: "var(--bg)", boxShadow: "0 6px 24px rgba(0,0,0,.28)" }}
        title="Ask the research copilot (⌘/)"
        aria-label="Open research copilot"
      >
        <MessageSquare className="h-6 w-6" strokeWidth={1.9} />
      </button>
    );
  }

  // Floating chat panel — overlays the bottom-right corner; does not push content.
  return (
    <div
      className="fixed bottom-5 right-5 z-40 flex flex-col overflow-hidden rounded-2xl border"
      style={{
        width: `min(${PANEL_WIDTH}px, calc(100vw - 40px))`,
        height: "min(680px, calc(100vh - 96px))",
        borderColor: "var(--border-subtle)",
        background: "var(--bg)",
        boxShadow: "0 12px 40px rgba(0,0,0,.34)",
      }}
    >
      {/* Header */}
      <div
        className="flex h-[52px] items-center justify-between border-b px-3"
        style={{ borderColor: "var(--border-subtle)" }}
      >
        <div className="flex min-w-0 items-center gap-2">
          <MessageSquare className="h-[14px] w-[14px] shrink-0 text-fg-muted" strokeWidth={1.75} />
          <div className="min-w-0">
            <div className="truncate text-[13px] font-medium text-fg">Research chat</div>
            {label ? (
              <div className="truncate text-[10.5px] uppercase tracking-wide text-fg-dim">{label}</div>
            ) : null}
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => router.push("/chat")}
            className="flex h-7 w-7 items-center justify-center rounded-md text-fg-muted transition-colors hover:bg-bg-hover hover:text-fg"
            title="Open in full page"
            aria-label="Open in full page"
          >
            <ExternalLink className="h-[14px] w-[14px]" strokeWidth={1.75} />
          </button>
          <button
            onClick={handleNew}
            disabled={!activeId && messages.length === 0}
            className="flex h-7 w-7 items-center justify-center rounded-md text-fg-muted transition-colors hover:bg-bg-hover hover:text-fg disabled:opacity-40"
            title="New conversation"
            aria-label="New conversation"
          >
            <Plus className="h-[14px] w-[14px]" strokeWidth={1.75} />
          </button>
          <button
            onClick={() => setOpen(false)}
            className="flex h-7 w-7 items-center justify-center rounded-md text-fg-muted transition-colors hover:bg-bg-hover hover:text-fg"
            title="Close (Esc)"
            aria-label="Close chat"
          >
            <X className="h-[14px] w-[14px]" strokeWidth={1.75} />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        {messages.length === 0 && !sending ? (
          <DrawerEmpty ctx={ctx} onPick={send} />
        ) : (
          <div className="px-3 py-4 space-y-3">
            {messages.map((m, i) => {
              const hasVisuals = m.role === "assistant" && extractVisuals(m.content).visuals.length > 0;
              return (
                <MessageBubble
                  key={i}
                  message={m}
                  onShowVisuals={hasVisuals ? () => router.push("/chat") : undefined}
                />
              );
            })}
            {sending && messages[messages.length - 1]?.role !== "assistant" && (
              <DrawerThinking status={statusText} />
            )}
          </div>
        )}
      </div>

      {/* Input */}
      <div
        data-drawer-input
        className="px-3 py-3"
        style={{ borderTop: "1px solid var(--border-subtle)" }}
      >
        <ChatInput onSubmit={send} disabled={sending} />
        <p className="mt-1.5 px-1 text-[10px] text-fg-dim">
          ⌘/ to focus · Esc to close
        </p>
      </div>
    </div>
  );
}

// ── Drawer-specific empty state ─────────────────────────────────────────
function DrawerEmpty({
  ctx,
  onPick,
}: {
  ctx: PageContext | null;
  onPick: (query: string) => void;
}) {
  const prompts: string[] = [];
  if (ctx?.current_scrip) {
    const s = ctx.current_scrip;
    prompts.push(
      `Summarize ${s}'s fundamentals`,
      `How is ${s}'s NPL trending?`,
      `Is ${s} cheap vs its own history?`,
      `Show ${s}'s Piotroski signals`,
    );
  } else if (ctx?.current_scrips?.length) {
    const cs = ctx.current_scrips;
    prompts.push(
      `Compare ${cs.join(" vs ")} on asset quality`,
      `Which has the best composite score?`,
      `Who has the highest dividend yield?`,
    );
  } else if (ctx?.current_screen) {
    prompts.push(
      `Explain this screen`,
      `What stands out in this list?`,
    );
  } else {
    prompts.push(
      "Top-quality banks by composite score",
      "Which banks are cheap vs their own history?",
      "Asset-quality leaders in the universe",
      "Highest dividend yields right now",
    );
  }

  return (
    <div className="flex h-full flex-col justify-end px-3 pb-4">
      <div className="mb-2 text-[10.5px] uppercase tracking-wide text-fg-dim">Try</div>
      <div className="space-y-1.5">
        {prompts.map((p) => (
          <button
            key={p}
            onClick={() => onPick(p)}
            className="w-full rounded-lg px-3 py-2 text-left text-[12.5px] text-fg-muted transition-colors hover:bg-bg-hover hover:text-fg"
            style={{ border: "1px solid var(--border-subtle)" }}
          >
            {p}
          </button>
        ))}
      </div>
    </div>
  );
}

function DrawerThinking({ status }: { status: string }) {
  return (
    <div className="flex items-center gap-2 px-1 text-[12px] text-fg-muted">
      <span className="thinking-dot" style={{ animationDelay: "0ms" }} />
      <span className="thinking-dot" style={{ animationDelay: "160ms" }} />
      <span className="thinking-dot" style={{ animationDelay: "320ms" }} />
      <span>{status || "Thinking…"}</span>
    </div>
  );
}
