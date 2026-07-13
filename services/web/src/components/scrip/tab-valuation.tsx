"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ResponsiveContainer, ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid, Tooltip,
} from "recharts";
import { api } from "@/lib/api";
import { SelfValuationChip } from "@/components/dashboard/chips";
import {
  Panel, MetricCell, EmptyState, LoadingState, quarterLabel,
} from "./primitives";

export function TabValuation({ scrip }: { scrip: string }) {
  const hist = useQuery({
    queryKey: ["valuation-history", scrip, 20],
    queryFn: () => api.scrip.valuationHistory(scrip, 20),
  });

  const rows = (hist.data ?? []).slice().reverse(); // oldest → latest for charts
  const latest = rows[rows.length - 1];

  const chartData = rows.map((r) => ({
    q: quarterLabel(r.fiscal_year_bs, r.quarter),
    pe: r.pe_ratio,
    pb: r.pb_ratio,
  }));

  return (
    <div className="grid grid-cols-12 gap-4">
      <Panel
        title="Vs own 5-year history"
        hint="Percentile below means cheaper than that share of own past"
        className="col-span-12"
        right={<SelfValuationChip tier={latest?.self_valuation_tier ?? null} />}
      >
        {hist.isLoading ? (
          <LoadingState rows={2} />
        ) : !latest ? (
          <EmptyState message="No valuation history." />
        ) : (
          <div className="grid grid-cols-4 gap-4">
            <MetricCell label="Current P/E" value={latest.pe_ratio?.toFixed(2) ?? "—"} />
            <MetricCell
              label="P/E percentile (5Y)"
              value={latest.pe_self_pct_5y !== null ? `${(latest.pe_self_pct_5y * 100).toFixed(0)}th` : "—"}
              hint="100th = most expensive the stock has traded at vs own past"
              tone={latest.pe_self_pct_5y !== null && latest.pe_self_pct_5y < 0.3 ? "ok" : latest.pe_self_pct_5y !== null && latest.pe_self_pct_5y > 0.8 ? "err" : "default"}
            />
            <MetricCell label="Current P/B" value={latest.pb_ratio?.toFixed(2) ?? "—"} />
            <MetricCell
              label="P/B percentile (5Y)"
              value={latest.pb_self_pct_5y !== null ? `${(latest.pb_self_pct_5y * 100).toFixed(0)}th` : "—"}
              tone={latest.pb_self_pct_5y !== null && latest.pb_self_pct_5y < 0.3 ? "ok" : latest.pb_self_pct_5y !== null && latest.pb_self_pct_5y > 0.8 ? "err" : "default"}
            />
          </div>
        )}
      </Panel>

      <Panel title="P/E history" className="col-span-6">
        <ValuationChart data={chartData} field="pe" label="P/E" isLoading={hist.isLoading} />
      </Panel>
      <Panel title="P/B history" className="col-span-6">
        <ValuationChart data={chartData} field="pb" label="P/B" isLoading={hist.isLoading} />
      </Panel>
    </div>
  );
}

function ValuationChart({
  data,
  field,
  label,
  isLoading,
}: {
  data: { q: string; pe: number | null; pb: number | null }[];
  field: "pe" | "pb";
  label: string;
  isLoading: boolean;
}) {
  if (isLoading) return <LoadingState rows={4} />;
  if (!data.length) return <EmptyState message="No series." />;

  const vals = data.map((d) => d[field]).filter((v): v is number => v !== null);
  const min = Math.min(...vals);
  const max = Math.max(...vals);

  // Shaded 20-80 percentile band — simple approximation so the chart reads
  // as "where does this sit vs its own past".
  const lo = min + (max - min) * 0.2;
  const hi = min + (max - min) * 0.8;

  const withBand = data.map((d) => ({ ...d, lo, hi }));

  return (
    <div className="h-[200px]">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={withBand} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="var(--border-subtle)" vertical={false} />
          <XAxis dataKey="q" tick={{ fontSize: 9, fill: "var(--fg-muted)" }} tickLine={false} axisLine={false} minTickGap={24} />
          <YAxis tick={{ fontSize: 10, fill: "var(--fg-muted)" }} tickLine={false} axisLine={false} width={36} />
          <Tooltip
            contentStyle={{ background: "var(--bg-panel)", border: "1px solid var(--border)", borderRadius: 6, fontSize: 11 }}
            formatter={(v, name) => [typeof v === "number" ? v.toFixed(2) : "—", name === field ? label : String(name)]}
          />
          <Area dataKey="hi" stroke="none" fill="var(--border-subtle)" fillOpacity={0.5} />
          <Area dataKey="lo" stroke="none" fill="var(--bg)" fillOpacity={1} />
          <Line type="monotone" dataKey={field} stroke="var(--fg)" strokeWidth={1.5} dot={false} connectNulls />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
