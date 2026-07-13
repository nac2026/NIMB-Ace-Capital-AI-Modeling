"use client";

import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { IndexRow } from "@/lib/api";
import { cn, formatNum, formatPct, formatBig } from "@/lib/utils";

export function IndexHeader({ data, isLoading }: { data?: IndexRow[]; isLoading?: boolean }) {
  return (
    <div className="grid grid-cols-2 gap-4">
      {(isLoading || !data)
        ? [0, 1].map((i) => <IndexSkeleton key={i} />)
        : data.map((idx) => <IndexCard key={idx.index_name} idx={idx} />)}
    </div>
  );
}

function IndexCard({ idx }: { idx: IndexRow }) {
  const pct = idx.percent_change ?? 0;
  const up = pct > 0;
  const flat = pct === 0;
  const changeColor = flat ? "text-fg-muted" : up ? "text-ok" : "text-err";
  const TrendIcon = flat ? Minus : up ? TrendingUp : TrendingDown;
  const accentBg = flat ? "bg-bg-subtle" : up ? "bg-ok/8" : "bg-err/8";
  const accentColor = flat ? "text-fg-muted" : up ? "text-ok" : "text-err";

  return (
    <div className="panel flex items-center justify-between px-6 py-5">
      {/* Left: index name + price */}
      <div>
        <p className="label mb-1">{idx.index_name}</p>
        <p className="num text-[28px] font-semibold leading-none tracking-tight text-fg">
          {formatNum(idx.close, 2)}
        </p>
        <p className="mt-1.5 text-[11px] text-fg-dim">As of {idx.date}</p>
      </div>

      {/* Center: change badge */}
      <div className={cn("flex items-center gap-2 rounded-xl px-4 py-2.5", accentBg)}>
        <TrendIcon className={cn("h-4 w-4", accentColor)} strokeWidth={2} />
        <div>
          <p className={cn("num text-[15px] font-semibold leading-tight", changeColor)}>
            {formatPct(idx.percent_change)}
          </p>
          <p className={cn("num text-[12px] leading-tight", changeColor)}>
            {(pct >= 0 ? "+" : "") + formatNum(idx.change, 2)} pts
          </p>
        </div>
      </div>

      {/* Right: turnover */}
      <div className="text-right">
        <p className="label mb-1">Turnover</p>
        <p className="num text-[15px] font-semibold text-fg">{formatBig(idx.turnover)}</p>
      </div>
    </div>
  );
}

function IndexSkeleton() {
  return (
    <div className="panel flex items-center justify-between px-6 py-5 animate-pulse">
      <div className="space-y-2">
        <div className="h-3 w-16 rounded bg-bg-hover" />
        <div className="h-7 w-28 rounded bg-bg-hover" />
        <div className="h-2.5 w-20 rounded bg-bg-hover" />
      </div>
      <div className="h-12 w-28 rounded-xl bg-bg-hover" />
      <div className="space-y-2 text-right">
        <div className="ml-auto h-3 w-14 rounded bg-bg-hover" />
        <div className="ml-auto h-5 w-20 rounded bg-bg-hover" />
      </div>
    </div>
  );
}
