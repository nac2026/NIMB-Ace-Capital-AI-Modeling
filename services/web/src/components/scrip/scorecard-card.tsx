"use client";

// 0-100 composite with 5 component percentiles. Each component renders as
// a horizontal stacked bar — length proportional to percentile, so the
// eye instantly sees which pillar is pulling the score up or down.

import type { ScorecardRow } from "@/lib/api";
import { cn } from "@/lib/utils";

const COMPONENTS: Array<{ key: keyof ScorecardRow; label: string; hint: string }> = [
  { key: "quality_pct",    label: "Quality",    hint: "Fundamental-quality composite (ROE, asset quality, capital, efficiency, growth, Piotroski)" },
  { key: "valuation_pct",  label: "Valuation",  hint: "Lower P/E and P/B → higher percentile" },
  { key: "momentum_pct",   label: "Momentum",   hint: "6-month price return vs peers" },
  { key: "risk_pct",       label: "Risk",       hint: "Lower realized vol → higher percentile" },
  { key: "income_pct",     label: "Income",     hint: "Total dividend yield vs peers" },
];

export function CompositeScorecardCard({ row }: { row: ScorecardRow | null | undefined }) {
  if (!row) return <div className="text-[13px] text-fg-muted">No scorecard.</div>;
  const score = row.scorecard_0_100;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-baseline gap-2">
        <span className="num text-[32px] font-semibold text-fg">{score !== null ? score.toFixed(0) : "—"}</span>
        <span className="text-[13px] text-fg-muted">/ 100</span>
        <span className="ml-2 label">Composite Analytics Score</span>
      </div>

      <div className="flex flex-col gap-2">
        {COMPONENTS.map((c) => {
          const raw = row[c.key] as number | null;
          const v = raw === null || raw === undefined ? null : raw * 100;
          const tone = v === null ? "muted" : v >= 60 ? "ok" : v >= 40 ? "muted" : "err";
          return (
            <div key={c.key as string} className="flex items-center gap-3" title={c.hint}>
              <div className="w-[84px] text-[11.5px] font-semibold uppercase tracking-wide text-fg-muted">{c.label}</div>
              <div className="flex-1 relative h-3 rounded-full bg-bg-hover overflow-hidden">
                <div
                  className={cn(
                    "absolute inset-y-0 left-0 rounded-full",
                    tone === "ok"  ? "bg-ok"  :
                    tone === "err" ? "bg-err" :
                                     "bg-fg-muted",
                  )}
                  style={{ width: v !== null ? `${Math.max(2, v)}%` : 0 }}
                />
              </div>
              <div className="w-[48px] text-right num text-[12px] font-semibold tabular-nums text-fg">
                {v === null ? "—" : `${v.toFixed(0)}`}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
