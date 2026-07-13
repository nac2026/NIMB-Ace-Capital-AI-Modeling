"use client";

import { memo, useRef } from "react";
import type { CSSProperties } from "react";
import type { LiveTick } from "@/hooks/use-market-stream";
import { Sparkline } from "./sparkline";

const SPARK_BUFFER = 60;

// Shared column widths — must match the header in live/page.tsx
export const COL_CLS = {
  scrip:    "min-w-[120px] flex-1 px-4",
  price:    "w-[110px] shrink-0 px-4 text-right",
  chgPct:   "w-[90px]  shrink-0 px-4 text-right",
  chgAbs:   "w-[90px]  shrink-0 px-4 text-right",
  volume:   "w-[80px]  shrink-0 px-4 text-right",
  turnover: "w-[110px] shrink-0 px-4 text-right",
  trend:    "w-[90px]  shrink-0 px-4",
};

function fmtPrice(v: number) {
  return v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function fmtPct(v: number | null) {
  if (v === null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}
function fmtVol(v: number) {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000)     return `${(v / 1_000).toFixed(1)}K`;
  return String(v);
}
function fmtTurnover(v: number) {
  if (v >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(2)}B`;
  if (v >= 1_000_000)     return `${(v / 1_000_000).toFixed(2)}M`;
  if (v >= 1_000)         return `${(v / 1_000).toFixed(1)}K`;
  return v.toFixed(2);
}

type ScripRowProps = {
  tick: LiveTick;
  style?: CSSProperties;   // injected by react-window for absolute positioning
};

export const ScripRow = memo(function ScripRow({ tick, style }: ScripRowProps) {
  const bufRef = useRef<number[]>([]);
  bufRef.current.push(tick.price);
  if (bufRef.current.length > SPARK_BUFFER) {
    bufRef.current = bufRef.current.slice(-SPARK_BUFFER);
  }

  const pct = tick.change_pct ?? 0;
  const isUp = pct >= 0;
  const changeColor = isUp ? "var(--ok)" : "var(--err)";

  return (
    <div
      style={{ ...style, borderBottom: "1px solid var(--border-subtle)" }}
      className="flex items-center text-[13px] transition-colors hover:bg-[var(--bg-hover)]"
    >
      {/* Scrip */}
      <div className={`${COL_CLS.scrip} font-semibold text-fg truncate`}>
        {tick.scrip}
      </div>

      {/* Price */}
      <div className={`${COL_CLS.price} font-semibold tabular-nums`} style={{ color: changeColor }}>
        {fmtPrice(tick.price)}
      </div>

      {/* Change % */}
      <div className={`${COL_CLS.chgPct} tabular-nums`} style={{ color: changeColor }}>
        {fmtPct(tick.change_pct)}
      </div>

      {/* Change abs */}
      <div className={`${COL_CLS.chgAbs} tabular-nums text-fg-muted`}>
        {tick.change_abs !== null
          ? `${tick.change_abs >= 0 ? "+" : ""}${tick.change_abs.toFixed(2)}`
          : "—"}
      </div>

      {/* Volume */}
      <div className={`${COL_CLS.volume} tabular-nums text-fg-muted`}>
        {fmtVol(tick.volume)}
      </div>

      {/* Turnover */}
      <div className={`${COL_CLS.turnover} tabular-nums text-fg-muted`}>
        {fmtTurnover(tick.turnover)}
      </div>

      {/* Sparkline */}
      <div className={COL_CLS.trend}>
        <Sparkline points={[...bufRef.current]} positive={isUp} />
      </div>
    </div>
  );
});
