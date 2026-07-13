"use client";

// Sector-level context panel rendered above the ticker cards in each
// sector group. Numbers are aggregated from the per-ticker snapshots —
// no extra API call required.
//
// Hidden when the sector has < 2 tickers (insufficient signal).

import { Building2 } from "lucide-react";
import type { SpeculativeResult } from "@/lib/api";

function meanOf(values: (number | null | undefined)[]): number | null {
  const v = values.filter((x): x is number => typeof x === "number" && Number.isFinite(x));
  if (v.length === 0) return null;
  return v.reduce((a, b) => a + b, 0) / v.length;
}

export function SectorOutlookPanel({
  sector,
  results,
}: {
  sector: string;
  results: SpeculativeResult[];
}) {
  if (results.length < 2) return null;

  const peVals       = results.map(r => (r.snapshot?.pe_ratio as number | undefined) ?? null);
  const nplVals      = results.map(r => (r.snapshot?.npl_ratio as number | undefined) ?? null);
  const yoyVals      = results.map(r => (r.snapshot?.net_profit_yoy_pct as number | undefined) ?? null);
  const dyVals       = results.map(r => (r.snapshot?.total_dividend_yield as number | undefined) ?? null);
  const ret6mVals    = results.map(r => (r.snapshot?.return_6m as number | undefined) ?? null);

  const pe   = meanOf(peVals);
  const npl  = meanOf(nplVals);
  const yoy  = meanOf(yoyVals);
  const dy   = meanOf(dyVals);
  const r6m  = meanOf(ret6mVals);

  const nValue = results.filter(r => r.cohort === "value_universe").length;
  const nFund  = results.filter(r => r.cohort === "fundamental_universe").length;
  const nOut   = results.filter(r => r.cohort === "out_of_universe").length;

  return (
    <div
      className="mb-3 rounded-xl p-4"
      style={{ background: "var(--brand-soft)", border: "1px solid var(--border-subtle)" }}
    >
      <div className="flex items-center gap-2">
        <div
          className="flex h-6 w-6 items-center justify-center rounded-md"
          style={{ background: "var(--brand)", color: "#ffffff" }}
        >
          <Building2 className="h-3.5 w-3.5" strokeWidth={2} />
        </div>
        <h3 className="text-[14px] font-semibold tracking-tight text-fg">
          {sector} <span className="text-fg-muted">· {results.length} ticker{results.length === 1 ? "" : "s"}</span>
        </h3>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 text-[12px] sm:grid-cols-4 lg:grid-cols-6">
        <Tile label="Mean PE" value={pe !== null ? pe.toFixed(1) : "—"} />
        <Tile label="Mean NPL" value={npl !== null ? `${(npl * 100).toFixed(1)}%` : "—"} />
        <Tile label="Profit YoY" value={yoy !== null ? `${yoy >= 0 ? "+" : ""}${yoy.toFixed(1)}%` : "—"} />
        <Tile label="Div yield" value={dy !== null ? `${dy.toFixed(1)}%` : "—"} />
        <Tile label="6m return" value={r6m !== null ? `${r6m >= 0 ? "+" : ""}${(r6m * 100).toFixed(1)}%` : "—"} />
        <Tile
          label="Cohort split"
          value={`${nValue}V · ${nFund}F · ${nOut}O`}
        />
      </div>
    </div>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md px-2.5 py-1.5" style={{ background: "var(--bg-panel)" }}>
      <div className="text-[10px] uppercase tracking-widest text-fg-dim">{label}</div>
      <div className="num text-[13px] font-semibold text-fg">{value}</div>
    </div>
  );
}
