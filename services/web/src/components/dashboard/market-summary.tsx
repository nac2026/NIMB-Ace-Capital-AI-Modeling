"use client";

// Market Intelligence summary (the design's "Management view"): headline KPIs +
// Fear-&-Greed, then Top Red Flags / Top Green Flags conviction cards. This is
// the analytics overview — no single-stock chart.

import { useMemo } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api, type UniverseRow } from "@/lib/api";
import { Spark, FearGreed, flagColor, deriveFlag, npr, type Flag } from "@/components/viz";

function scoreOf(r: UniverseRow): number {
  return Math.round(r.scorecard_0_100 ?? r.quality_score_0_100 ?? 50);
}
function tagsOf(r: UniverseRow): string[] {
  if (r.flags?.length) return r.flags.slice(0, 2);
  const t: string[] = [];
  if (r.quality_tier) t.push(r.quality_tier);
  if (r.quadrant) t.push(r.quadrant);
  return t.slice(0, 2);
}

export function MarketSummary() {
  const indices = useQuery({ queryKey: ["indices"], queryFn: api.indices });
  const universe = useQuery({ queryKey: ["universe"], queryFn: api.universe });
  const pulse = useQuery({ queryKey: ["market-pulse"], queryFn: api.marketPulse });
  const sparks = useQuery({ queryKey: ["universe-sparklines", 30], queryFn: () => api.universeSparklines(30) });

  const rows = universe.data ?? [];
  const flagged = rows.map((r) => ({ r, flag: deriveFlag(scoreOf(r), r.change_pct) }));
  const reds = flagged.filter((x) => x.flag === "red");
  const greens = flagged.filter((x) => x.flag === "green");

  const topReds = [...reds].sort((a, b) => scoreOf(a.r) - scoreOf(b.r)).slice(0, 3);
  const topGreens = [...greens].sort((a, b) => scoreOf(b.r) - scoreOf(a.r)).slice(0, 3);

  const idx = indices.data ?? [];
  const nepse = idx.find((r) => /nepse/i.test(r.index_name)) ?? idx[0] ?? null;
  const turnover = nepse?.turnover ?? idx.find((r) => r.turnover != null)?.turnover ?? null;

  // Fear & Greed proxy: breadth (advances share) blended with avg news sentiment.
  const adv = rows.filter((r) => (r.change_pct ?? 0) > 0).length;
  const dec = rows.filter((r) => (r.change_pct ?? 0) < 0).length;
  const breadth = adv + dec > 0 ? adv / (adv + dec) : 0.5;
  const sent = pulse.data?.sentiment_avg ?? 0; // -1..1
  const fearGreed = Math.round(Math.max(0, Math.min(100, breadth * 70 + ((sent + 1) / 2) * 30)));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap)" }}>
      {/* KPI row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr) 1.1fr", gap: "var(--gap)" }}>
        <Kpi label="NEPSE Index" value={nepse ? npr(nepse.close, 1) : "—"} delta={nepse?.percent_change ?? null} sub={nepse?.percent_change != null ? `${nepse.percent_change >= 0 ? "+" : ""}${nepse.percent_change.toFixed(2)}% today` : undefined} />
        <Kpi label="Turnover" value={turnover != null ? `${npr(turnover / 1e9, 2)}B` : "—"} sub={`Rs · ${adv + dec} scrips traded`} />
        <Kpi label="Red Flags" value={String(reds.length)} accent="var(--neg)" sub="require review" />
        <Kpi label="Green Flags" value={String(greens.length)} accent="var(--pos)" sub="conviction longs" />
        <div className="panel" style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: 10 }}>
          <FearGreed value={fearGreed} size={150} />
        </div>
      </div>

      {/* Top flags */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--gap)", alignItems: "start" }}>
        <FlagSection title="Top Red Flags" eyebrow="elevated risk · lowest conviction" items={topReds} sparks={sparks.data} empty="No red-flag names." />
        <FlagSection title="Top Green Flags" eyebrow="highest-conviction longs" items={topGreens} sparks={sparks.data} empty="No green-flag names." />
      </div>
    </div>
  );
}

function Kpi({ label, value, delta, sub, accent }: { label: string; value: string; delta?: number | null; sub?: string; accent?: string }) {
  const dc = delta == null ? undefined : delta >= 0 ? "var(--pos)" : "var(--neg)";
  return (
    <div className="panel" style={{ padding: 16 }}>
      <div className="eyebrow">{label}</div>
      <div className="display tnum" style={{ fontSize: 30, fontWeight: 700, marginTop: 6, color: accent ?? "var(--ink)" }}>{value}</div>
      {sub && <div style={{ fontSize: 11.5, color: dc ?? "var(--ink-3)", marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

function FlagSection({ title, eyebrow, items, sparks, empty }: {
  title: string; eyebrow: string; items: { r: UniverseRow; flag: Flag }[]; sparks?: Record<string, number[]>; empty: string;
}) {
  return (
    <div className="panel overflow-hidden">
      <div className="px-4 py-3" style={{ borderBottom: "1px solid var(--line)" }}>
        <h3 className="text-[12.5px] font-semibold uppercase tracking-wider text-fg">{title}</h3>
        <p className="mt-0.5 text-[11px] text-fg-muted">{eyebrow}</p>
      </div>
      <div style={{ padding: 14 }}>
        {items.length === 0 ? (
          <div className="py-6 text-center text-[12px] text-fg-muted">{empty}</div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10 }}>
            {items.map(({ r, flag }) => <FlagCard key={r.scrip} r={r} flag={flag} spark={sparks?.[r.scrip]} />)}
          </div>
        )}
      </div>
    </div>
  );
}

function FlagCard({ r, flag, spark }: { r: UniverseRow; flag: Flag; spark?: number[] }) {
  const router = useRouter();
  const c = flagColor(flag);
  const tags = tagsOf(r);
  return (
    <button
      onClick={() => router.push(`/scrip/${r.scrip}`)}
      className="flex flex-col gap-2 text-left"
      style={{ padding: 14, borderRadius: 12, background: "var(--panel-2)", border: "1px solid var(--line-soft)", borderTop: `3px solid ${c}` }}
    >
      <div className="flex items-start justify-between">
        <div className="min-w-0">
          <div className="mono" style={{ fontWeight: 700, fontSize: 14 }}>{r.scrip}</div>
          <div className="truncate" style={{ fontSize: 10.5, color: "var(--ink-3)" }}>{r.sector}</div>
        </div>
        <span className="display tnum" style={{ fontSize: 26, fontWeight: 700, color: c }}>{scoreOf(r)}</span>
      </div>
      {spark && spark.length > 1 ? <Spark data={spark} w={180} h={30} color={c} fullWidth /> : <div style={{ height: 30 }} />}
      <div className="flex flex-wrap gap-1.5">
        {tags.map((t, i) => (
          <span key={i} className="mono" style={{ fontSize: 9, padding: "2px 6px", borderRadius: 6, background: "var(--panel-3)", border: "1px solid var(--line)", color: "var(--ink-2)" }}>{t}</span>
        ))}
      </div>
    </button>
  );
}
