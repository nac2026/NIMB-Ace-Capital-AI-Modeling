"use client";

// Transposed metric grid — rows are metrics, columns are scrips. Numeric
// rows show a subtle heatmap (best value in row highlighted) so analysts
// can scan dominance at a glance. Categorical rows render chips.

import { useQueries } from "@tanstack/react-query";
import { api, UniverseRow } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Panel, LoadingState, EmptyState, npr } from "@/components/scrip/primitives";
import {
  QualityTierChip, QuadrantChip, SelfValuationChip, MarketCapChip, ScoreBadge,
} from "@/components/dashboard/chips";

type BetterWhen = "higher" | "lower";

type MetricDef = {
  label: string;
  group: "Identity" | "Size & market" | "Returns" | "Valuation" | "Fundamentals" | "Asset quality" | "Capital" | "Dividend" | "Quality";
  format: (r: UniverseRow) => React.ReactNode;
  rawValue?: (r: UniverseRow) => number | null;
  betterWhen?: BetterWhen;
};

function pct(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

function pctRaw(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined) return "—";
  return `${v.toFixed(digits)}%`;
}

const METRICS: MetricDef[] = [
  { label: "Company",   group: "Identity", format: (r) => <span className="text-fg">{r.company_name}</span> },
  { label: "Sector",    group: "Identity", format: (r) => <span className="text-fg-muted">{r.sector}</span> },

  { label: "Market cap",    group: "Size & market", format: (r) => npr(r.market_cap_npr), rawValue: (r) => r.market_cap_npr, betterWhen: "higher" },
  { label: "Size",          group: "Size & market", format: (r) => <MarketCapChip tier={r.market_cap_tier} /> },
  { label: "Price",         group: "Size & market", format: (r) => r.latest_close?.toFixed(2) ?? "—", rawValue: (r) => r.latest_close },
  { label: "1D change",     group: "Size & market", format: (r) => r.change_pct !== null ? `${r.change_pct.toFixed(2)}%` : "—", rawValue: (r) => r.change_pct, betterWhen: "higher" },

  { label: "6M return",     group: "Returns", format: (r) => pct(r.return_6m), rawValue: (r) => r.return_6m, betterWhen: "higher" },

  { label: "P/E",                group: "Valuation", format: (r) => r.pe_ratio?.toFixed(2) ?? "—", rawValue: (r) => r.pe_ratio, betterWhen: "lower" },
  { label: "Vs own P/E",         group: "Valuation", format: (r) => <SelfValuationChip tier={r.self_valuation_tier} /> },

  { label: "ROE",    group: "Fundamentals", format: (r) => pct(r.roe), rawValue: (r) => r.roe, betterWhen: "higher" },
  { label: "CD",     group: "Fundamentals", format: (r) => pct(r.cd_ratio, 1), rawValue: (r) => r.cd_ratio, betterWhen: "lower" },

  { label: "NPL",    group: "Asset quality", format: (r) => pct(r.npl_ratio, 2), rawValue: (r) => r.npl_ratio, betterWhen: "lower" },
  { label: "CAR",    group: "Capital",       format: (r) => pct(r.car, 2),       rawValue: (r) => r.car,       betterWhen: "higher" },

  { label: "Total yield",    group: "Dividend", format: (r) => pctRaw(r.total_dividend_yield), rawValue: (r) => r.total_dividend_yield, betterWhen: "higher" },

  { label: "Composite score", group: "Quality", format: (r) => <ScoreBadge v={r.scorecard_0_100} />, rawValue: (r) => r.scorecard_0_100, betterWhen: "higher" },
  { label: "Quality tier",    group: "Quality", format: (r) => <QualityTierChip tier={r.quality_tier} /> },
  { label: "Quadrant",        group: "Quality", format: (r) => <QuadrantChip quadrant={r.quadrant} /> },
];

export function MetricGrid({ scrips }: { scrips: string[] }) {
  // Pull from /api/universe (already carries every field we need) and
  // pick the requested scrips. One query for everyone, no per-scrip fan-out.
  const queries = useQueries({
    queries: [{
      queryKey: ["universe"],
      queryFn: api.universe,
    }],
  });

  const universe = queries[0];
  const rows = (universe.data ?? []).filter((r) => scrips.includes(r.scrip));
  // Preserve the order the user picked
  const ordered = scrips.map((s) => rows.find((r) => r.scrip === s)).filter(Boolean) as UniverseRow[];

  if (universe.isLoading) {
    return (
      <Panel title="Metric comparison">
        <LoadingState rows={6} />
      </Panel>
    );
  }

  if (!ordered.length) {
    return (
      <Panel title="Metric comparison">
        <EmptyState message="No data for the selected scrips." />
      </Panel>
    );
  }

  // Group metrics for section headers
  const groups: Record<string, MetricDef[]> = {};
  METRICS.forEach((m) => {
    if (!groups[m.group]) groups[m.group] = [];
    groups[m.group].push(m);
  });

  return (
    <Panel title="Metric comparison" hint="Best value per row highlighted">
      <div className="overflow-x-auto">
        <table className="w-full text-[12.5px]">
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border)" }}>
              <th className="py-2 px-3 text-left label sticky left-0 bg-bg-panel z-10">Metric</th>
              {ordered.map((r) => (
                <th key={r.scrip} className="py-2 px-3 text-left">
                  <div className="text-[13px] font-semibold text-fg">{r.scrip}</div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Object.entries(groups).map(([group, metrics]) => (
              <GroupRows key={group} group={group} metrics={metrics} rows={ordered} />
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function GroupRows({
  group,
  metrics,
  rows,
}: {
  group: string;
  metrics: MetricDef[];
  rows: UniverseRow[];
}) {
  return (
    <>
      <tr>
        <td
          colSpan={1 + rows.length}
          className="py-2 px-3 text-[10.5px] font-semibold uppercase tracking-wider text-fg-dim"
          style={{ background: "var(--bg-subtle)", borderBottom: "1px solid var(--border-subtle)" }}
        >
          {group}
        </td>
      </tr>
      {metrics.map((m) => {
        const values = rows.map((r) => m.rawValue?.(r) ?? null);
        const numeric = values.filter((v): v is number => v !== null);
        const best: number | null = numeric.length === 0 ? null :
          m.betterWhen === "lower" ? Math.min(...numeric) :
          m.betterWhen === "higher" ? Math.max(...numeric) :
          null;
        return (
          <tr key={m.label} className="hover:bg-bg-hover" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
            <td className="py-2 px-3 text-fg-muted sticky left-0 bg-bg-panel z-10">{m.label}</td>
            {rows.map((r, i) => {
              const v = values[i];
              const isBest = best !== null && v === best;
              return (
                <td
                  key={r.scrip}
                  className={cn(
                    "py-2 px-3 num tabular-nums",
                    isBest && "font-semibold",
                  )}
                  style={isBest ? { background: "var(--ok)", color: "var(--bg)", borderRadius: 4 } : undefined}
                >
                  <div className={isBest ? "inline-flex rounded px-1" : undefined}>
                    {m.format(r)}
                  </div>
                </td>
              );
            })}
          </tr>
        );
      })}
    </>
  );
}
