"use client";

import type { Flag } from "@/lib/api";

const STYLES: Record<Flag, { bg: string; fg: string; label: string }> = {
  green:   { bg: "var(--ok)",   fg: "#ffffff", label: "GREEN" },
  amber:   { bg: "var(--warn)", fg: "#1c2331", label: "AMBER" },
  red:     { bg: "var(--err)",  fg: "#ffffff", label: "RED" },
  unknown: { bg: "var(--fg-dim)", fg: "#ffffff", label: "UNKNOWN" },
};

export function FlagBadge({
  flag,
  size = "md",
}: {
  flag: Flag;
  size?: "sm" | "md";
}) {
  const s = STYLES[flag];
  const cls = size === "sm"
    ? "px-1.5 py-0.5 text-[10px]"
    : "px-2 py-1 text-[11px]";
  return (
    <span
      className={`inline-flex items-center justify-center rounded-md font-bold uppercase tracking-widest ${cls}`}
      style={{ background: s.bg, color: s.fg }}
    >
      {s.label}
    </span>
  );
}

export function FlagDot({ flag }: { flag: Flag | "green" | "amber" | "red" }) {
  const s = STYLES[flag as Flag] || STYLES.unknown;
  return (
    <span
      className="inline-block h-2 w-2 shrink-0 rounded-full"
      style={{ background: s.bg }}
    />
  );
}
