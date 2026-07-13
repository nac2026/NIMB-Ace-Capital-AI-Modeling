"use client";

// Sector momentum heatmap — the design's "Sector Sentiment Heatmap" signature
// panel, wired to /api/sector-momentum (avg 6M / 3M returns). Values are
// normalized to [-1,1] relative to the strongest sector so the colour scale
// reads cleanly; the cell text shows the normalized intensity.

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Heatmap, type HeatRow } from "@/components/viz";

export function SectorHeatmap() {
  const q = useQuery({ queryKey: ["sector-momentum"], queryFn: api.sectorMomentum });
  const data = q.data ?? [];

  const maxAbs = (sel: (r: (typeof data)[number]) => number | null) =>
    Math.max(0.0001, ...data.map((r) => Math.abs(sel(r) ?? 0)));
  const m6 = maxAbs((r) => r.avg_return_6m);
  const m3 = maxAbs((r) => r.avg_return_3m);

  const rows: HeatRow[] = [...data]
    .sort((a, b) => (b.avg_return_6m ?? 0) - (a.avg_return_6m ?? 0))
    .map((r) => ({
      sector: r.sector,
      sentiment: (r.avg_return_6m ?? 0) / m6,
      flow: (r.avg_return_3m ?? 0) / m3,
    }));

  return (
    <div className="panel p-4">
      <div className="mb-3">
        <h3 className="text-[12.5px] font-semibold uppercase tracking-wider text-fg">Sector momentum heatmap</h3>
        <p className="mt-0.5 text-[11px] text-fg-muted">where capital is rotating · relative 6M / 3M returns</p>
      </div>
      {q.isLoading ? (
        <div className="py-8 text-center text-[12px] text-fg-muted">Loading sectors…</div>
      ) : rows.length === 0 ? (
        <div className="py-8 text-center text-[12px] text-fg-muted">No sector data.</div>
      ) : (
        <Heatmap rows={rows} colLabels={["6M momentum", "3M momentum"]} />
      )}
    </div>
  );
}
