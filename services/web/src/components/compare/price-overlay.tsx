"use client";

// Overlaid price chart for 2-5 scrips, normalized to 100 at the earliest
// shared date so magnitudes are comparable regardless of absolute price.

import { useQueries } from "@tanstack/react-query";
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
} from "recharts";
import { api } from "@/lib/api";
import { Panel, EmptyState, LoadingState } from "@/components/scrip/primitives";

const SERIES_COLORS = ["var(--fg)", "var(--ok)", "var(--warn)", "var(--err)", "var(--fg-muted)"];

export function PriceOverlay({ scrips }: { scrips: string[] }) {
  const queries = useQueries({
    queries: scrips.map((s) => ({
      queryKey: ["prices", s, 180],
      queryFn: () => api.prices(s, 180),
    })),
  });

  const loading = queries.some((q) => q.isLoading);
  const allData = queries.map((q) => q.data ?? []);

  // Align on the intersection of dates — simple approach: pick the
  // earliest-common-date and rebase every series to 100 at that point.
  const chartData = buildNormalized(scrips, allData);

  return (
    <Panel title="Price (normalized to 100)" hint="180-day window, rebased so % moves are directly comparable">
      {loading ? (
        <LoadingState rows={4} />
      ) : !chartData.length ? (
        <EmptyState message="No shared price history for these scrips." />
      ) : (
        <div className="h-[280px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <CartesianGrid stroke="var(--border-subtle)" vertical={false} />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: "var(--fg-muted)" }} tickLine={false} axisLine={false} minTickGap={40} />
              <YAxis tick={{ fontSize: 10, fill: "var(--fg-muted)" }} tickLine={false} axisLine={false} width={38} />
              <Tooltip
                contentStyle={{ background: "var(--bg-panel)", border: "1px solid var(--border)", borderRadius: 6, fontSize: 11 }}
                formatter={(v) => [typeof v === "number" ? v.toFixed(1) : "—", ""]}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {scrips.map((s, i) => (
                <Line
                  key={s}
                  type="monotone"
                  dataKey={s}
                  stroke={SERIES_COLORS[i % SERIES_COLORS.length]}
                  strokeWidth={1.5}
                  dot={false}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </Panel>
  );
}

function buildNormalized(
  scrips: string[],
  series: Array<{ date: string; close: number }[]>,
) {
  const firstClose: Record<string, number> = {};
  const byDate = new Map<string, Record<string, number>>();
  scrips.forEach((s, i) => {
    const rows = series[i] ?? [];
    if (!rows.length) return;
    firstClose[s] = rows[0].close;
    rows.forEach((p) => {
      if (!byDate.has(p.date)) byDate.set(p.date, {});
      const base = firstClose[s] || 1;
      byDate.get(p.date)![s] = (p.close / base) * 100;
    });
  });
  return Array.from(byDate.entries())
    .sort(([a], [b]) => (a < b ? -1 : 1))
    .map(([date, vals]) => ({ date, ...vals }));
}
