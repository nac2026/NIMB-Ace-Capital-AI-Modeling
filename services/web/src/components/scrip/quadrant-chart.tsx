"use client";

// 2×2 quality-momentum scatter with this scrip highlighted. X = 6m return,
// Y = quality score 0-100. Sector medians are the axis-cross lines, so the
// 4 quadrants read as QUALITY_LEADER / CONTRARIAN_BET / MOMENTUM_TRAP / AVOID.

import { useQuery } from "@tanstack/react-query";
import {
  ResponsiveContainer, ScatterChart, Scatter, CartesianGrid, XAxis, YAxis, ZAxis, Tooltip, ReferenceLine,
} from "recharts";
import { api } from "@/lib/api";
import { LoadingState, EmptyState } from "./primitives";

export function QuadrantChart({ scrip }: { scrip: string }) {
  const quadrant = useQuery({ queryKey: ["quadrant"], queryFn: api.quadrant });

  if (quadrant.isLoading) return <LoadingState rows={4} />;
  const rows = quadrant.data ?? [];
  if (!rows.length) return <EmptyState message="No quadrant data." />;

  const xs = rows.map((r) => (r.return_6m ?? 0) * 100);
  const medX = rows[0]?.sector_return_6m_median !== null && rows[0]?.sector_return_6m_median !== undefined
    ? rows[0].sector_return_6m_median * 100
    : null;
  const medY = rows[0]?.sector_quality_median ?? null;

  const others = rows
    .filter((r) => r.scrip !== scrip && r.return_6m !== null && r.quality_score_0_100 !== null)
    .map((r) => ({ x: (r.return_6m as number) * 100, y: r.quality_score_0_100 as number, scrip: r.scrip }));
  const me = rows.find((r) => r.scrip === scrip && r.return_6m !== null && r.quality_score_0_100 !== null);
  const meData = me ? [{ x: (me.return_6m as number) * 100, y: me.quality_score_0_100 as number, scrip: me.scrip }] : [];

  return (
    <div className="h-[280px]">
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 12, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid stroke="var(--border-subtle)" />
          <XAxis
            type="number"
            dataKey="x"
            name="6M return"
            unit="%"
            tick={{ fontSize: 10, fill: "var(--fg-muted)" }}
            tickLine={false}
            axisLine={{ stroke: "var(--border)" }}
            domain={[Math.min(...xs) - 5, Math.max(...xs) + 5]}
          />
          <YAxis
            type="number"
            dataKey="y"
            name="Quality"
            tick={{ fontSize: 10, fill: "var(--fg-muted)" }}
            tickLine={false}
            axisLine={{ stroke: "var(--border)" }}
            domain={[0, 100]}
          />
          <ZAxis range={[60, 60]} />
          {medX !== null && <ReferenceLine x={medX} stroke="var(--fg-dim)" strokeDasharray="4 3" />}
          {medY !== null && <ReferenceLine y={medY} stroke="var(--fg-dim)" strokeDasharray="4 3" />}
          <Tooltip
            cursor={{ strokeDasharray: "3 3" }}
            contentStyle={{ background: "var(--bg-panel)", border: "1px solid var(--border)", borderRadius: 6, fontSize: 11 }}
            formatter={(v, name) => [typeof v === "number" ? v.toFixed(1) : "—", String(name)]}
          />
          <Scatter data={others} fill="var(--fg-muted)" fillOpacity={0.5} />
          <Scatter data={meData} fill="var(--fg)" shape="circle" />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
