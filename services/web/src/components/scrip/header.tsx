"use client";

import { Sparkles, Eye } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api, ScripSummary } from "@/lib/api";
import { formatPct } from "@/lib/utils";
import { ScoreGauge, FlagPill, Spark, RangeBar, npr, deriveFlag } from "@/components/viz";

export function ScripHeader({ scrip, summary }: { scrip: string; summary?: ScripSummary }) {
  // 90-day price sparkline — separate query so the header paints before
  // price data lands.
  const prices = useQuery({
    queryKey: ["prices", scrip, 90],
    queryFn: () => api.prices(scrip, 90),
    staleTime: 5 * 60_000,
  });

  const closes = (prices.data ?? []).map((p) => p.close);
  const pricePositive = (summary?.change_pct ?? 0) >= 0;

  const hi = summary?.week52_high ?? null;
  const lo = summary?.week52_low ?? null;
  const cur = summary?.latest_close ?? null;

  const score = summary?.quality_score_0_100 ?? null;
  const flag = deriveFlag(score, summary?.change_pct);
  const sectorColor = flag === "red" ? "var(--neg)" : flag === "green" ? "var(--pos)" : "var(--accent)";
  const initials = scrip.slice(0, 2);

  function askCopilot() {
    window.dispatchEvent(new CustomEvent("nrc:open-copilot"));
  }

  return (
    <div
      className="px-6 py-5"
      style={{ borderBottom: "1px solid var(--line)", background: "var(--panel)" }}
    >
      <div className="flex flex-wrap items-start gap-5">
        {/* Monogram */}
        <div
          style={{
            width: 64,
            height: 64,
            borderRadius: 16,
            flexShrink: 0,
            background: `color-mix(in oklab, ${sectorColor} 16%, var(--panel-3))`,
            border: `1px solid color-mix(in oklab, ${sectorColor} 35%, transparent)`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: sectorColor,
            fontFamily: "var(--font-display)",
            fontWeight: 700,
            fontSize: 23,
          }}
        >
          {initials}
        </div>

        {/* Identity */}
        <div className="flex min-w-[220px] flex-1 flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="serif" style={{ margin: 0, fontSize: 28, fontWeight: 600, letterSpacing: "-.01em", lineHeight: 1.05, color: "var(--ink)" }}>
              {summary?.company_name ?? scrip}
            </h1>
            <FlagPill flag={flag} />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span
              className="mono"
              style={{ fontSize: 12, fontWeight: 600, padding: "3px 9px", borderRadius: 7, background: "var(--panel-3)", border: "1px solid var(--line)", color: "var(--ink)" }}
            >
              {scrip}
            </span>
            <span style={{ fontSize: 12.5, color: "var(--ink-2)" }}>{summary?.sector ?? "—"}</span>
            {summary?.latest_date && (
              <>
                <span style={{ color: "var(--ink-4)" }}>·</span>
                <span style={{ fontSize: 12.5, color: "var(--ink-3)" }}>as of {summary.latest_date}</span>
              </>
            )}
          </div>
          {/* sparkline + 52w */}
          <div className="mt-1 flex flex-wrap items-end gap-6">
            {closes.length > 1 && <Spark data={closes} w={220} h={42} color="var(--accent)" />}
            {hi !== null && lo !== null && cur !== null && (
              <div style={{ width: 220 }}>
                <RangeBar low={lo} high={hi} cur={cur} label="52-week range" />
              </div>
            )}
          </div>
        </div>

        {/* Price */}
        <div className="flex flex-col gap-1">
          <div className="flex items-baseline gap-2.5">
            <span className="display tnum" style={{ fontSize: 32, fontWeight: 700, color: "var(--ink)" }}>
              {cur !== null ? npr(cur, 2) : "—"}
            </span>
            {summary?.change_pct !== null && summary?.change_pct !== undefined && (
              <span className="mono" style={{ fontSize: 14, color: pricePositive ? "var(--pos)" : "var(--neg)" }}>
                {pricePositive ? "▲" : "▼"} {formatPct(Math.abs(summary.change_pct))}
              </span>
            )}
          </div>
          <div className="eyebrow" style={{ marginTop: 2 }}>Last traded · NPR</div>
          <div className="mt-3 flex gap-2">
            <button
              onClick={askCopilot}
              className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12.5px] font-semibold"
              style={{ background: "var(--accent)", color: "var(--bg)" }}
            >
              <Sparkles className="h-3.5 w-3.5" strokeWidth={2.2} />
              Ask Copilot
            </button>
            <button
              className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12.5px] font-semibold"
              style={{ background: "var(--panel-2)", color: "var(--ink-2)", border: "1px solid var(--line)" }}
            >
              <Eye className="h-3.5 w-3.5" strokeWidth={2} />
              Watch
            </button>
          </div>
        </div>

        {/* Conviction gauge */}
        <div className="flex flex-col items-center" style={{ minWidth: 120 }}>
          <ScoreGauge score={Math.round(score ?? 50)} flag={flag} size={112} thick={8} label="Conviction" />
        </div>
      </div>
    </div>
  );
}
