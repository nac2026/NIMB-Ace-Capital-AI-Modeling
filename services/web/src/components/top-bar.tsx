"use client";
// Top bar — Dark Intelligence Terminal shell: brand, module Launcher dropdown,
// global company search (→ /scrip/[sym]), theme toggle, alerts. Replaces the
// old left sidebar. The right-side ChatDrawer is the design's research chat.

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  LayoutGrid, Building2, MessageSquare, FileSearch, GitCompareArrows,
  Activity, Database, Search, Bell, ChevronRight, Check, BellRing, ShieldAlert, FileUp,
} from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useTheme } from "@/components/theme/theme-provider";

type Mod = { id: string; href: string; name: string; sub: string; Icon: React.ComponentType<{ className?: string; strokeWidth?: number }> };

const MODULES: Mod[] = [
  { id: "dashboard",   href: "/dashboard",         name: "Market Intelligence", sub: "Dashboards · signals · surveillance", Icon: LayoutGrid },
  { id: "company",     href: "/scrip/NABIL",       name: "Company Deep-Dive",   sub: "Search a company · full profile",     Icon: Building2 },
  { id: "chat",        href: "/chat",              name: "Research Copilot",    sub: "Grounded analytical chat",            Icon: MessageSquare },
  { id: "speculative", href: "/speculative",       name: "Speculative Analysis",sub: "Report → unbiased flag verdict",      Icon: FileSearch },
  { id: "alerts",      href: "/alerts",            name: "Surveillance Alerts", sub: "Speculation & manipulation signals",  Icon: BellRing },
  { id: "surveillance",href: "/surveillance",      name: "Trade Surveillance",  sub: "Our own fills · suspicious trades",    Icon: ShieldAlert },
  { id: "internal",    href: "/internal/file/uploads", name: "Internal Files",  sub: "Upload trade-book & strategy docs",    Icon: FileUp },
  { id: "compare",     href: "/compare",           name: "Compare",             sub: "Side-by-side scrips",                 Icon: GitCompareArrows },
  { id: "live",        href: "/live",              name: "Live Market",         sub: "Real-time ticks",                     Icon: Activity },
  { id: "data",        href: "/data-coverage",     name: "Data Coverage",       sub: "What's in the system",                Icon: Database },
];

function activeModule(pathname: string): Mod {
  if (pathname.startsWith("/scrip")) return MODULES.find((m) => m.id === "company")!;
  if (pathname.startsWith("/screen")) return MODULES.find((m) => m.id === "dashboard")!;
  const hit = MODULES.find((m) => m.id !== "company" && (pathname === m.href || pathname.startsWith(m.href)));
  return hit ?? MODULES[0];
}

function Launcher() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const cur = activeModule(pathname);
  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  return (
    <div ref={ref} className="relative">
      <button onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-3 rounded-[11px] border border-line bg-panel-2 px-3 py-2 text-fg transition-colors hover:bg-hover">
        <span className="flex h-[30px] w-[30px] items-center justify-center rounded-lg text-accent"
          style={{ background: "color-mix(in oklab, var(--accent) 18%, var(--panel-3))" }}>
          <cur.Icon className="h-[17px] w-[17px]" strokeWidth={1.8} />
        </span>
        <span className="text-left">
          <span className="eyebrow block" style={{ fontSize: 8.5 }}>Module</span>
          <span className="display block text-[13.5px] font-semibold leading-tight">{cur.name}</span>
        </span>
        <ChevronRight className={cn("ml-1 h-[15px] w-[15px] text-fg-dim transition-transform", open && "rotate-90")} strokeWidth={2} />
      </button>
      {open && (
        <div className="rise absolute left-0 top-[calc(100%+8px)] z-50 w-[340px] rounded-[14px] border border-line bg-panel p-2"
          style={{ boxShadow: "var(--shadow)" }}>
          {MODULES.map((m) => {
            const isActive = m.id === cur.id;
            return (
              <Link key={m.id} href={m.href} onClick={() => setOpen(false)}
                className={cn("mb-0.5 flex items-center gap-3 rounded-[10px] border px-3 py-[11px] transition-colors",
                  isActive ? "border-line bg-hover" : "border-transparent hover:bg-hover")}>
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[9px]"
                  style={{ background: isActive ? "color-mix(in oklab, var(--accent) 18%, var(--panel-3))" : "var(--panel-3)",
                           color: isActive ? "var(--accent)" : "var(--ink-2)" }}>
                  <m.Icon className="h-[18px] w-[18px]" strokeWidth={1.8} />
                </span>
                <span className="min-w-0">
                  <span className="display block text-[13.5px] font-semibold">{m.name}</span>
                  <span className="block text-[11px] text-fg-dim">{m.sub}</span>
                </span>
                {isActive && <Check className="ml-auto h-[15px] w-[15px] text-accent" strokeWidth={2} />}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

function GlobalSearch() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const { data } = useQuery({ queryKey: ["universe-search"], queryFn: api.universe, staleTime: 300_000 });
  const t = q.trim().toLowerCase();
  const results = (data ?? []).filter((s) =>
    t && (s.scrip.toLowerCase().includes(t) || (s.company_name ?? "").toLowerCase().includes(t) || (s.sector ?? "").toLowerCase().includes(t))
  ).slice(0, 7);
  function go(sym: string) { setQ(""); setOpen(false); router.push(`/scrip/${sym}`); }
  return (
    <div className="relative max-w-[380px] flex-1">
      <div className="flex items-center gap-2.5 rounded-[11px] border border-line bg-panel-2 px-3.5 py-[9px] text-fg-dim">
        <Search className="h-4 w-4 shrink-0" strokeWidth={1.8} />
        <input value={q} onChange={(e) => { setQ(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)}
          onKeyDown={(e) => { if (e.key === "Enter" && results[0]) go(results[0].scrip); }}
          placeholder="Search a company — NABIL, Upper Tamakoshi…"
          className="min-w-0 flex-1 bg-transparent text-[12.5px] text-fg outline-none placeholder:text-fg-dim" />
        <span className="mono rounded-[5px] border border-line px-1.5 py-px text-[10px] text-ink-3">⌘K</span>
      </div>
      {open && results.length > 0 && (
        <div className="absolute left-0 right-0 top-[calc(100%+6px)] z-[60] rounded-[13px] border border-line bg-panel p-1.5"
          style={{ boxShadow: "var(--shadow)" }}>
          {results.map((s) => (
            <button key={s.scrip} onMouseDown={() => go(s.scrip)}
              className="flex w-full items-center gap-2.5 rounded-[9px] px-2.5 py-2 text-left text-fg hover:bg-hover">
              <span className="mono w-14 text-[12px] font-semibold">{s.scrip}</span>
              <span className="flex-1 truncate text-[12px] text-fg-muted">{s.company_name}</span>
              <span className="eyebrow shrink-0">{s.sector}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

const SEEN_KEY = "nrc.alerts_seen_at";

function AlertsBell() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const [seenAt, setSeenAt] = useState<number>(0);

  const q = useQuery({
    queryKey: ["alerts-recent"],
    queryFn: () => api.alerts.recent(20),
    refetchInterval: 120_000,
  });
  const alerts = q.data ?? [];
  const active = alerts.filter((a) => !a.cleared_at);

  useEffect(() => {
    setSeenAt(Number(localStorage.getItem(SEEN_KEY) || 0));
  }, []);
  useEffect(() => {
    function onDoc(e: MouseEvent) { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const unseen = active.filter((a) => new Date(a.first_seen_at ?? 0).getTime() > seenAt).length;

  function toggle() {
    const next = !open;
    setOpen(next);
    if (next) {
      const now = Date.now();
      localStorage.setItem(SEEN_KEY, String(now));
      setSeenAt(now);
    }
  }

  const color = (t: string) => (t === "spec" ? "var(--neg)" : t === "conc" ? "var(--warn)" : "var(--accent-2)");

  return (
    <div ref={ref} className="relative">
      <button onClick={toggle} title="Speculation alerts"
        className="relative flex h-[38px] w-[38px] items-center justify-center rounded-[10px] border border-line bg-panel-2 text-ink-2 hover:text-fg">
        <Bell className="h-[17px] w-[17px]" strokeWidth={1.7} />
        {unseen > 0 && (
          <span className="absolute right-1.5 top-1 flex h-[15px] min-w-[15px] items-center justify-center rounded-full px-1 text-[9px] font-bold"
            style={{ background: "var(--neg)", color: "#0b0d10", border: "2px solid var(--panel)" }}>
            {unseen > 9 ? "9+" : unseen}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 top-[calc(100%+8px)] z-50 w-[360px] overflow-hidden rounded-xl border border-line bg-panel shadow-lg"
             style={{ boxShadow: "var(--shadow-lg)" }}>
          <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
            <div>
              <div className="text-[12.5px] font-semibold text-fg">Speculation alerts</div>
              <div className="eyebrow">{active.length} active · floor-sheet surveillance</div>
            </div>
            <Link href="/alerts" onClick={() => setOpen(false)} className="text-[11.5px] font-semibold" style={{ color: "var(--accent)" }}>
              View all →
            </Link>
          </div>
          <div className="max-h-[420px] overflow-y-auto">
            {q.isLoading && <div className="px-4 py-6 text-center text-[12px] text-fg-muted">Loading…</div>}
            {!q.isLoading && alerts.length === 0 && (
              <div className="px-4 py-8 text-center text-[12px] text-fg-muted">No alerts — the floor-sheet surveillance is quiet.</div>
            )}
            {alerts.map((a) => (
              <button key={a.signal_key + (a.first_seen_at ?? "")}
                onClick={() => { setOpen(false); router.push(`/scrip/${a.scrip}#floorsheet`); }}
                className="flex w-full items-start gap-3 border-b border-line-soft px-4 py-2.5 text-left hover:bg-hover"
                style={{ opacity: a.cleared_at ? 0.5 : 1 }}>
                <span className="mt-1 h-2 w-2 shrink-0 rounded-full" style={{ background: color(a.alert_type) }} />
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="mono text-[12px] font-semibold text-fg">{a.scrip}</span>
                    <span className="mono text-[9px] uppercase tracking-wide" style={{ color: color(a.alert_type) }}>{a.level}</span>
                    {a.cleared_at && <span className="text-[9px] text-fg-dim">cleared</span>}
                  </div>
                  <div className="truncate text-[11.5px] text-fg-muted">{a.title}</div>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function TopBar() {
  const { resolved, setPref } = useTheme();
  return (
    <header className="sticky top-0 z-40 flex shrink-0 items-center gap-4 border-b border-line px-5 py-3.5"
      style={{ background: "color-mix(in oklab, var(--panel) 72%, transparent)", backdropFilter: "blur(12px)" }}>
      <Link href="/dashboard" className="flex items-center gap-2.5">
        <span className="display flex h-[34px] w-[34px] items-center justify-center rounded-[9px] text-[16px] font-bold"
          style={{ background: "linear-gradient(135deg, var(--accent), color-mix(in oklab, var(--accent) 55%, var(--accent-2)))",
                   color: "#0b0d10", boxShadow: "0 2px 12px -2px color-mix(in oklab, var(--accent) 60%, transparent)" }}>N</span>
        <span className="leading-none">
          <span className="display block text-[14.5px] font-bold tracking-tight">NIMB Ace</span>
          <span className="eyebrow mt-[2px] block" style={{ fontSize: 8.5 }}>NEPSE Intelligence Portal</span>
        </span>
      </Link>
      <span className="h-[30px] w-px bg-line" />
      <Launcher />
      <GlobalSearch />
      <div className="flex-1" />
      <button onClick={() => setPref(resolved === "dark" ? "light" : "dark")} title="Toggle theme"
        className="flex h-[38px] w-[38px] items-center justify-center rounded-[10px] border border-line bg-panel-2 text-ink-2 hover:text-fg">
        {resolved === "dark"
          ? <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4"/></svg>
          : <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"/></svg>}
      </button>
      <AlertsBell />
      <span className="flex h-[34px] w-[34px] items-center justify-center rounded-full border border-line bg-panel-3 text-[12px] font-semibold text-ink-2">RT</span>
    </header>
  );
}
