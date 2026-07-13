"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ReferenceLine,
} from "recharts";
import { api } from "@/lib/api";
import { Pill } from "@/components/dashboard/chips";
import {
  Panel, MetricCell, EmptyState, LoadingState, pctFromPct,
} from "./primitives";

const YIELD_TONE: Record<string, "ok" | "warn" | "muted" | "err"> = {
  ABOVE_FD_RATE: "ok",
  NEAR_FD_RATE: "muted",
  BELOW_FD_RATE: "warn",
  NONE: "err",
};

export function TabIncome({ scrip }: { scrip: string }) {
  const div = useQuery({
    queryKey: ["dividends", scrip],
    queryFn: () => api.scrip.dividends(scrip),
  });

  const annual = div.data?.annual ?? [];
  const latest = annual[0];

  const chartData = [...annual].slice(0, 10).reverse().map((d) => ({
    year: `FY${d.fiscal_year_bs}`,
    cash: d.annual_cash_div_pct ?? 0,
    bonus: d.annual_bonus_pct ?? 0,
  }));

  return (
    <div className="grid grid-cols-12 gap-4">
      <Panel
        title="Latest dividend (annual)"
        className="col-span-12"
        right={latest?.yield_tier ? (
          <Pill label={latest.yield_tier} tone={YIELD_TONE[latest.yield_tier] ?? "muted"} />
        ) : null}
      >
        {div.isLoading ? (
          <LoadingState rows={2} />
        ) : !latest ? (
          <EmptyState message="No dividend history." />
        ) : (
          <div className="grid grid-cols-4 gap-4">
            <MetricCell label={`FY${latest.fiscal_year_bs} cash %`} value={latest.annual_cash_div_pct !== null ? `${latest.annual_cash_div_pct.toFixed(2)}%` : "—"} />
            <MetricCell label={`FY${latest.fiscal_year_bs} bonus %`} value={latest.annual_bonus_pct !== null ? `${latest.annual_bonus_pct.toFixed(2)}%` : "—"} />
            <MetricCell label="Cash yield" value={pctFromPct(latest.cash_dividend_yield, 2)} />
            <MetricCell label="Total yield" value={pctFromPct(latest.total_dividend_yield, 2)} tone={latest.total_dividend_yield !== null && latest.total_dividend_yield >= 8 ? "ok" : "default"} />
          </div>
        )}
      </Panel>

      <Panel title="Annual dividend history" hint="Cash vs bonus (on par) — FD rate reference 8%" className="col-span-12">
        {div.isLoading ? (
          <LoadingState rows={5} />
        ) : !chartData.length ? (
          <EmptyState message="No series." />
        ) : (
          <div className="h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="var(--border-subtle)" vertical={false} />
                <XAxis dataKey="year" tick={{ fontSize: 10, fill: "var(--fg-muted)" }} tickLine={false} axisLine={false} />
                <YAxis tick={{ fontSize: 10, fill: "var(--fg-muted)" }} tickLine={false} axisLine={false} width={40} tickFormatter={(v) => `${v}%`} />
                <Tooltip
                  contentStyle={{ background: "var(--bg-panel)", border: "1px solid var(--border)", borderRadius: 6, fontSize: 11 }}
                  formatter={(v, k) => [typeof v === "number" ? `${v.toFixed(2)}%` : "—", k === "cash" ? "Cash" : "Bonus"]}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <ReferenceLine y={8} stroke="var(--warn)" strokeDasharray="3 3" strokeWidth={1} label={{ value: "8% FD", fontSize: 10, fill: "var(--warn)", position: "insideTopRight" }} />
                <Bar dataKey="cash"  stackId="a" fill="var(--fg)"       name="Cash" />
                <Bar dataKey="bonus" stackId="a" fill="var(--fg-muted)" name="Bonus" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </Panel>
    </div>
  );
}
