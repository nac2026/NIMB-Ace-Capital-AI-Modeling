"use client";

import { FlagDot } from "./flag-badge";
import type { RuleOutcome } from "@/lib/api";

const RULE_LABELS: Record<string, string> = {
  asset_quality:     "Asset quality (NPL)",
  npl_trend:         "NPL trend (YoY)",
  capital:           "Capital adequacy",
  piotroski:         "Piotroski F-score",
  quality_composite: "Quality composite",
  valuation_self:    "Valuation vs own history",
  momentum:          "Price momentum (6m)",
  drawdown:          "Drawdown from peak",
  volatility:        "Realized volatility",
};

function order(o: RuleOutcome): number {
  return { red: 0, amber: 1, green: 2 }[o.status as "red" | "amber" | "green"] ?? 3;
}

export function RuleOutcomesList({ outcomes }: { outcomes: RuleOutcome[] }) {
  if (!outcomes || outcomes.length === 0) {
    return <div className="text-[12px] text-fg-muted">No rule data.</div>;
  }
  const sorted = [...outcomes].sort((a, b) => order(a) - order(b));
  return (
    <ul className="space-y-1.5">
      {sorted.map((o) => (
        <li key={o.rule} className="flex items-start gap-2.5 text-[12px]">
          <span className="pt-1.5"><FlagDot flag={o.status} /></span>
          <div className="min-w-0 flex-1">
            <div className="font-medium text-fg">{RULE_LABELS[o.rule] || o.rule}</div>
            <div className="mt-0.5 text-[11.5px] text-fg-muted">{o.threshold}</div>
          </div>
        </li>
      ))}
    </ul>
  );
}
