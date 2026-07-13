"use client";

// Four high-signal tiles. Replaced the original generic KPIs per the
// dashboard redesign plan: sector market cap, median composite score,
// TOP_DECILE count, CONTRARIAN_BET count. These are the numbers analysts
// glance at to decide "where in the universe should I look first".

import { Coins, Gauge, Trophy, Crosshair, LucideIcon } from "lucide-react";
import { UniverseRow } from "@/lib/api";
import { cn, formatNum } from "@/lib/utils";

type Tone = "default" | "ok" | "warn" | "err" | "accent";

type KpiData = {
  label: string;
  value: string;
  hint: string;
  icon: LucideIcon;
  tone: Tone;
};

export function StatCards({ data }: { data?: UniverseRow[] }) {
  const stats = computeStats(data);
  return (
    <div className="grid grid-cols-4 gap-4">
      <KpiCard
        label="Sector market cap"
        value={stats.totalMarketCap}
        hint={`${stats.nRows} active banks`}
        icon={Coins}
        tone="default"
      />
      <KpiCard
        label="Median composite"
        value={stats.medianScorecard}
        hint="Scorecard 0–100, universe median"
        icon={Gauge}
        tone={stats.medianScorecardNum !== null && stats.medianScorecardNum >= 60 ? "ok" : "default"}
      />
      <KpiCard
        label="Top-decile quality"
        value={stats.topDecileCount.toString()}
        hint={stats.topDecileScrips || "—"}
        icon={Trophy}
        tone="accent"
      />
      <KpiCard
        label="Contrarian bets"
        value={stats.contrarianCount.toString()}
        hint={stats.contrarianScrips || "No scrips in the quadrant"}
        icon={Crosshair}
        tone={stats.contrarianCount > 0 ? "warn" : "default"}
      />
    </div>
  );
}

const TONE_STYLES: Record<Tone, { card: string; icon: string; iconBg: string }> = {
  default: { card: "",                             icon: "text-fg-muted", iconBg: "bg-bg-subtle" },
  ok:      { card: "border-l-[3px] border-l-ok",   icon: "text-ok",       iconBg: "bg-ok/8" },
  warn:    { card: "border-l-[3px] border-l-warn", icon: "text-warn",     iconBg: "bg-warn/8" },
  err:     { card: "border-l-[3px] border-l-err",  icon: "text-err",      iconBg: "bg-err/8" },
  accent:  { card: "border-l-[3px] border-l-fg",   icon: "text-fg",       iconBg: "bg-bg-hover" },
};

function KpiCard({ label, value, hint, icon: Icon, tone }: KpiData) {
  const s = TONE_STYLES[tone];
  return (
    <div className={cn("panel px-5 py-4 flex items-start gap-4", s.card)}>
      <div className={cn("mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl", s.iconBg)}>
        <Icon className={cn("h-4.5 w-4.5", s.icon)} strokeWidth={1.75} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="label truncate">{label}</p>
        <p className="mt-1 text-[22px] font-semibold leading-none tracking-tight num text-fg">
          {value}
        </p>
        <p className="mt-2 text-[11.5px] text-fg-muted leading-tight truncate" title={hint}>
          {hint}
        </p>
      </div>
    </div>
  );
}

// ── Stats ────────────────────────────────────────────────────────────────

function formatNpr(v: number | null): string {
  if (v === null || !isFinite(v)) return "—";
  if (v >= 1e12) return `NPR ${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9)  return `NPR ${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6)  return `NPR ${(v / 1e6).toFixed(0)}M`;
  return `NPR ${Math.round(v).toLocaleString("en-US")}`;
}

function median(xs: number[]): number | null {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

function computeStats(rows?: UniverseRow[]) {
  if (!rows || rows.length === 0) {
    return {
      nRows: 0,
      totalMarketCap: "—",
      medianScorecard: "—",
      medianScorecardNum: null as number | null,
      topDecileCount: 0,
      topDecileScrips: "",
      contrarianCount: 0,
      contrarianScrips: "",
    };
  }

  const capSum = rows.reduce((a, r) => a + (r.market_cap_npr ?? 0), 0);
  const scorecards = rows.map((r) => r.scorecard_0_100).filter((v): v is number => v !== null);
  const med = median(scorecards);

  const topDecile = rows.filter((r) => r.quality_tier === "TOP_DECILE");
  const contrarian = rows.filter((r) => r.quadrant === "CONTRARIAN_BET");

  return {
    nRows: rows.length,
    totalMarketCap: formatNpr(capSum || null),
    medianScorecard: med === null ? "—" : formatNum(med, 1),
    medianScorecardNum: med,
    topDecileCount: topDecile.length,
    topDecileScrips: topDecile.map((r) => r.scrip).slice(0, 4).join(" · "),
    contrarianCount: contrarian.length,
    contrarianScrips: contrarian.map((r) => r.scrip).slice(0, 4).join(" · "),
  };
}
