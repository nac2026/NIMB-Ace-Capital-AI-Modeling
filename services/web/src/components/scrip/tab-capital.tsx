"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ResponsiveContainer, AreaChart, Area, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine,
} from "recharts";
import { api } from "@/lib/api";
import { Pill } from "@/components/dashboard/chips";
import {
  Panel, MetricCell, EmptyState, LoadingState, pct, npr, quarterLabel,
} from "./primitives";

const CAP_TONE: Record<string, "ok" | "warn" | "err" | "muted"> = {
  STRONG: "ok",
  ADEQUATE: "muted",
  TIGHT_CAPITAL: "warn",
  BREACH: "err",
};

export function TabCapital({ scrip }: { scrip: string }) {
  const hist = useQuery({
    queryKey: ["capital", scrip, 20],
    queryFn: () => api.scrip.capital(scrip, 20),
  });

  const rows = (hist.data ?? []).slice().reverse();
  const latest = rows[rows.length - 1];

  const data = rows.map((r) => ({
    q: quarterLabel(r.fiscal_year_bs, r.quarter),
    car: r.car !== null ? r.car * 100 : null,
    tier1: r.tier1_capital,
    tier2: r.tier2_capital,
  }));

  return (
    <div className="grid grid-cols-12 gap-4">
      <Panel
        title="Latest capital"
        className="col-span-12"
        right={latest?.capital_tier ? (
          <Pill label={latest.capital_tier} tone={CAP_TONE[latest.capital_tier] ?? "muted"} />
        ) : null}
      >
        {hist.isLoading ? (
          <LoadingState rows={2} />
        ) : !latest ? (
          <EmptyState message="No capital data." />
        ) : (
          <div className="grid grid-cols-4 gap-4">
            <MetricCell label="CAR" value={pct(latest.car, 2)} tone={latest.car !== null && latest.car < 0.11 ? "err" : latest.car !== null && latest.car > 0.13 ? "ok" : "default"} />
            <MetricCell label="CAR buffer vs 11%" value={latest.car_buffer !== null ? `${(latest.car_buffer * 100).toFixed(2)}pp` : "—"} />
            <MetricCell label="CAR YoY Δ" value={latest.car_yoy_change !== null ? `${latest.car_yoy_change >= 0 ? "+" : ""}${(latest.car_yoy_change * 100).toFixed(2)}pp` : "—"} tone={latest.car_yoy_change !== null && latest.car_yoy_change > 0 ? "ok" : "default"} />
            <MetricCell label="Tier 1 share" value={pct(latest.tier1_share, 1)} />
            <MetricCell label="Tier 1" value={npr(latest.tier1_capital)} />
            <MetricCell label="Tier 2" value={npr(latest.tier2_capital)} />
            <MetricCell label="Total capital" value={npr(latest.total_capital)} />
          </div>
        )}
      </Panel>

      <Panel title="CAR trajectory" hint="NRB minimum 11% shown as reference" className="col-span-6">
        {hist.isLoading ? (
          <LoadingState rows={4} />
        ) : !data.length ? (
          <EmptyState message="No series." />
        ) : (
          <div className="h-[220px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="var(--border-subtle)" vertical={false} />
                <XAxis dataKey="q" tick={{ fontSize: 9, fill: "var(--fg-muted)" }} tickLine={false} axisLine={false} minTickGap={24} />
                <YAxis domain={["auto", "auto"]} tick={{ fontSize: 10, fill: "var(--fg-muted)" }} tickLine={false} axisLine={false} width={38} />
                <Tooltip
                  contentStyle={{ background: "var(--bg-panel)", border: "1px solid var(--border)", borderRadius: 6, fontSize: 11 }}
                  formatter={(v) => [typeof v === "number" ? `${v.toFixed(2)}%` : "—", "CAR"]}
                />
                <ReferenceLine y={11} stroke="var(--err)" strokeDasharray="3 3" strokeWidth={1} label={{ value: "NRB 11%", fontSize: 10, fill: "var(--err)", position: "insideTopRight" }} />
                <Line type="monotone" dataKey="car" stroke="var(--fg)" strokeWidth={1.5} dot={false} connectNulls />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </Panel>

      <Panel title="Tier 1 / Tier 2 stack" className="col-span-6">
        {hist.isLoading ? (
          <LoadingState rows={4} />
        ) : !data.length ? (
          <EmptyState message="No series." />
        ) : (
          <div className="h-[220px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="var(--border-subtle)" vertical={false} />
                <XAxis dataKey="q" tick={{ fontSize: 9, fill: "var(--fg-muted)" }} tickLine={false} axisLine={false} minTickGap={24} />
                <YAxis tick={{ fontSize: 10, fill: "var(--fg-muted)" }} tickLine={false} axisLine={false} width={54} tickFormatter={(v) => (v >= 1e9 ? `${(v / 1e9).toFixed(0)}B` : v >= 1e6 ? `${(v / 1e6).toFixed(0)}M` : String(v))} />
                <Tooltip
                  contentStyle={{ background: "var(--bg-panel)", border: "1px solid var(--border)", borderRadius: 6, fontSize: 11 }}
                  formatter={(v, k) => [typeof v === "number" ? npr(v) : "—", k === "tier1" ? "Tier 1" : "Tier 2"]}
                />
                <Area dataKey="tier1" stackId="a" stroke="var(--fg)" fill="var(--fg)" fillOpacity={0.8} />
                <Area dataKey="tier2" stackId="a" stroke="var(--fg-muted)" fill="var(--fg-muted)" fillOpacity={0.5} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </Panel>
    </div>
  );
}
