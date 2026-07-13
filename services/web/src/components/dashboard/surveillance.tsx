"use client";

// Surveillance Watchlist + selected-stock detail — the design's Research-view
// replacement for the old "Active Universe" table. Left: a compact, sortable,
// flag-filterable scrip list. Right: the selected scrip's price chart, key
// stats and conviction gauge, with a deep-dive link.

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api, type UniverseRow } from "@/lib/api";
import { ScoreGauge, FlagPill, Spark, deriveFlag, flagColor, npr, type Flag } from "@/components/viz";
import { Sparkles } from "lucide-react";

type Sort = "score" | "chg" | "name";
type FilterFlag = "all" | Flag;

function scoreOf(r: UniverseRow): number {
  return Math.round(r.scorecard_0_100 ?? r.quality_score_0_100 ?? 50);
}

export function Surveillance() {
  const universe = useQuery({ queryKey: ["universe"], queryFn: api.universe });
  const sparks = useQuery({ queryKey: ["universe-sparklines", 30], queryFn: () => api.universeSparklines(30) });
  const [sel, setSel] = useState<string | null>(null);

  const rows = universe.data ?? [];
  // Default the detail to the highest-conviction scrip (matches the watchlist's
  // default sort) — not the arbitrary first row of the API response.
  const topScrip = useMemo(
    () => [...rows].sort((a, b) => scoreOf(b) - scoreOf(a))[0]?.scrip ?? null,
    [rows],
  );
  const selected = rows.find((r) => r.scrip === (sel ?? topScrip)) ?? null;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "340px 1fr", gap: "var(--gap)", alignItems: "start" }}>
      <Watchlist rows={rows} sel={selected?.scrip ?? null} onSel={setSel} loading={universe.isLoading} />
      <StockDetail row={selected} spark={selected ? sparks.data?.[selected.scrip] : undefined} />
    </div>
  );
}

function Watchlist({ rows, sel, onSel, loading }: { rows: UniverseRow[]; sel: string | null; onSel: (s: string) => void; loading: boolean }) {
  const [sort, setSort] = useState<Sort>("score");
  const [filter, setFilter] = useState<FilterFlag>("all");

  const view = useMemo(() => {
    let r = rows.map((x) => ({ x, flag: deriveFlag(scoreOf(x), x.change_pct) }));
    if (filter !== "all") r = r.filter((it) => it.flag === filter);
    r.sort((a, b) =>
      sort === "score" ? scoreOf(b.x) - scoreOf(a.x) : sort === "chg" ? (b.x.change_pct ?? 0) - (a.x.change_pct ?? 0) : a.x.scrip.localeCompare(b.x.scrip),
    );
    return r;
  }, [rows, sort, filter]);

  return (
    <div className="panel overflow-hidden" style={{ display: "flex", flexDirection: "column", maxHeight: 560 }}>
      <div className="flex items-start justify-between gap-3 px-4 py-3" style={{ borderBottom: "1px solid var(--line)" }}>
        <div>
          <h3 className="text-[12.5px] font-semibold uppercase tracking-wider text-fg">Surveillance Watchlist</h3>
          <p className="mt-0.5 text-[11px] text-fg-muted">{rows.length} scrips · live signals</p>
        </div>
        <div className="flex gap-1">
          {(["all", "red", "amber", "green"] as FilterFlag[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className="rounded-md px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
              style={{
                color: filter === f ? "var(--bg)" : "var(--ink-3)",
                background: filter === f ? (f === "all" ? "var(--accent)" : flagColor(f)) : "var(--panel-2)",
                border: "1px solid var(--line)",
              }}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {/* column heads */}
      <div className="grid items-center gap-2 px-4 py-2" style={{ gridTemplateColumns: "1.6fr .8fr .8fr 70px", borderBottom: "1px solid var(--line)" }}>
        {([["Scrip", null], ["LTP", null], ["Chg%", "chg"], ["Score", "score"]] as [string, Sort | null][]).map(([h, k], i) => (
          <button
            key={h}
            onClick={() => k && setSort(k)}
            className="eyebrow"
            style={{ textAlign: i ? "right" : "left", background: "none", border: "none", cursor: k ? "pointer" : "default", color: sort === k ? "var(--accent)" : "var(--ink-3)" }}
          >
            {h}{sort === k ? " ↓" : ""}
          </button>
        ))}
      </div>

      <div className="overflow-y-auto">
        {loading && <div className="px-4 py-6 text-center text-[12px] text-fg-muted">Loading universe…</div>}
        {!loading && view.map(({ x, flag }) => {
          const sc = scoreOf(x);
          const active = sel === x.scrip;
          return (
            <button
              key={x.scrip}
              onClick={() => onSel(x.scrip)}
              className="grid w-full items-center gap-2 px-4 py-2 text-left"
              style={{
                gridTemplateColumns: "1.6fr .8fr .8fr 70px",
                background: active ? "var(--hover)" : "transparent",
                borderLeft: active ? "2px solid var(--accent)" : "2px solid transparent",
                borderBottom: "1px solid var(--line-soft)",
              }}
            >
              <div className="flex min-w-0 items-center gap-2.5">
                <span style={{ width: 7, height: 7, borderRadius: 99, background: flagColor(flag), flexShrink: 0, boxShadow: `0 0 5px ${flagColor(flag)}` }} />
                <div className="min-w-0">
                  <div className="mono text-[12.5px] font-semibold text-fg">{x.scrip}</div>
                  <div className="truncate text-[10px] text-fg-dim">{x.sector}</div>
                </div>
              </div>
              <span className="mono tabular-nums text-right text-[12px] text-fg">{x.latest_close != null ? npr(x.latest_close, 1) : "—"}</span>
              <span className="mono tabular-nums text-right text-[12px]" style={{ color: (x.change_pct ?? 0) >= 0 ? "var(--pos)" : "var(--neg)" }}>
                {x.change_pct != null ? `${x.change_pct >= 0 ? "+" : ""}${x.change_pct.toFixed(1)}` : "—"}
              </span>
              <div className="flex items-center justify-end gap-1.5">
                <div style={{ width: 28, height: 5, borderRadius: 9, background: "var(--line)", overflow: "hidden" }}>
                  <div style={{ width: `${sc}%`, height: "100%", background: flagColor(flag) }} />
                </div>
                <span className="mono tabular-nums text-[11.5px]" style={{ width: 18, textAlign: "right" }}>{sc}</span>
              </div>
            </button>
          );
        })}
        {!loading && view.length === 0 && <div className="px-4 py-6 text-center text-[12px] text-fg-muted">No scrips match this filter.</div>}
      </div>
    </div>
  );
}

function StockDetail({ row, spark }: { row: UniverseRow | null; spark?: number[] }) {
  const router = useRouter();
  const prices = useQuery({
    queryKey: ["prices", row?.scrip, 90],
    queryFn: () => api.prices(row!.scrip, 90),
    enabled: !!row,
    staleTime: 5 * 60_000,
  });

  if (!row) return <div className="panel p-6 text-center text-[12px] text-fg-muted">Select a scrip.</div>;

  const sc = scoreOf(row);
  const flag = deriveFlag(sc, row.change_pct);
  const series = (prices.data ?? []).map((p) => p.close);
  const chartData = series.length > 1 ? series : spark && spark.length > 1 ? spark : [];

  return (
    <div className="panel overflow-hidden">
      {/* head */}
      <div className="flex flex-wrap items-center gap-5 px-5 py-4" style={{ borderBottom: "1px solid var(--line)" }}>
        <div>
          <div className="eyebrow">{row.sector}</div>
          <div className="serif" style={{ fontSize: 19, fontWeight: 600, marginTop: 2 }}>
            <span className="mono" style={{ fontSize: 14, fontWeight: 700, color: "var(--accent)" }}>{row.scrip}</span>
            <span style={{ color: "var(--ink-3)", margin: "0 8px" }}>·</span>
            {row.company_name}
          </div>
        </div>
        <div className="flex items-baseline gap-2.5">
          <span className="display tnum" style={{ fontSize: 28, fontWeight: 700 }}>{row.latest_close != null ? npr(row.latest_close, 1) : "—"}</span>
          {row.change_pct != null && (
            <span className="mono" style={{ fontSize: 13, color: row.change_pct >= 0 ? "var(--pos)" : "var(--neg)" }}>
              {row.change_pct >= 0 ? "▲" : "▼"} {Math.abs(row.change_pct).toFixed(2)}%
            </span>
          )}
        </div>
        <div className="flex gap-6">
          <Stat label="Mkt cap" value={npr(row.market_cap_npr ?? null)} />
          <Stat label="P/E" value={row.pe_ratio != null ? row.pe_ratio.toFixed(1) : "—"} />
          <Stat label="6M return" value={row.return_6m != null ? `${(row.return_6m * 100).toFixed(1)}%` : "—"} />
        </div>
        <div className="flex-1" />
        <ScoreGauge score={sc} flag={flag} size={92} thick={7} label="Conviction" />
      </div>

      {/* chart */}
      <div className="p-5">
        <div className="mb-2 flex items-center justify-between">
          <span className="eyebrow">90-day price</span>
          <FlagPill flag={flag} sm />
        </div>
        {chartData.length > 1 ? (
          <Spark data={chartData} w={760} h={220} color="var(--accent)" strokeW={2} />
        ) : (
          <div className="py-12 text-center text-[12px] text-fg-muted">No price history yet.</div>
        )}
        <div className="mt-4">
          <button
            onClick={() => router.push(`/scrip/${row.scrip}`)}
            className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12.5px] font-semibold"
            style={{ background: "var(--accent)", color: "var(--bg)" }}
          >
            <Sparkles className="h-3.5 w-3.5" strokeWidth={2.2} />
            Open deep-dive
          </button>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1">
      <div className="eyebrow">{label}</div>
      <div className="mono tabular-nums text-[14px] font-semibold text-fg">{value}</div>
    </div>
  );
}
