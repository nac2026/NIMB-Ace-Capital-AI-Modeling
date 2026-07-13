"use client";

// Per-ticker card. Single clickable row showing:
//   - Symbol · company name
//   - Cohort badge · Flag badge
//   - Inline metric strip (EPS · PE · CAR · NPL · Rating)
//   - One-line remark
//
// Click anywhere on the card → opens the TickerDetailModal with the full
// vital-stats grid + descriptive verdict + scorecard + rule outcomes.

import { useState } from "react";
import { ExternalLink } from "lucide-react";
import type { SpeculativeResult } from "@/lib/api";
import { FlagBadge } from "./flag-badge";
import { CohortBadge } from "./cohort-badge";
import { TickerDetailModal } from "./ticker-detail-modal";

function num(v: unknown, digits = 2): string | null {
  if (typeof v !== "number" || !Number.isFinite(v)) return null;
  return v.toFixed(digits);
}
function pct(v: unknown, digits = 1): string | null {
  if (typeof v !== "number" || !Number.isFinite(v)) return null;
  return `${(v * 100).toFixed(digits)}%`;
}

export function TickerResultCard({ result }: { result: SpeculativeResult }) {
  const [open, setOpen] = useState(false);
  const s = result.snapshot ?? {};

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="panel group flex w-full flex-col gap-2 p-4 text-left transition-all hover:-translate-y-px"
        style={{ boxShadow: "var(--shadow-sm)" }}
      >
        {/* Top line: ticker · company · badges */}
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="mono num text-[17px] font-bold" style={{ color: "var(--brand)" }}>
                {result.scrip}
              </span>
              {result.company_name && (
                <span className="truncate text-[13px] text-fg-muted">{result.company_name}</span>
              )}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <CohortBadge cohort={result.cohort} size="sm" />
            <FlagBadge flag={result.flag} size="sm" />
          </div>
        </div>

        {/* Inline metric strip — research-report style */}
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-[12.5px] text-fg-muted">
          <InlineMetric label="EPS" value={num(s.eps)} />
          <InlineMetric label="PE"  value={num(s.pe_ratio)} />
          <InlineMetric label="CAR" value={pct(s.car)} />
          <InlineMetric label="NPL" value={pct(s.npl_ratio)} />
          <InlineMetric label="Rating" value={null} tooltip="Credit Rating — not in current dataset (phase 2 vendor feed)" />
        </div>

        {/* Remark */}
        {result.headline && (
          <div className="text-[12.5px] leading-relaxed text-fg">
            <span className="font-semibold text-fg-muted">Remarks:</span>{" "}
            <span>{result.headline}</span>
          </div>
        )}

        {/* Subtle "details" hint */}
        <div
          className="mt-1 inline-flex items-center gap-1 self-end text-[10.5px] uppercase tracking-widest text-fg-dim transition-colors group-hover:text-brand"
          style={{ color: undefined }}
        >
          <span className="transition-colors group-hover:[color:var(--brand)]">View details</span>
          <ExternalLink className="h-2.5 w-2.5 transition-colors group-hover:[color:var(--brand)]" strokeWidth={2} />
        </div>
      </button>

      {open && <TickerDetailModal result={result} onClose={() => setOpen(false)} />}
    </>
  );
}

function InlineMetric({
  label, value, tooltip,
}: {
  label: string;
  value: string | null;
  tooltip?: string;
}) {
  if (value === null) {
    return (
      <span className="inline-flex items-center gap-1">
        <span className="text-fg-dim">{label}</span>
        <span className="group/im relative inline-flex items-center">
          <span className="num font-medium" style={{ color: "var(--fg-dim)" }}>—</span>
          {tooltip && (
            <span
              role="tooltip"
              className="pointer-events-none absolute left-1/2 top-full z-50 mt-1.5 -translate-x-1/2 whitespace-nowrap rounded-md px-2 py-1 text-[10.5px] font-medium opacity-0 transition-opacity duration-150 delay-150 group-hover/im:opacity-100"
              style={{ background: "var(--fg)", color: "var(--bg)", boxShadow: "var(--shadow-md)" }}
            >
              {tooltip}
            </span>
          )}
        </span>
      </span>
    );
  }
  return (
    <span>
      <span className="text-fg-dim">{label} </span>
      <span className="num font-medium text-fg">{value}</span>
    </span>
  );
}
