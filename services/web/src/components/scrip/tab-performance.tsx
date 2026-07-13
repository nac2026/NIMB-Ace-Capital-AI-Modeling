"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ResponsiveContainer, LineChart, Line, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
} from "recharts";
import { api } from "@/lib/api";
import { Panel, MetricCell, EmptyState, LoadingState, signedPct } from "./primitives";

export function TabPerformance({ scrip }: { scrip: string }) {
  const prices = useQuery({ queryKey: ["prices", scrip, 365], queryFn: () => api.prices(scrip, 365) });
  const returns = useQuery({ queryKey: ["returns", scrip], queryFn: () => api.scrip.returns(scrip) });
  const intraday = useQuery({
    queryKey: ["intraday", scrip],
    queryFn: () => api.scrip.intraday(scrip),
    staleTime: 60_000,
    refetchInterval: 60_000,
  });

  const r = returns.data;
  const iday = intraday.data?.series ?? [];
  const idayUp = iday.length >= 2 && (iday[iday.length - 1].price ?? 0) >= (iday[0].price ?? 0);
  const idayColor = idayUp ? "var(--ok)" : "var(--err)";

  return (
    <div className="grid grid-cols-12 gap-4">
      <Panel
        title="Intraday (today)"
        hint="Live minute bars — SMTM"
        className="col-span-12"
        right={intraday.isFetching ? <span className="text-[10px] text-fg-muted">live…</span> : undefined}
      >
        {intraday.isLoading ? (
          <LoadingState rows={4} />
        ) : iday.length < 2 ? (
          <EmptyState message="No intraday session yet — the market hasn't traded today." />
        ) : (
          <div className="h-[200px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={iday}>
                <defs>
                  <linearGradient id="iday-fill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={idayColor} stopOpacity={0.28} />
                    <stop offset="100%" stopColor={idayColor} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="var(--border-subtle)" vertical={false} />
                <XAxis
                  dataKey="t"
                  tick={{ fontSize: 10, fill: "var(--fg-muted)" }}
                  tickLine={false}
                  axisLine={false}
                  minTickGap={48}
                  tickFormatter={(t: string) => (t?.length >= 16 ? t.slice(11, 16) : t)}
                />
                <YAxis tick={{ fontSize: 10, fill: "var(--fg-muted)" }} tickLine={false} axisLine={false} width={44} domain={["auto", "auto"]} />
                <Tooltip
                  contentStyle={{ background: "var(--bg-panel)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
                  labelStyle={{ color: "var(--fg-muted)" }}
                  labelFormatter={(t) => (typeof t === "string" && t.length >= 16 ? t.slice(11, 16) : String(t))}
                  formatter={(v) => [typeof v === "number" ? `Rs ${v}` : "—", "Price"]}
                />
                <Area type="monotone" dataKey="price" stroke={idayColor} strokeWidth={1.5} fill="url(#iday-fill)" dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </Panel>

      <Panel title="Price history (1Y)" className="col-span-8">
        {prices.isLoading ? (
          <LoadingState rows={5} />
        ) : !prices.data?.length ? (
          <EmptyState message="No price history available." />
        ) : (
          <div className="h-[280px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={prices.data}>
                <CartesianGrid stroke="var(--border-subtle)" vertical={false} />
                <XAxis dataKey="date" tick={{ fontSize: 10, fill: "var(--fg-muted)" }} tickLine={false} axisLine={false} minTickGap={40} />
                <YAxis tick={{ fontSize: 10, fill: "var(--fg-muted)" }} tickLine={false} axisLine={false} width={44} />
                <Tooltip
                  contentStyle={{
                    background: "var(--bg-panel)",
                    border: "1px solid var(--border)",
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                  labelStyle={{ color: "var(--fg-muted)" }}
                />
                <Line type="monotone" dataKey="close" stroke="var(--fg)" strokeWidth={1.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </Panel>

      <Panel title="Market risk" hint="Beta & vol vs NEPSE" className="col-span-4">
        {returns.isLoading ? (
          <LoadingState rows={4} />
        ) : !r ? (
          <EmptyState message="No market-risk data." />
        ) : (
          <div className="grid grid-cols-2 gap-y-5 gap-x-4">
            <MetricCell label="Beta (NEPSE)" value={r.beta?.toFixed(2) ?? "—"} />
            <MetricCell label="Alpha (annual)" value={r.alpha_annual !== null ? `${(r.alpha_annual * 100).toFixed(1)}%` : "—"} />
            <MetricCell label="R²" value={r.r_squared?.toFixed(2) ?? "—"} />
            <MetricCell label="Annualised vol" value={r.annualized_vol !== null ? `${(r.annualized_vol * 100).toFixed(1)}%` : "—"} />
            <MetricCell label="Sharpe (2Y)" value={r.sharpe_ratio_2y?.toFixed(2) ?? "—"} />
            <MetricCell label="20D vol" value={r.realized_vol_20d !== null ? `${(r.realized_vol_20d * 100).toFixed(1)}%` : "—"} />
          </div>
        )}
      </Panel>

      <Panel title="Returns" hint="Price-only (capital gain)" className="col-span-6">
        {!r ? <LoadingState rows={3} /> : (
          <div className="grid grid-cols-3 gap-y-5 gap-x-4">
            <MetricCell label="1M"  value={signedPct(r.return_1m)} tone={tone(r.return_1m)} />
            <MetricCell label="3M"  value={signedPct(r.return_3m)} tone={tone(r.return_3m)} />
            <MetricCell label="6M"  value={signedPct(r.return_6m)} tone={tone(r.return_6m)} />
            <MetricCell label="1Y"  value={signedPct(r.return_1y)} tone={tone(r.return_1y)} />
            <MetricCell label="3Y"  value={signedPct(r.return_3y)} tone={tone(r.return_3y)} />
            <MetricCell label="5Y"  value={signedPct(r.return_5y)} tone={tone(r.return_5y)} />
          </div>
        )}
      </Panel>

      <Panel title="Total shareholder return" hint="Includes cash + bonus dividends" className="col-span-6">
        {!r ? <LoadingState rows={3} /> : (
          <div className="grid grid-cols-3 gap-y-5 gap-x-4">
            <MetricCell label="TSR 1Y" value={signedPct(r.tsr_1y)} tone={tone(r.tsr_1y)} />
            <MetricCell label="TSR 3Y" value={signedPct(r.tsr_3y)} tone={tone(r.tsr_3y)} />
            <MetricCell label="TSR 5Y" value={signedPct(r.tsr_5y)} tone={tone(r.tsr_5y)} />
            <MetricCell label="Drawdown from peak" value={r.drawdown_from_peak !== null ? `${(r.drawdown_from_peak * 100).toFixed(1)}%` : "—"} tone={r.drawdown_from_peak !== null && r.drawdown_from_peak < -0.2 ? "err" : "default"} />
          </div>
        )}
      </Panel>
    </div>
  );
}

function tone(v: number | null | undefined) {
  if (v === null || v === undefined) return "default" as const;
  return v >= 0 ? "ok" as const : "err" as const;
}
