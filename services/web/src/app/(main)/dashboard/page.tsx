"use client";
// Market Intelligence — the analytics summary (the design's "Management view"):
//   headline KPIs + Fear-&-Greed · Top Red / Green flags ·
//   Sector sentiment + Pattern & manipulation alerts ·
//   News impact timeline + market sentiment breadth.
// No single-stock chart here — this is the market overview.

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { MarketSummary } from "@/components/dashboard/market-summary";
import { SectorHeatmap } from "@/components/dashboard/sector-heatmap";
import { AlertsFeed, NewsTimeline, SentimentBreadth } from "@/components/dashboard/intel-panels";
import { IndexIntraday } from "@/components/dashboard/index-intraday";

export default function DashboardPage() {
  const indices = useQuery({ queryKey: ["indices"], queryFn: api.indices });
  const asOf = indices.data?.[0]?.date ?? "—";

  return (
    <div className="h-full overflow-y-auto" style={{ background: "var(--bg)" }}>
      {/* Page header */}
      <div className="flex items-center justify-between px-6 py-4" style={{ borderBottom: "1px solid var(--line)", background: "var(--panel)" }}>
        <div>
          <div className="eyebrow">NEPSE · all sectors</div>
          <h1 className="serif" style={{ fontSize: 22, fontWeight: 600, letterSpacing: "-.01em", marginTop: 2 }}>
            Market Intelligence
          </h1>
        </div>
        <div className="flex items-center gap-2 rounded-xl px-3 py-1.5" style={{ background: "var(--panel-2)", border: "1px solid var(--line)" }}>
          <span className="eyebrow">As of</span>
          <span className="mono text-[13px] font-semibold text-fg">{asOf}</span>
        </div>
      </div>

      <div className="px-6 py-6" style={{ display: "flex", flexDirection: "column", gap: "var(--gap)" }}>
        {/* NEPSE intraday pulse (live from SMTM) */}
        <IndexIntraday slug="nepse" />

        {/* KPIs + Fear/Greed + Top Red / Green flags */}
        <MarketSummary />

        {/* Sector sentiment + market sentiment breadth (both medium height) */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--gap)", alignItems: "start" }}>
          <SectorHeatmap />
          <SentimentBreadth />
        </div>

        {/* News impact timeline + manipulation alerts (both tall) */}
        <div style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr", gap: "var(--gap)", alignItems: "start" }}>
          <NewsTimeline />
          <AlertsFeed />
        </div>
      </div>
    </div>
  );
}
