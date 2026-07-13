"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
} from "recharts";
import { api } from "@/lib/api";
import {
  Panel, MetricCell, EmptyState, LoadingState, pct, pctFromPct, npr, quarterLabel,
} from "./primitives";

const MINI_SERIES: Array<{ key: "roe" | "roa" | "nim" | "npl_ratio" | "car" | "cd_ratio"; label: string; fmt: (v: number) => string }> = [
  { key: "roe",        label: "ROE %",  fmt: (v) => pct(v, 2) },
  { key: "roa",        label: "ROA %",  fmt: (v) => pct(v, 2) },
  { key: "nim",        label: "NIM %",  fmt: (v) => pct(v, 2) },
  { key: "npl_ratio",  label: "NPL %",  fmt: (v) => pct(v, 2) },
  { key: "car",        label: "CAR %",  fmt: (v) => pct(v, 2) },
  { key: "cd_ratio",   label: "CD %",   fmt: (v) => pct(v, 1) },
];

export function TabFundamentals({ scrip }: { scrip: string }) {
  const hist = useQuery({
    queryKey: ["fundamentals-history", scrip, 20],
    queryFn: () => api.scrip.fundamentalsHistory(scrip, 20),
  });

  const rows = hist.data ?? [];
  const latest = rows[rows.length - 1];
  // rows are already ordered oldest→latest from backend

  const chartData = rows.map((r) => ({
    q: quarterLabel(r.fiscal_year_bs, r.quarter),
    roe: r.roe !== null ? r.roe * 100 : null,
    roa: r.roa !== null ? r.roa * 100 : null,
    nim: r.ttm_nim !== null ? r.ttm_nim * 100 : null,
    npl_ratio: r.npl_ratio !== null ? r.npl_ratio * 100 : null,
    car: r.car !== null ? r.car * 100 : null,
    cd_ratio: r.cd_ratio !== null ? r.cd_ratio * 100 : null,
  }));

  return (
    <div className="grid grid-cols-12 gap-4">
      <Panel title="TTM snapshot" hint="Trailing four quarters" className="col-span-12">
        {hist.isLoading ? (
          <LoadingState rows={2} />
        ) : !latest ? (
          <EmptyState message="No fundamentals history." />
        ) : (
          <div className="grid grid-cols-4 gap-4">
            <MetricCell label="TTM Net profit"      value={npr(latest.ttm_net_profit)} />
            <MetricCell label="TTM ROE"             value={pct(latest.ttm_roe, 2)} />
            <MetricCell label="TTM ROA"             value={pct(latest.ttm_roa, 2)} />
            <MetricCell label="TTM NIM"             value={pct(latest.ttm_nim, 2)} />
            <MetricCell label="Net profit YoY"      value={pctFromPct(latest.net_profit_yoy_pct, 1)} />
            <MetricCell label="Loans YoY"           value={pctFromPct(latest.total_loans_yoy_pct, 1)} />
            <MetricCell label="Deposits YoY"        value={pctFromPct(latest.total_deposits_yoy_pct, 1)} />
            <MetricCell label="Operating income YoY" value={pctFromPct(latest.total_operating_income_yoy_pct, 1)} />
          </div>
        )}
      </Panel>

      {MINI_SERIES.map(({ key, label }) => (
        <Panel key={key} title={label} className="col-span-4">
          {hist.isLoading ? (
            <LoadingState rows={3} />
          ) : !rows.length ? (
            <EmptyState message="No series." />
          ) : (
            <div className="h-[140px]">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke="var(--border-subtle)" vertical={false} />
                  <XAxis dataKey="q" hide />
                  <YAxis tick={{ fontSize: 9, fill: "var(--fg-muted)" }} tickLine={false} axisLine={false} width={32} />
                  <Tooltip
                    contentStyle={{ background: "var(--bg-panel)", border: "1px solid var(--border)", borderRadius: 6, fontSize: 11 }}
                    formatter={(v) => [typeof v === "number" ? `${v.toFixed(2)}%` : "—", label]}
                  />
                  <Line type="monotone" dataKey={key} stroke="var(--fg)" strokeWidth={1.5} dot={false} connectNulls />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </Panel>
      ))}
    </div>
  );
}
