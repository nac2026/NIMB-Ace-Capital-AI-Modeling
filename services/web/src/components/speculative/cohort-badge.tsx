"use client";

import type { Cohort } from "@/lib/api";

// Three distinct visual treatments per cohort:
// Value Universe       — brand navy filled (the "investable" tier)
// Fundamental Universe — navy outline       (tracked with caveats)
// Out of Universe      — err-red outline    (rejected by hard signal)
// Unknown              — muted grey         (no data)

const STYLES: Record<Cohort, { bg: string; fg: string; border: string; label: string }> = {
  value_universe: {
    bg: "var(--brand)",
    fg: "#ffffff",
    border: "var(--brand)",
    label: "Value Universe",
  },
  fundamental_universe: {
    bg: "transparent",
    fg: "var(--brand)",
    border: "var(--brand)",
    label: "Fundamental",
  },
  out_of_universe: {
    bg: "transparent",
    fg: "var(--err)",
    border: "var(--err)",
    label: "Out of Universe",
  },
  unknown: {
    bg: "transparent",
    fg: "var(--fg-dim)",
    border: "var(--fg-dim)",
    label: "Unknown",
  },
};

export function CohortBadge({
  cohort,
  size = "md",
}: {
  cohort: Cohort;
  size?: "sm" | "md";
}) {
  const s = STYLES[cohort] || STYLES.unknown;
  const cls = size === "sm"
    ? "px-1.5 py-0.5 text-[10px]"
    : "px-2 py-1 text-[11px]";
  return (
    <span
      className={`inline-flex items-center justify-center rounded-md font-semibold uppercase tracking-widest ${cls}`}
      style={{
        background: s.bg,
        color: s.fg,
        border: `1px solid ${s.border}`,
        whiteSpace: "nowrap",
      }}
    >
      {s.label}
    </span>
  );
}
