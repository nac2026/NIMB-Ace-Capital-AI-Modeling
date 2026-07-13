"use client";

// Label-over-value cell used in the vital-stats grid.
// Renders "—" with a tooltip when the value is unavailable in the current
// dataset (phase-2 vendor data).

import { Info } from "lucide-react";

export function MetricCell({
  label,
  value,
  tooltip,
}: {
  label: string;
  value: string | number | null | undefined;
  tooltip?: string;
}) {
  const missing = value === null || value === undefined || value === "";
  return (
    <div className="rounded-md p-3" style={{ background: "var(--bg-subtle)" }}>
      <div className="flex items-center gap-1 text-[10px] uppercase tracking-widest text-fg-dim">
        {label}
        {missing && tooltip && (
          <span className="group relative inline-flex">
            <Info className="h-2.5 w-2.5 cursor-help" strokeWidth={2} />
            <span
              role="tooltip"
              className="pointer-events-none absolute left-1/2 top-full z-50 mt-1.5 -translate-x-1/2 whitespace-nowrap rounded-md px-2 py-1 text-[10.5px] font-medium normal-case tracking-normal opacity-0 transition-opacity duration-150 delay-150 group-hover:opacity-100"
              style={{ background: "var(--fg)", color: "var(--bg)", boxShadow: "var(--shadow-md)" }}
            >
              {tooltip}
            </span>
          </span>
        )}
      </div>
      <div
        className={`mt-1 num text-[15px] font-semibold ${missing ? "" : "text-fg"}`}
        style={missing ? { color: "var(--fg-dim)" } : undefined}
      >
        {missing ? "—" : value}
      </div>
    </div>
  );
}
