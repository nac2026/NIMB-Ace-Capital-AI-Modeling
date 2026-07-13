"use client";

// NEPSE intraday — live index value curve for the current session (SMTM
// indices-timeseries). Sits atop Market Intelligence as the market's pulse.

import { useQuery } from "@tanstack/react-query";
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
} from "recharts";
import { api } from "@/lib/api";

export function IndexIntraday({ slug = "nepse" }: { slug?: string }) {
  const q = useQuery({
    queryKey: ["index-intraday", slug],
    queryFn: () => api.indexTimeseries(slug),
    staleTime: 60_000,
    refetchInterval: 60_000,
  });

  const series = q.data?.series ?? [];
  const first = series[0]?.value ?? null;
  const last = series[series.length - 1]?.value ?? null;
  const up = first != null && last != null && last >= first;
  const change = first != null && last != null ? last - first : null;
  const changePct = change != null && first ? (change / first) * 100 : null;
  const color = up ? "var(--pos)" : "var(--neg)";
  const name = q.data?.name ?? slug.toUpperCase();

  return (
    <section
      className="panel overflow-hidden"
      style={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: 14 }}
    >
      <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: "1px solid var(--line)" }}>
        <div className="flex items-baseline gap-3">
          <div className="eyebrow">{name} · Intraday</div>
          {last != null && (
            <>
              <span className="mono text-[15px] font-semibold text-fg tabular-nums">{last.toFixed(2)}</span>
              {change != null && (
                <span className="mono text-[12px] font-semibold tabular-nums" style={{ color }}>
                  {change >= 0 ? "▲" : "▼"} {Math.abs(change).toFixed(2)} ({changePct?.toFixed(2)}%)
                </span>
              )}
            </>
          )}
        </div>
        <span className="text-[10px] uppercase tracking-wider" style={{ color: "var(--fg-dim)" }}>
          {q.isFetching ? "live…" : "SMTM"}
        </span>
      </div>
      <div className="p-3">
        {q.isLoading ? (
          <div className="h-[160px] animate-pulse rounded-lg" style={{ background: "var(--panel-2)" }} />
        ) : series.length < 2 ? (
          <div className="flex h-[160px] items-center justify-center text-[13px]" style={{ color: "var(--fg-muted)" }}>
            No intraday session yet — the market hasn&apos;t traded today.
          </div>
        ) : (
          <div className="h-[160px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={series}>
                <defs>
                  <linearGradient id="nepse-iday" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={color} stopOpacity={0.25} />
                    <stop offset="100%" stopColor={color} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="var(--border-subtle, var(--line))" vertical={false} />
                <XAxis
                  dataKey="t"
                  tick={{ fontSize: 10, fill: "var(--fg-muted)" }}
                  tickLine={false}
                  axisLine={false}
                  minTickGap={56}
                  tickFormatter={(t: string) => (t?.length >= 16 ? t.slice(11, 16) : t)}
                />
                <YAxis
                  tick={{ fontSize: 10, fill: "var(--fg-muted)" }}
                  tickLine={false}
                  axisLine={false}
                  width={52}
                  domain={["auto", "auto"]}
                  tickFormatter={(v: number) => v.toFixed(0)}
                />
                <Tooltip
                  contentStyle={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: 8, fontSize: 12 }}
                  labelStyle={{ color: "var(--fg-muted)" }}
                  labelFormatter={(t) => (typeof t === "string" && t.length >= 16 ? t.slice(11, 16) : String(t))}
                  formatter={(v) => [typeof v === "number" ? v.toFixed(2) : "—", name]}
                />
                <Area type="monotone" dataKey="value" stroke={color} strokeWidth={1.5} fill="url(#nepse-iday)" dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </section>
  );
}
