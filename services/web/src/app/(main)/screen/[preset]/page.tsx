"use client";

// Screen preset route — renders the universe table pre-filtered by one of
// 5 named strategies. Reuses the existing dashboard table by filtering its
// rows in memory; each preset is just a saved filter for now (per plan:
// "screen builder with custom filter UI" is deferred).

import { use, useMemo } from "react";
import { notFound } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api, type UniverseRow } from "@/lib/api";
import { UniverseTable } from "@/components/dashboard/universe-table";

type PresetKey = "top-quality" | "cheap-vs-self" | "high-yield" | "contrarian" | "turnaround";

const PRESETS: Record<PresetKey, {
  title: string;
  hint: string;
  filter: (rows: UniverseRow[]) => UniverseRow[];
}> = {
  "top-quality": {
    title: "Top quality",
    hint: "Composite analytics score ≥ 70.",
    filter: (rs) => rs.filter((r) => (r.scorecard_0_100 ?? 0) >= 70),
  },
  "cheap-vs-self": {
    title: "Cheap vs own history",
    hint: "P/E self-percentile tier is VERY_CHEAP or CHEAP.",
    filter: (rs) => rs.filter((r) => r.self_valuation_tier === "VERY_CHEAP" || r.self_valuation_tier === "CHEAP"),
  },
  "high-yield": {
    title: "High dividend yield",
    hint: "Total dividend yield ≥ 8% (above fixed-deposit rate).",
    filter: (rs) => rs.filter((r) => (r.total_dividend_yield ?? 0) >= 8),
  },
  "contrarian": {
    title: "Contrarian bets",
    hint: "Quality-momentum quadrant is CONTRARIAN_BET (strong quality, weak momentum).",
    filter: (rs) => rs.filter((r) => r.quadrant === "CONTRARIAN_BET"),
  },
  "turnaround": {
    title: "Turnaround candidates",
    hint: "Recovering from low quality — weak tier but NPL trending down.",
    filter: (rs) => rs.filter((r) => (r.quality_tier === "WEAK" || r.quality_tier === "BELOW_AVERAGE") && (r.return_6m ?? 0) > 0),
  },
};

export default function ScreenPage({ params }: { params: Promise<{ preset: string }> }) {
  const { preset } = use(params);
  const cfg = PRESETS[preset as PresetKey];

  const universe = useQuery({ queryKey: ["universe"], queryFn: api.universe });

  const filtered = useMemo(() => {
    if (!cfg || !universe.data) return [];
    return cfg.filter(universe.data);
  }, [cfg, universe.data]);

  if (!cfg) notFound();

  return (
    <div className="h-full overflow-y-auto bg-bg">
      <div
        className="px-6 py-4"
        style={{ borderBottom: "1px solid var(--border-subtle)", background: "var(--bg-panel)" }}
      >
        <div className="flex items-baseline justify-between gap-4">
          <div>
            <h1 className="text-[15px] font-semibold tracking-tight text-fg">{cfg.title}</h1>
            <p className="mt-0.5 text-[12px] text-fg-muted">{cfg.hint}</p>
          </div>
          <div className="rounded-xl px-3 py-1.5 text-[11px] text-fg-dim" style={{ background: "var(--bg-subtle)", border: "1px solid var(--border-subtle)" }}>
            <span className="num text-[13px] font-semibold text-fg">{filtered.length}</span>
            <span className="ml-1">matches</span>
          </div>
        </div>
      </div>

      <div className="px-6 py-5">
        <UniverseTable data={filtered} isLoading={universe.isLoading} />
      </div>
    </div>
  );
}
