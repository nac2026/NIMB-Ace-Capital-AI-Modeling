"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import {
  QualityTierChip,
} from "@/components/dashboard/chips";
import { Panel, EmptyState, LoadingState } from "./primitives";
import { CompositeScorecardCard } from "./scorecard-card";
import { PiotroskiGrid } from "./piotroski-grid";
import { QuadrantChart } from "./quadrant-chart";

export function TabQuality({ scrip }: { scrip: string }) {
  const scorecard = useQuery({ queryKey: ["scorecard"], queryFn: api.scorecard });
  const piotroski = useQuery({
    queryKey: ["piotroski", scrip, 8],
    queryFn: () => api.scrip.piotroski(scrip, 8),
  });
  const quality = useQuery({
    queryKey: ["quality", scrip, 8],
    queryFn: () => api.scrip.quality(scrip, 8),
  });

  const myScorecard = scorecard.data?.find((r) => r.scrip === scrip);
  const latestPiotroski = piotroski.data?.[piotroski.data.length - 1];
  const latestQuality = quality.data?.[quality.data.length - 1];

  return (
    <div className="grid grid-cols-12 gap-4">
      <Panel title="Composite scorecard (0–100)" className="col-span-6">
        {scorecard.isLoading ? (
          <LoadingState rows={5} />
        ) : !myScorecard ? (
          <EmptyState message="No scorecard data." />
        ) : (
          <CompositeScorecardCard row={myScorecard} />
        )}
      </Panel>

      <Panel
        title="Latest quality posture"
        className="col-span-6"
        right={
          <div className="flex items-center gap-2">
            <QualityTierChip tier={latestQuality?.quality_tier ?? null} />
          </div>
        }
      >
        {quality.isLoading ? (
          <LoadingState rows={4} />
        ) : !latestQuality ? (
          <EmptyState message="No quality-composite data." />
        ) : (
          <div className="grid grid-cols-3 gap-3">
            <QualitySubMetric label="Profitability"  value={latestQuality.profitability_pct} />
            <QualitySubMetric label="Asset quality"  value={latestQuality.asset_quality_pct} />
            <QualitySubMetric label="Growth"         value={latestQuality.growth_pct} />
            <QualitySubMetric label="Capital"        value={latestQuality.capital_pct} />
            <QualitySubMetric label="Efficiency"     value={latestQuality.efficiency_pct} />
            <QualitySubMetric label="Piotroski"      value={latestQuality.piotroski_pct} />
            <div className="col-span-3 flex items-baseline gap-2 pt-1" style={{ borderTop: "1px solid var(--border-subtle)" }}>
              <span className="num text-[22px] font-semibold text-fg">
                {latestQuality.quality_score_0_100?.toFixed(0) ?? "—"}
              </span>
              <span className="text-[12px] text-fg-muted">/ 100 fundamental-quality composite</span>
            </div>
          </div>
        )}
      </Panel>

      <Panel title="Piotroski F-Score" hint="Bank-adapted, 9 signals" className="col-span-12">
        {piotroski.isLoading ? <LoadingState rows={3} /> : <PiotroskiGrid row={latestPiotroski} />}
      </Panel>

      <Panel
        title="Quality × 6M momentum"
        hint="This scrip highlighted vs sector peers"
        className="col-span-12"
      >
        <QuadrantChart scrip={scrip} />
      </Panel>
    </div>
  );
}

function QualitySubMetric({ label, value }: { label: string; value: number | null }) {
  const pct = value === null || value === undefined ? null : value * 100;
  return (
    <div className="flex flex-col gap-1">
      <div className="label">{label}</div>
      <div className="flex items-center gap-2">
        <div className="flex-1 h-1.5 rounded-full bg-bg-hover overflow-hidden">
          <div
            className="h-full rounded-full"
            style={{
              width: pct !== null ? `${Math.max(2, Math.min(100, pct))}%` : 0,
              background: "var(--fg)",
            }}
          />
        </div>
        <div className="num w-[34px] text-right text-[12px] font-semibold tabular-nums text-fg">
          {pct === null ? "—" : pct.toFixed(0)}
        </div>
      </div>
    </div>
  );
}
