"use client";

// Small descriptive pills used across the universe table + scrip detail.
// Each takes the raw tier / quadrant string (exact enum from Postgres) and
// maps to a tone. Labels are pretty-printed from the enum so backend
// changes surface as readable chips without a rename.

import { cn } from "@/lib/utils";

type Tone = "ok" | "warn" | "err" | "fg" | "muted";

const TONE: Record<Tone, { bg: string; text: string }> = {
  ok:     { bg: "bg-ok/10",        text: "text-ok" },
  warn:   { bg: "bg-warn/12",      text: "text-warn" },
  err:    { bg: "bg-err/10",       text: "text-err" },
  fg:     { bg: "bg-fg",           text: "" },           // inverted (dark bg, light text) — styled inline
  muted:  { bg: "bg-bg-hover",     text: "text-fg-muted" },
};

function prettify(v: string): string {
  return v.replace(/_/g, " ").toLowerCase().replace(/(^|\s)\w/g, (m) => m.toUpperCase());
}

export function Pill({ label, tone, title }: { label: string; tone: Tone; title?: string }) {
  const t = TONE[tone];
  const isInverted = tone === "fg";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md px-1.5 py-0.5 text-[10.5px] font-semibold uppercase tracking-wide whitespace-nowrap",
        t.bg,
        t.text,
      )}
      style={isInverted ? { color: "var(--bg)" } : undefined}
      title={title ?? label}
    >
      {prettify(label)}
    </span>
  );
}

// Quality tier chip — TOP_DECILE → ok, STRONG → ok, AVERAGE → muted, BELOW_AVERAGE → warn, WEAK → err
const QUALITY_TONE: Record<string, Tone> = {
  TOP_DECILE: "fg",
  STRONG: "ok",
  AVERAGE: "muted",
  BELOW_AVERAGE: "warn",
  WEAK: "err",
};

export function QualityTierChip({ tier }: { tier: string | null }) {
  if (!tier) return <span className="text-fg-dim">—</span>;
  return <Pill label={tier} tone={QUALITY_TONE[tier] ?? "muted"} />;
}

const QUADRANT_TONE: Record<string, Tone> = {
  QUALITY_LEADER: "ok",
  CONTRARIAN_BET: "warn",
  MOMENTUM_TRAP: "warn",
  AVOID: "err",
};

export function QuadrantChip({ quadrant }: { quadrant: string | null }) {
  if (!quadrant) return <span className="text-fg-dim">—</span>;
  return <Pill label={quadrant} tone={QUADRANT_TONE[quadrant] ?? "muted"} />;
}

const SELF_VAL_TONE: Record<string, Tone> = {
  VERY_CHEAP: "ok",
  CHEAP: "ok",
  FAIR: "muted",
  EXPENSIVE: "warn",
  VERY_EXPENSIVE: "err",
};

export function SelfValuationChip({ tier }: { tier: string | null }) {
  if (!tier) return <span className="text-fg-dim">—</span>;
  return <Pill label={tier} tone={SELF_VAL_TONE[tier] ?? "muted"} />;
}

const MKT_CAP_TONE: Record<string, Tone> = {
  LARGE: "fg",
  MID: "muted",
  SMALL: "muted",
  MICRO: "muted",
};

export function MarketCapChip({ tier }: { tier: string | null }) {
  if (!tier) return <span className="text-fg-dim">—</span>;
  return <Pill label={tier} tone={MKT_CAP_TONE[tier] ?? "muted"} />;
}

// 0-100 scorecard → compact colored numeric badge.
export function ScoreBadge({ v }: { v: number | null }) {
  if (v === null) return <span className="text-fg-dim">—</span>;
  const tone: Tone = v >= 70 ? "ok" : v >= 45 ? "muted" : "err";
  const t = TONE[tone];
  return (
    <span className={cn("num inline-block rounded-md px-2 py-0.5 text-[12px] font-semibold tabular-nums", t.bg, t.text)}>
      {v.toFixed(0)}
    </span>
  );
}
