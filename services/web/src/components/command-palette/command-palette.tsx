"use client";

// Global ⌘K overlay. Four command kinds:
//   - Search    (scrip search → navigate to /scrip/[symbol])
//   - Navigate  (dashboard, compare, screen/*, chat)
//   - Ask       (push the query into chat via /chat?q=)
//   - Run       (multi-step shorthand: "compare NABIL and NICA" etc.)
//
// Context-aware: if current page is /scrip/NABIL, the "Ask" default text
// references NABIL. Mounted once at the app shell level.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  Search, LayoutGrid, GitCompareArrows, MessageSquare, Activity, Filter,
  ArrowRight, Sparkles,
} from "lucide-react";
import { api } from "@/lib/api";
import { usePageContext } from "@/lib/use-page-context";
import { cn } from "@/lib/utils";

type CommandItem = {
  id: string;
  type: "search" | "navigate" | "ask" | "run";
  label: string;
  hint?: string;
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  onPick: () => void;
};

const NAV_ITEMS: Array<{ href: string; label: string; icon: CommandItem["icon"] }> = [
  { href: "/dashboard",            label: "Dashboard",       icon: LayoutGrid },
  { href: "/compare",              label: "Compare",         icon: GitCompareArrows },
  { href: "/screen/top-quality",   label: "Screen: Top quality",     icon: Filter },
  { href: "/screen/cheap-vs-self", label: "Screen: Cheap vs own",    icon: Filter },
  { href: "/screen/high-yield",    label: "Screen: High yield",      icon: Filter },
  { href: "/screen/contrarian",    label: "Screen: Contrarian bets", icon: Filter },
  { href: "/screen/turnaround",    label: "Screen: Turnaround",      icon: Filter },
  { href: "/chat",                 label: "Chat history",    icon: MessageSquare },
  { href: "/live",                 label: "Live market",     icon: Activity },
];

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlightIdx, setHighlightIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const router = useRouter();
  const pathname = usePathname();
  const ctx = usePageContext();

  const universe = useQuery({
    queryKey: ["universe"],
    queryFn: api.universe,
    staleTime: 60_000,
  });

  // Global shortcut: ⌘K or Ctrl+K
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(true);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Close + reset on pathname change
  useEffect(() => { setOpen(false); }, [pathname]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setHighlightIdx(0);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  const handleClose = useCallback(() => setOpen(false), []);

  const items: CommandItem[] = useMemo(() => {
    const out: CommandItem[] = [];
    const q = query.trim().toLowerCase();

    // 1. Scrip matches (search). Show even with empty query (top 6 scrips).
    const rows = (universe.data ?? []);
    const scripMatches = q
      ? rows.filter((r) => r.scrip.toLowerCase().includes(q) || r.company_name.toLowerCase().includes(q))
      : rows;
    scripMatches.slice(0, 6).forEach((r) => {
      out.push({
        id: `scrip-${r.scrip}`,
        type: "search",
        label: r.scrip,
        hint: r.company_name,
        icon: Search,
        onPick: () => {
          router.push(`/scrip/${r.scrip}`);
          handleClose();
        },
      });
    });

    // 2. Navigation items (filtered by query)
    NAV_ITEMS.forEach((n) => {
      if (q && !n.label.toLowerCase().includes(q)) return;
      out.push({
        id: `nav-${n.href}`,
        type: "navigate",
        label: n.label,
        hint: n.href,
        icon: n.icon,
        onPick: () => {
          router.push(n.href);
          handleClose();
        },
      });
    });

    // 3. Ask command — always present if query is non-empty, framed with
    //    current page context when we have one.
    if (q) {
      let askLabel = `Ask chat: "${query.trim()}"`;
      if (ctx?.current_scrip) askLabel += ` (about ${ctx.current_scrip})`;
      out.push({
        id: "ask",
        type: "ask",
        label: askLabel,
        icon: Sparkles,
        onPick: () => {
          router.push(`/chat?q=${encodeURIComponent(query.trim())}`);
          handleClose();
        },
      });
    }

    // 4. Run: "compare X and Y" / "compare X, Y, Z"
    if (q.startsWith("compare ")) {
      const tail = query.trim().slice(8);
      const tokens = tail.split(/[,\s]+|and|vs/i).map((t) => t.trim().toUpperCase()).filter(Boolean);
      if (tokens.length >= 2) {
        out.push({
          id: "run-compare",
          type: "run",
          label: `Compare ${tokens.join(" vs ")}`,
          icon: GitCompareArrows,
          onPick: () => {
            router.push(`/compare?scrips=${encodeURIComponent(tokens.slice(0, 5).join(","))}`);
            handleClose();
          },
        });
      }
    }

    return out;
  }, [query, universe.data, ctx?.current_scrip, router, handleClose]);

  // Keyboard navigation within the list
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (!open) return;
      if (e.key === "Escape") { handleClose(); return; }
      if (e.key === "ArrowDown") { e.preventDefault(); setHighlightIdx((i) => Math.min(items.length - 1, i + 1)); }
      if (e.key === "ArrowUp")   { e.preventDefault(); setHighlightIdx((i) => Math.max(0, i - 1)); }
      if (e.key === "Enter") {
        e.preventDefault();
        items[highlightIdx]?.onPick();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, items, highlightIdx, handleClose]);

  // Reset highlight when items list shrinks
  useEffect(() => {
    if (highlightIdx >= items.length) setHighlightIdx(Math.max(0, items.length - 1));
  }, [items.length, highlightIdx]);

  if (!open) return null;

  // Group items by type for section headers
  const groups: Record<string, CommandItem[]> = {};
  items.forEach((it) => {
    const key = it.type === "search" ? "Scrips" :
                it.type === "navigate" ? "Navigate" :
                it.type === "ask" ? "Ask" :
                "Run";
    if (!groups[key]) groups[key] = [];
    groups[key].push(it);
  });

  let running = 0;
  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[12vh] animate-fade-in"
      style={{ background: "rgba(0,0,0,0.35)" }}
      onClick={handleClose}
    >
      <div
        className="w-[560px] max-w-[92vw] overflow-hidden rounded-xl"
        style={{ background: "var(--bg-panel)", border: "1px solid var(--border)", boxShadow: "var(--shadow-md, 0 20px 40px rgba(0,0,0,0.18))" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          className="flex items-center gap-3 px-4 py-3"
          style={{ borderBottom: "1px solid var(--border-subtle)" }}
        >
          <Search className="h-4 w-4 text-fg-muted" strokeWidth={2} />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search scrip, navigate, ask chat…"
            className="flex-1 bg-transparent text-[14px] text-fg outline-none placeholder:text-fg-dim"
          />
          <kbd className="rounded-md border border-border-subtle px-1.5 py-0.5 text-[10.5px] font-semibold text-fg-dim">Esc</kbd>
        </div>

        <div ref={listRef} className="max-h-[60vh] overflow-y-auto py-1">
          {items.length === 0 ? (
            <div className="py-10 text-center text-[12.5px] text-fg-muted">No matches</div>
          ) : (
            Object.entries(groups).map(([group, gi]) => (
              <div key={group} className="px-1 py-1">
                <div className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-fg-dim">{group}</div>
                {gi.map((it) => {
                  const idx = running++;
                  const isActive = idx === highlightIdx;
                  const Icon = it.icon;
                  return (
                    <button
                      key={it.id}
                      onMouseMove={() => setHighlightIdx(idx)}
                      onClick={() => it.onPick()}
                      className={cn(
                        "flex w-full items-center gap-3 rounded-md px-3 py-2 text-left transition-colors",
                        isActive ? "bg-bg-hover text-fg" : "text-fg-muted hover:bg-bg-hover hover:text-fg",
                      )}
                    >
                      <Icon className="h-[14px] w-[14px] shrink-0" strokeWidth={1.75} />
                      <div className="flex-1 min-w-0">
                        <div className="truncate text-[13px] font-medium text-fg">{it.label}</div>
                        {it.hint && (
                          <div className="truncate text-[11px] text-fg-dim">{it.hint}</div>
                        )}
                      </div>
                      {isActive && <ArrowRight className="h-3 w-3 text-fg-muted" strokeWidth={2} />}
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>

        <div
          className="flex items-center justify-between px-3 py-2 text-[10.5px] text-fg-dim"
          style={{ borderTop: "1px solid var(--border-subtle)", background: "var(--bg-subtle)" }}
        >
          <div className="flex items-center gap-2">
            <kbd className="rounded border border-border-subtle bg-bg px-1 py-0.5">↑↓</kbd>
            navigate
            <kbd className="rounded border border-border-subtle bg-bg px-1 py-0.5">↵</kbd>
            select
          </div>
          <div>⌘K to toggle</div>
        </div>
      </div>
    </div>
  );
}
