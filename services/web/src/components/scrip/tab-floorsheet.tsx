"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Pill } from "@/components/dashboard/chips";
import { AccumBars, MultiLineChart, type AccumRow, type LineSeries } from "@/components/viz";
import { Panel, MetricCell, EmptyState, LoadingState } from "./primitives";

const PHASE_TONE: Record<string, string> = { accumulating: "var(--ok)", distributing: "var(--err)", flat: "var(--fg-muted)" };
const LINE_COLORS = ["#3fb37f", "#38c6cf", "#d8a64a", "#e8884e", "#e5575c", "#9b8cff"];

function fmtDate(s: string | null | undefined): string {
  if (!s) return "—";
  const d = new Date(s);
  return isNaN(d.getTime()) ? "—" : d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
}

const SPEC_TONE: Record<string, "ok" | "warn" | "err" | "muted"> = {
  LOW: "ok",
  MODERATE: "muted",
  ELEVATED: "warn",
  HIGH: "err",
};

function sharePct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `${(v * 100).toFixed(0)}%`;
}
function qty(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  const a = Math.abs(v);
  const s = a >= 1e6 ? `${(v / 1e6).toFixed(2)}M` : a >= 1e3 ? `${(v / 1e3).toFixed(1)}K` : String(Math.round(v));
  return v > 0 ? `+${s}` : s;
}

export function TabFloorsheet({ scrip }: { scrip: string }) {
  const q = useQuery({
    queryKey: ["floorsheet", scrip],
    queryFn: () => api.scrip.floorsheet(scrip),
  });
  const d = q.data;
  const spec = d?.speculation;
  const latest = d?.concentration_recent?.[0];

  // Position-over-time series (cum net position per top broker).
  const tl = d?.position_timeline ?? [];
  const dates = Array.from(new Set(tl.flatMap((s) => s.points.map((p) => p.date)))).sort();
  const dateIdx: Record<string, number> = Object.fromEntries(dates.map((dd, i) => [dd, i]));
  const series: LineSeries[] = tl.map((s, i) => ({
    label: `#${s.broker}`,
    color: LINE_COLORS[i % LINE_COLORS.length],
    points: s.points.map((p) => ({ t: dateIdx[p.date], v: p.cum_net_qty ?? 0 })),
  }));

  // Diverging net-activity rows: accumulators as buy-side, distributors as sell-side.
  const accumRows: AccumRow[] = [
    ...(d?.top_accumulators ?? []).slice(0, 5).map((r) => ({
      broker: `#${r.broker}`,
      buy: Math.abs(r.cum_net_qty ?? 0),
      sell: 0,
    })),
    ...(d?.top_distributors ?? []).slice(0, 5).map((r) => ({
      broker: `#${r.broker}`,
      buy: 0,
      sell: Math.abs(r.cum_net_qty ?? 0),
    })),
  ];

  return (
    <div className="grid grid-cols-12 gap-4">
      {/* Speculation / manipulation score */}
      <Panel
        title="Speculation score"
        hint="Floor-sheet microstructure: broker concentration, circular/wash trading, single-broker accumulation, block trades"
        className="col-span-12"
        right={spec?.speculation_tier ? <Pill label={spec.speculation_tier} tone={SPEC_TONE[spec.speculation_tier] ?? "muted"} /> : null}
      >
        {q.isLoading ? <LoadingState rows={2} /> : !spec ? (
          <EmptyState message="No floor-sheet data for this scrip yet." />
        ) : (
          <div className="grid grid-cols-6 gap-4">
            <MetricCell label="Score (0–100)" value={spec.speculation_score?.toFixed(1) ?? "—"}
              tone={(spec.speculation_score ?? 0) >= 70 ? "err" : (spec.speculation_score ?? 0) >= 45 ? "warn" : "default"} />
            <MetricCell label="Concentration" value={sharePct(spec.c_concentration)} />
            <MetricCell label="Circular/wash" value={sharePct(spec.c_circular)} tone={(spec.c_circular ?? 0) > 0.3 ? "warn" : "default"} />
            <MetricCell label="1-broker accum." value={sharePct(spec.c_accumulation)} tone={(spec.c_accumulation ?? 0) > 0.4 ? "warn" : "default"} />
            <MetricCell label="Block trades" value={sharePct(spec.c_block)} />
            <MetricCell label="Self-trade" value={spec.has_self_trade ? "Detected" : "None"} tone={spec.has_self_trade ? "err" : "ok"} />
          </div>
        )}
      </Panel>

      {/* Net broker activity — diverging accumulation vs distribution */}
      <Panel title="Net broker activity" hint="Net buy (right, green) vs net sell (left, red) by broker over the loaded window" className="col-span-12">
        {q.isLoading ? <LoadingState rows={4} /> : accumRows.length === 0 ? (
          <EmptyState message="No broker flow." />
        ) : (
          <AccumBars rows={accumRows} w={520} />
        )}
      </Panel>

      {/* Broker position over time */}
      <Panel title="Broker position over time" hint="Cumulative net position per top broker — see the build-up and when a broker flips to selling" className="col-span-12">
        {q.isLoading ? <LoadingState rows={3} /> : series.length === 0 ? (
          <EmptyState message="No position history yet (floor-sheet history is still shallow)." />
        ) : (
          <div>
            <MultiLineChart series={series} dates={dates} />
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
              {series.map((s) => (
                <span key={s.label} className="inline-flex items-center gap-1.5 text-[11px] text-fg-muted">
                  <span style={{ width: 9, height: 3, borderRadius: 2, background: s.color, display: "inline-block" }} />
                  <span className="num">{s.label}</span>
                </span>
              ))}
              <span className="text-[10.5px] text-fg-dim">· line rises = accumulating, falls = distributing</span>
            </div>
          </div>
        )}
      </Panel>

      {/* Top accumulators */}
      <Panel title="Top accumulating brokers" hint="Net buyers over the loaded window — flagged when persistent & material (≥15% of volume)" className="col-span-6">
        {q.isLoading ? <LoadingState rows={4} /> : !d?.top_accumulators?.length ? (
          <EmptyState message="No broker flow." />
        ) : (
          <BrokerTable rows={d.top_accumulators} kind="accum" />
        )}
      </Panel>

      {/* Top distributors */}
      <Panel title="Top distributing brokers" hint="Net sellers over the loaded window" className="col-span-6">
        {q.isLoading ? <LoadingState rows={4} /> : !d?.top_distributors?.length ? (
          <EmptyState message="No broker flow." />
        ) : (
          <BrokerTable rows={d.top_distributors} kind="dist" />
        )}
      </Panel>

      {/* Concentration (latest day) */}
      <Panel title="Broker concentration" hint="Is one broker controlling a side? Dominance = top-1 > 30%; control = top-3 > 60%" className="col-span-12">
        {q.isLoading ? <LoadingState rows={2} /> : !latest ? (
          <EmptyState message="No concentration data." />
        ) : (
          <div className="grid grid-cols-6 gap-4">
            <MetricCell label="Top-1 buy share" value={sharePct(latest.top1_buy_share)} tone={(latest.top1_buy_share ?? 0) > 0.3 ? "warn" : "default"} />
            <MetricCell label="Top-3 buy share" value={sharePct(latest.top3_buy_share)} tone={(latest.top3_buy_share ?? 0) > 0.6 ? "warn" : "default"} />
            <MetricCell label="Top-1 sell share" value={sharePct(latest.top1_sell_share)} tone={(latest.top1_sell_share ?? 0) > 0.3 ? "warn" : "default"} />
            <MetricCell label="Top-3 sell share" value={sharePct(latest.top3_sell_share)} tone={(latest.top3_sell_share ?? 0) > 0.6 ? "warn" : "default"} />
            <MetricCell label="Active brokers" value={latest.n_brokers?.toString() ?? "—"} />
            <div className="flex items-end">
              {latest.concentration_flag ? <Pill label="CONCENTRATED" tone="warn" /> : <Pill label="DISPERSED" tone="ok" />}
            </div>
          </div>
        )}
      </Panel>
    </div>
  );
}

function BrokerTable({ rows, kind }: { rows: import("@/lib/api").BrokerPositionRow[]; kind: "accum" | "dist" }) {
  return (
    <table className="w-full text-[12.5px]">
      <thead>
        <tr className="text-fg-dim text-[10.5px] uppercase tracking-wider">
          <th className="text-left font-semibold py-1">Broker</th>
          <th className="text-right font-semibold py-1">Net qty</th>
          <th className="text-right font-semibold py-1">Vol share</th>
          <th className="text-left font-semibold py-1 pl-3">Phase</th>
          <th className="text-right font-semibold py-1">Since</th>
          <th className="text-right font-semibold py-1">Flipped</th>
        </tr>
      </thead>
      <tbody className="tabular-nums">
        {rows.map((r) => {
          const phase = r.phase ?? (kind === "accum" ? "accumulating" : "distributing");
          return (
            <tr key={r.broker} style={{ borderTop: "1px solid var(--border-subtle)" }}>
              <td className="py-1.5 num font-medium">#{r.broker}</td>
              <td className={"py-1.5 text-right num " + ((r.cum_net_qty ?? 0) > 0 ? "text-ok" : "text-err")}>{qty(r.cum_net_qty)}</td>
              <td className="py-1.5 text-right num">{sharePct(r.volume_share)}</td>
              <td className="py-1.5 pl-3">
                <span className="num text-[10.5px] font-semibold uppercase tracking-wide" style={{ color: PHASE_TONE[phase] ?? "var(--fg-muted)" }}>{phase}</span>
              </td>
              <td className="py-1.5 text-right num text-fg-muted" title="Accumulation started">{fmtDate(r.accum_start_date)}</td>
              <td className="py-1.5 text-right num" style={{ color: r.dist_start_date ? "var(--err)" : "var(--fg-dim)" }} title="Flipped to distributing">{fmtDate(r.dist_start_date)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
