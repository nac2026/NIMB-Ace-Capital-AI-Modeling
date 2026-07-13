"use client";

// Standalone documentation page. Lives OUTSIDE the (main) route group so
// no sidebar, no chat drawer, no command palette — pure reading surface.
// Opens in a new tab from the main-app sidebar.

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BookOpen, Gauge, Search as SearchIcon, ArrowUp } from "lucide-react";
import { ThemeToggle } from "@/components/theme/theme-toggle";
import { SYSTEM_SECTIONS, SystemCard } from "@/components/help/system-content";
import { METRIC_CATEGORIES, MetricCardView, type Metric } from "@/components/help/metrics-content";
import { cn } from "@/lib/utils";

type Tab = "system" | "metrics";

function HelpPageInner() {
  const [tab, setTab] = useState<Tab>("system");
  const [activeId, setActiveId] = useState<string>("");
  const [query, setQuery] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  // Read initial tab + anchor from URL (?tab=metrics#sharpe etc.)
  useEffect(() => {
    const url = new URL(window.location.href);
    const t = url.searchParams.get("tab");
    if (t === "metrics" || t === "system") setTab(t);

    const h = url.hash.slice(1);
    if (h) {
      setActiveId(h);
      // If hash is a metric slug, flip tab automatically.
      const isMetric = METRIC_CATEGORIES.some((c) => c.metrics.some((m) => m.slug === h));
      if (isMetric) setTab("metrics");
      requestAnimationFrame(() => {
        document.getElementById(h)?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    }
  }, []);

  // Write tab change to URL so the state survives copy/paste.
  useEffect(() => {
    const url = new URL(window.location.href);
    url.searchParams.set("tab", tab);
    window.history.replaceState(null, "", url.toString());
    // Reset scroll when switching tabs
    scrollRef.current?.scrollTo({ top: 0, behavior: "instant" as ScrollBehavior });
  }, [tab]);

  // Scroll-spy across whichever section list is currently visible.
  useEffect(() => {
    const root = scrollRef.current;
    if (!root) return;

    const ids = tab === "system"
      ? SYSTEM_SECTIONS.map((s) => s.id)
      : METRIC_CATEGORIES.map((c) => c.id);

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]?.target.id) setActiveId(visible[0].target.id);
      },
      { root, rootMargin: "-10% 0px -70% 0px", threshold: 0 },
    );
    ids.forEach((id) => {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, [tab]);

  const jump = useCallback((id: string) => {
    setActiveId(id);
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.hash = id;
      window.history.replaceState(null, "", url.toString());
      document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, []);

  const toTop = useCallback(() => {
    scrollRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  // ── Metric search across all categories ─────────────────────────────
  const filteredCategories = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return METRIC_CATEGORIES;
    return METRIC_CATEGORIES
      .map((c) => ({
        ...c,
        metrics: c.metrics.filter((m) =>
          m.name.toLowerCase().includes(q) ||
          (typeof m.summary === "string" && m.summary.toLowerCase().includes(q)) ||
          m.slug.toLowerCase().includes(q),
        ),
      }))
      .filter((c) => c.metrics.length > 0);
  }, [query]);

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden" style={{ background: "var(--bg)" }}>
      {/* ── Header ────────────────────────────────────────────────── */}
      <header
        className="flex h-[56px] shrink-0 items-center justify-between gap-6 px-6"
        style={{ borderBottom: "1px solid var(--border-subtle)", background: "var(--bg-panel)" }}
      >
        <div className="flex items-center gap-3 min-w-0">
          <BookOpen className="h-4 w-4 shrink-0" style={{ color: "var(--brand)" }} strokeWidth={1.75} />
          <div className="min-w-0">
            <div className="truncate text-[14px] font-semibold text-fg">
              <span style={{ color: "var(--brand)" }}>NIMB Ace</span> · Research Portal — Documentation
            </div>
            <div className="text-[10.5px] text-fg-dim uppercase tracking-widest">Internal · Training & reference</div>
          </div>
        </div>

        <nav className="flex items-center gap-1 rounded-lg p-0.5" style={{ background: "var(--bg-subtle)", border: "1px solid var(--border-subtle)" }}>
          <TabButton active={tab === "system"}  onClick={() => setTab("system")}  icon={BookOpen} label="System" />
          <TabButton active={tab === "metrics"} onClick={() => setTab("metrics")} icon={Gauge}    label="Metrics" />
        </nav>

        <div className="flex items-center gap-3">
          <ThemeToggle />
        </div>
      </header>

      {/* ── Body ─────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">
        {/* TOC */}
        <aside
          className="hidden w-[260px] shrink-0 flex-col overflow-y-auto border-r px-3 py-5 md:flex"
          style={{ borderColor: "var(--border-subtle)", background: "var(--bg-panel)" }}
        >
          <div className="mb-2 px-2 text-[10.5px] font-semibold uppercase tracking-widest text-fg-dim">
            {tab === "system" ? "System topics" : "Metric categories"}
          </div>

          {tab === "metrics" && (
            <div
              className="mb-3 flex items-center gap-2 rounded-md px-2 py-1.5"
              style={{ background: "var(--bg-subtle)", border: "1px solid var(--border-subtle)" }}
            >
              <SearchIcon className="h-3.5 w-3.5 text-fg-dim" strokeWidth={2} />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search metric…"
                className="w-full bg-transparent text-[12.5px] text-fg placeholder:text-fg-dim outline-none"
              />
            </div>
          )}

          <nav className="flex flex-col gap-px">
            {tab === "system" ? (
              SYSTEM_SECTIONS.map((s) => (
                <TocLink key={s.id} id={s.id} title={s.title} active={activeId === s.id} onPick={jump} />
              ))
            ) : (
              filteredCategories.map((c) => (
                <div key={c.id} className="mb-2">
                  <TocLink id={c.id} title={c.title} active={activeId === c.id} onPick={jump} />
                  <div className="ml-3 mt-0.5 flex flex-col gap-px">
                    {c.metrics.map((m) => (
                      <TocLink
                        key={m.slug}
                        id={m.slug}
                        title={m.name}
                        active={activeId === m.slug}
                        onPick={jump}
                        small
                      />
                    ))}
                  </div>
                </div>
              ))
            )}
          </nav>

          <div className="mt-auto px-2 pt-6 text-[10.5px] leading-relaxed text-fg-dim">
            Content lives in <code className="font-mono text-[10px]">src/components/help/</code>.
            New metric = one entry in the array. New system topic = one section.
          </div>
        </aside>

        {/* Content */}
        <main ref={scrollRef} className="relative flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[860px] px-8 py-8 pb-24">
            {tab === "system" ? <SystemTab /> : <MetricsTab categories={filteredCategories} query={query} />}
          </div>

          <button
            onClick={toTop}
            title="Back to top"
            aria-label="Back to top"
            className="fixed bottom-6 right-6 z-40 flex h-9 w-9 items-center justify-center rounded-full shadow-lg transition-opacity hover:opacity-80"
            style={{ background: "var(--fg)", color: "var(--bg)" }}
          >
            <ArrowUp className="h-4 w-4" strokeWidth={2} />
          </button>
        </main>
      </div>
    </div>
  );
}

export default function HelpPage() {
  return (
    <Suspense fallback={<div className="flex h-screen w-screen items-center justify-center text-[13px] text-fg-muted">Loading…</div>}>
      <HelpPageInner />
    </Suspense>
  );
}

// ── Sub-components ──────────────────────────────────────────────────────

function TabButton({
  active, onClick, icon: Icon, label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-3 py-1 text-[12.5px] font-medium transition-colors",
        active ? "text-fg" : "text-fg-muted hover:text-fg",
      )}
      style={active ? { background: "var(--bg-panel)", boxShadow: "var(--shadow-sm)" } : undefined}
    >
      <Icon className="h-[14px] w-[14px]" strokeWidth={1.75} />
      {label}
    </button>
  );
}

function TocLink({
  id, title, active, onPick, small,
}: {
  id: string;
  title: string;
  active: boolean;
  onPick: (id: string) => void;
  small?: boolean;
}) {
  return (
    <button
      onClick={() => onPick(id)}
      className={cn(
        "rounded-md px-2 py-1 text-left transition-colors",
        small ? "text-[11.5px] text-fg-dim hover:text-fg" : "text-[12.5px] text-fg-muted hover:bg-bg-hover hover:text-fg",
        active && !small && "bg-bg-hover text-fg",
        active && small && "text-fg font-medium",
      )}
    >
      {title}
    </button>
  );
}

function SystemTab() {
  return (
    <>
      <div className="mb-8">
        <h1 className="text-[26px] font-semibold tracking-tight text-fg">How the portal works</h1>
        <p className="mt-2 text-[13px] leading-relaxed text-fg-muted">
          Reference for using the NIMB research portal. Learn each surface, what every card means,
          and the shortcuts that speed things up.
        </p>
      </div>

      {SYSTEM_SECTIONS.map((s) => (
        <section key={s.id} id={s.id} className="mb-12 scroll-mt-4">
          <h2 className="mb-2 text-[18px] font-semibold tracking-tight text-fg">{s.title}</h2>
          <div className="mb-4 text-[13px] leading-relaxed text-fg-muted">{s.intro}</div>
          {s.items && (
            <div className="flex flex-col gap-2.5">
              {s.items.map((it, i) => (
                <SystemCard key={i} item={it} />
              ))}
            </div>
          )}
          {s.custom}
        </section>
      ))}
    </>
  );
}

function MetricsTab({ categories, query }: { categories: ReturnType<typeof filterFallback>; query: string }) {
  const hasResults = categories.length > 0;
  return (
    <>
      <div className="mb-8">
        <h1 className="text-[26px] font-semibold tracking-tight text-fg">Metric glossary</h1>
        <p className="mt-2 text-[13px] leading-relaxed text-fg-muted">
          Every metric we compute, with a plain-English definition, the formula it's derived from,
          how to read it, and the Postgres source. Use the search or the table of contents to find
          a specific one. Bookmark <code className="font-mono text-[11px]">/help?tab=metrics#npl-ratio</code>-style
          links for direct reference.
        </p>
      </div>

      {!hasResults && (
        <div
          className="rounded-lg px-4 py-8 text-center text-[13px] text-fg-muted"
          style={{ background: "var(--bg-panel)", border: "1px solid var(--border-subtle)" }}
        >
          No metrics match &ldquo;{query}&rdquo;. Try a shorter term.
        </div>
      )}

      {categories.map((c) => (
        <section key={c.id} id={c.id} className="mb-10 scroll-mt-4">
          <div className="mb-3">
            <h2 className="text-[17px] font-semibold tracking-tight text-fg">{c.title}</h2>
            {c.blurb && <p className="mt-1 text-[12.5px] text-fg-muted">{c.blurb}</p>}
          </div>
          <div className="flex flex-col gap-3">
            {c.metrics.map((m: Metric) => (
              <MetricCardView key={m.slug} metric={m} />
            ))}
          </div>
        </section>
      ))}
    </>
  );
}

// Type helper — categories returned from the search filter have the same shape.
function filterFallback() {
  return METRIC_CATEGORIES;
}
