"use client";

// Piotroski 9-cell pass/fail grid. Each signal shows as a small square with
// ✓ (pass) or ✗ (fail) and a one-line label on hover. Always cite specific
// failed signals when explaining the score — per the plan display rule.

import { Check, X, Minus } from "lucide-react";
import { cn } from "@/lib/utils";
import type { PiotroskiRow } from "@/lib/api";

const SIGNALS: Array<{ key: keyof Pick<PiotroskiRow,
  | "p1_positive_profit" | "p2_positive_roa" | "p3_profit_grew" | "p4_roa_improved"
  | "p5_npl_not_worse" | "p6_car_not_worse" | "p7_no_large_issuance"
  | "p8_nim_improved" | "p9_cti_improved">; label: string; hint: string }> = [
  { key: "p1_positive_profit",   label: "P1",  hint: "Positive profit" },
  { key: "p2_positive_roa",      label: "P2",  hint: "Positive ROA" },
  { key: "p3_profit_grew",       label: "P3",  hint: "Profit grew YoY" },
  { key: "p4_roa_improved",      label: "P4",  hint: "ROA improved YoY" },
  { key: "p5_npl_not_worse",     label: "P5",  hint: "NPL not worse YoY" },
  { key: "p6_car_not_worse",     label: "P6",  hint: "CAR not worse YoY" },
  { key: "p7_no_large_issuance", label: "P7",  hint: "No large share issuance" },
  { key: "p8_nim_improved",      label: "P8",  hint: "NIM improved" },
  { key: "p9_cti_improved",      label: "P9",  hint: "Cost-to-income improved" },
];

export function PiotroskiGrid({ row }: { row: PiotroskiRow | null | undefined }) {
  if (!row) return <div className="text-[13px] text-fg-muted">No Piotroski data.</div>;
  const score = row.f_score;
  const avail = row.n_signals_available;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-baseline gap-2">
        <span className="num text-[28px] font-semibold text-fg">{score ?? "—"}</span>
        <span className="text-[13px] text-fg-muted">/ {avail ?? 9}</span>
        <span className="ml-2 label">Piotroski F-Score</span>
      </div>
      <div className="grid grid-cols-9 gap-1.5">
        {SIGNALS.map(({ key, label, hint }) => {
          const v = row[key];
          const pass = v === 1;
          const fail = v === 0;
          return (
            <div
              key={key}
              title={`${label}: ${hint} — ${pass ? "Pass" : fail ? "Fail" : "n/a"}`}
              className={cn(
                "flex flex-col items-center gap-1 rounded-md py-2",
                pass ? "bg-ok/12"   : fail ? "bg-err/10"  : "bg-bg-hover",
              )}
            >
              <div className={cn(
                "flex h-6 w-6 items-center justify-center rounded-md",
                pass ? "bg-ok/20 text-ok" : fail ? "bg-err/15 text-err" : "text-fg-dim",
              )}>
                {pass ? <Check className="h-3.5 w-3.5" strokeWidth={2.5} /> : fail ? <X className="h-3.5 w-3.5" strokeWidth={2.5} /> : <Minus className="h-3.5 w-3.5" />}
              </div>
              <div className="text-[10px] font-semibold uppercase tracking-wide text-fg-muted">{label}</div>
            </div>
          );
        })}
      </div>
      <div className="grid grid-cols-9 gap-1.5 text-[10px] text-fg-dim">
        {SIGNALS.map((s) => (
          <div key={s.key} className="truncate text-center leading-tight" title={s.hint}>{s.hint}</div>
        ))}
      </div>
    </div>
  );
}
