"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { List, type RowComponentProps } from "react-window";
import { Search, Circle } from "lucide-react";
import { useMarketStream, type LiveTick } from "@/hooks/use-market-stream";
import { ScripRow, COL_CLS } from "@/components/dashboard/scrip-row";

const ROW_HEIGHT = 44;

// Row renderer for react-window v2.
// RowData is the custom data passed via rowProps={{ rows }}.
// index + style are injected by the List itself.
type RowData = { rows: LiveTick[] };
function TickRow({ rows, index, style }: RowComponentProps<RowData>) {
  const tick = rows[index];
  if (!tick) return null;
  return <ScripRow tick={tick} style={style} />;
}

export default function LiveMarketPage() {
  const [search, setSearch] = useState("");
  const [subScrips, setSubScrips] = useState<string[] | undefined>(undefined);

  const { prices, lastTickAt, connected, isStale } = useMarketStream(subScrips);

  const rows = useMemo(() => {
    const entries = Array.from(prices.values());
    const q = search.trim().toUpperCase();
    const filtered = q ? entries.filter((t) => t.scrip.includes(q)) : entries;
    return filtered.sort((a, b) => a.scrip.localeCompare(b.scrip));
  }, [prices, search]);

  // Viewport-aware subscription: debounce 500ms after scroll settles.
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onRowsRendered = useCallback(
    (visibleRows: { startIndex: number; stopIndex: number }) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        const visible = rows
          .slice(visibleRows.startIndex, visibleRows.stopIndex + 1)
          .map((r) => r.scrip);
        if (visible.length > 0) setSubScrips(visible);
      }, 500);
    },
    [rows],
  );

  const lastTickStr = lastTickAt
    ? new Date(lastTickAt).toLocaleTimeString("en-IN", {
        hour: "2-digit", minute: "2-digit", second: "2-digit",
      })
    : null;

  const status = !connected
    ? { label: "Connecting…", color: "var(--fg-dim)", dot: false }
    : isStale
    ? { label: "Stale", color: "var(--warn)", dot: false }
    : { label: "Live", color: "var(--ok)", dot: true };

  return (
    <div className="flex h-full flex-col overflow-hidden">

      {/* ── Page header ──────────────────────────────────────────────── */}
      <header
        className="flex shrink-0 items-center gap-4 px-6 py-3"
        style={{ borderBottom: "1px solid var(--border-subtle)", background: "var(--bg-panel)" }}
      >
        <span className="font-semibold text-[14px] text-fg">Live Market</span>

        <div
          className="flex items-center gap-2 rounded-xl px-3 py-1.5"
          style={{ background: "var(--bg-subtle)", border: "1px solid var(--border-subtle)" }}
        >
          <Search size={13} className="text-fg-dim shrink-0" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter scrip…"
            className="bg-transparent text-[13px] text-fg placeholder:text-fg-dim outline-none w-32"
          />
        </div>

        <div className="flex-1" />

        <div className="flex items-center gap-2 text-[12px]" style={{ color: status.color }}>
          {status.dot ? (
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ background: "var(--ok)", boxShadow: "0 0 0 2px rgba(22,163,74,0.25)" }}
            />
          ) : (
            <Circle size={8} />
          )}
          <span className="font-medium">{status.label}</span>
          {lastTickStr && <span className="text-fg-dim">· {lastTickStr}</span>}
        </div>
      </header>

      {/* ── Column header — stays above the virtual list ─────────────── */}
      <div
        className="flex shrink-0 items-center text-[11px] font-semibold uppercase tracking-wider text-fg-muted"
        style={{ background: "var(--bg-subtle)", borderBottom: "1px solid var(--border-subtle)" }}
      >
        <div className={`${COL_CLS.scrip} py-2.5`}>Scrip</div>
        <div className={`${COL_CLS.price} py-2.5`}>Price (NPR)</div>
        <div className={`${COL_CLS.chgPct} py-2.5`}>Chg %</div>
        <div className={`${COL_CLS.chgAbs} py-2.5`}>Chg NPR</div>
        <div className={`${COL_CLS.volume} py-2.5`}>Volume</div>
        <div className={`${COL_CLS.turnover} py-2.5`}>Turnover</div>
        <div className={`${COL_CLS.trend} py-2.5`}>Trend</div>
      </div>

      {/* ── Virtualized row area ──────────────────────────────────────── */}
      <div className="flex-1" style={{ overflow: "hidden", position: "relative" }}>
        {prices.size === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-[13px] text-fg-dim">
            {connected ? (
              <>
                <p>Waiting for ticks…</p>
                <p className="text-[12px]">
                  Start the simulator:&nbsp;
                  <code className="rounded bg-bg-subtle px-2 py-0.5 font-mono text-[11px] text-fg-muted">
                    uv run nrc-simulate --all-banks
                  </code>
                </p>
              </>
            ) : (
              <p>Connecting to live feed…</p>
            )}
          </div>
        ) : rows.length === 0 ? (
          <div className="flex h-full items-center justify-center text-[13px] text-fg-dim">
            No scrips match &ldquo;{search}&rdquo;
          </div>
        ) : (
          <List
            rowCount={rows.length}
            rowHeight={ROW_HEIGHT}
            rowComponent={TickRow}
            rowProps={{ rows }}
            onRowsRendered={onRowsRendered}
            overscanCount={5}
            style={{ width: "100%", height: "100%" }}
          />
        )}
      </div>

      {/* ── Footer ───────────────────────────────────────────────────── */}
      <footer
        className="shrink-0 px-6 py-2 text-[11px] text-fg-dim"
        style={{ borderTop: "1px solid var(--border-subtle)" }}
      >
        {prices.size} scrip{prices.size !== 1 ? "s" : ""}
        {subScrips && ` · ${subScrips.length} visible`}
        &nbsp;· Simulated intraday ticks
      </footer>
    </div>
  );
}
