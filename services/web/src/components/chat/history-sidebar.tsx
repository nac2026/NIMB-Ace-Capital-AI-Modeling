"use client";

import Link from "next/link";
import {
  Activity, LayoutGrid, MessageSquare, SquarePen, Trash2, X,
  PanelLeftClose, PanelLeft,
} from "lucide-react";
import { cn } from "@/lib/utils";

export type ConversationMeta = {
  id: string;
  title: string;
  createdAt: number;
};

type Group = { label: string; items: ConversationMeta[] };

function groupByDate(convos: ConversationMeta[]): Group[] {
  const DAY = 86_400_000;
  const now = Date.now();
  const today: ConversationMeta[] = [];
  const yesterday: ConversationMeta[] = [];
  const older: ConversationMeta[] = [];

  for (const c of convos) {
    const age = now - c.createdAt;
    if (age < DAY) today.push(c);
    else if (age < 2 * DAY) yesterday.push(c);
    else older.push(c);
  }

  const groups: Group[] = [];
  if (today.length)     groups.push({ label: "Today",     items: today });
  if (yesterday.length) groups.push({ label: "Yesterday", items: yesterday });
  if (older.length)     groups.push({ label: "Earlier",   items: older });
  return groups;
}

export function HistorySidebar({
  conversations,
  activeId,
  onNew,
  onSelect,
  onDelete,
  onClearAll,
  collapsed,
  onToggleCollapse,
}: {
  conversations: ConversationMeta[];
  activeId: string | null;
  onNew: () => void;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onClearAll: () => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
}) {
  const sorted = [...conversations].sort((a, b) => b.createdAt - a.createdAt);
  const groups = groupByDate(sorted);

  // ── Collapsed rail ───────────────────────────────────────────────────
  if (collapsed) {
    return (
      <aside className="flex h-full w-[44px] shrink-0 flex-col items-center border-r border-border-subtle bg-bg-subtle py-2 transition-[width] duration-200">
        <RailButton label="Expand history" onClick={onToggleCollapse}>
          <PanelLeft className="h-[14px] w-[14px]" strokeWidth={1.75} />
        </RailButton>
        <div className="mt-1">
          <RailButton label="New chat" onClick={onNew}>
            <SquarePen className="h-[14px] w-[14px]" strokeWidth={1.75} />
          </RailButton>
        </div>
        <div className="my-2 h-px w-6" style={{ background: "var(--border-subtle)" }} />
        <div className="flex flex-1 flex-col gap-0.5 px-1">
          {sorted.slice(0, 10).map((c) => (
            <RailButton
              key={c.id}
              label={c.title}
              onClick={() => onSelect(c.id)}
              active={activeId === c.id}
            >
              <MessageSquare className="h-[12px] w-[12px]" strokeWidth={1.75} />
            </RailButton>
          ))}
        </div>
      </aside>
    );
  }

  // ── Expanded ────────────────────────────────────────────────────────
  return (
    <aside className="flex h-full w-[240px] shrink-0 flex-col border-r border-border-subtle bg-bg-subtle transition-[width] duration-200">

      {/* Header */}
      <div className="flex h-[52px] shrink-0 items-center justify-between border-b border-border-subtle px-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[12px] font-semibold uppercase tracking-wider text-fg-muted truncate">History</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={onNew}
            title="New chat"
            className="flex h-7 w-7 items-center justify-center rounded-md text-fg-muted transition-colors hover:bg-bg-hover hover:text-fg"
          >
            <SquarePen className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={onToggleCollapse}
            title="Collapse history"
            aria-label="Collapse chat history"
            className="flex h-7 w-7 items-center justify-center rounded-md text-fg-muted transition-colors hover:bg-bg-hover hover:text-fg"
          >
            <PanelLeftClose className="h-[14px] w-[14px]" strokeWidth={1.75} />
          </button>
        </div>
      </div>

      {/* Conversation list */}
      <div className="flex-1 overflow-y-auto px-3 pb-2 pt-3">
        {activeId === null && (
          <div
            className="mb-3 flex items-center gap-2 rounded-xl px-3 py-2.5"
            style={{ background: "var(--bg-panel)", boxShadow: "var(--shadow-sm)" }}
          >
            <SquarePen className="h-3.5 w-3.5 shrink-0 text-fg-muted" />
            <span className="text-[13px] font-medium text-fg">New conversation</span>
          </div>
        )}

        {conversations.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 py-8 text-center">
            <MessageSquare className="h-8 w-8 text-fg-dim opacity-40" />
            <p className="text-[12px] text-fg-dim">No past conversations</p>
          </div>
        ) : (
          groups.map((g) => (
            <div key={g.label} className="mb-5">
              <p className="mb-1.5 px-2 text-[10px] font-semibold uppercase tracking-widest text-fg-dim">
                {g.label}
              </p>
              <div className="space-y-0.5">
                {g.items.map((c) => (
                  <ConvoRow
                    key={c.id}
                    convo={c}
                    active={c.id === activeId}
                    onSelect={() => onSelect(c.id)}
                    onDelete={() => onDelete(c.id)}
                  />
                ))}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Footer */}
      <div className="px-3 pb-4 pt-2 space-y-0.5" style={{ borderTop: "1px solid var(--border-subtle)" }}>
        <Link
          href="/dashboard"
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-[12px] text-fg-dim transition-all duration-150 hover:bg-bg-hover hover:text-fg"
        >
          <LayoutGrid className="h-3.5 w-3.5" />
          Dashboard
        </Link>
        <Link
          href="/live"
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-[12px] text-fg-dim transition-all duration-150 hover:bg-bg-hover hover:text-fg"
        >
          <Activity className="h-3.5 w-3.5" />
          Live Market
        </Link>
        {conversations.length > 0 && (
          <button
            onClick={onClearAll}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-[12px] text-fg-dim transition-all duration-150 hover:bg-bg-hover hover:text-err"
          >
            <Trash2 className="h-3.5 w-3.5" />
            Clear all history
          </button>
        )}
      </div>
    </aside>
  );
}

function RailButton({
  label,
  onClick,
  active,
  children,
}: {
  label: string;
  onClick: () => void;
  active?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      className={cn(
        "group relative flex h-7 w-7 items-center justify-center rounded-md transition-colors",
        active ? "bg-bg-panel text-fg shadow-sm" : "text-fg-muted hover:bg-bg-hover hover:text-fg",
      )}
    >
      {children}
      <span
        role="tooltip"
        className="pointer-events-none absolute left-full top-1/2 z-50 ml-2 -translate-y-1/2 -translate-x-1 max-w-[260px] truncate whitespace-nowrap rounded-md px-2 py-1 text-[11px] font-medium opacity-0 transition-[opacity,transform] duration-150 ease-out delay-150 group-hover:translate-x-0 group-hover:opacity-100"
        style={{ background: "var(--fg)", color: "var(--bg)", boxShadow: "var(--shadow-md)" }}
      >
        {label}
      </span>
    </button>
  );
}

function ConvoRow({
  convo,
  active,
  onSelect,
  onDelete,
}: {
  convo: ConversationMeta;
  active: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  return (
    <div
      onClick={onSelect}
      className={cn(
        "group flex cursor-pointer items-center gap-2 rounded-xl px-3 py-2.5 transition-all duration-150",
        active
          ? "bg-bg-panel text-fg shadow-sm"
          : "text-fg-muted hover:bg-bg-panel/70 hover:text-fg",
      )}
      style={active ? { boxShadow: "var(--shadow-sm)" } : undefined}
    >
      <span className="min-w-0 flex-1 truncate text-[13px] leading-5 font-medium">
        {convo.title}
      </span>
      <button
        onClick={(e) => { e.stopPropagation(); onDelete(); }}
        className="shrink-0 rounded-md p-0.5 opacity-0 transition-all duration-150 group-hover:opacity-100 hover:bg-bg-hover hover:text-err"
        aria-label="Delete"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
