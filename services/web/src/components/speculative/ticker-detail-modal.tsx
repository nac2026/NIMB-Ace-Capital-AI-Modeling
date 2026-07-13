"use client";

// Per-ticker detail modal. Opens when the user clicks a TickerResultCard.
// Centered, ~960px wide, max-h ~88vh, scrolls inside. Backdrop blur.
// Close: Escape key, backdrop click, or the X button in the header.
//
// Sections (top → bottom):
//   1. Header — ticker · company · cohort + flag pills · close
//   2. Why this verdict — descriptive LLM rationale (or templated fallback)
//   3. Vital statistics grid (15 cells)
//   4. Cohort placement reasoning (short)
//   5. Composite scorecard + Rule outcomes (side by side)
//   6. Footer — "Open in Research →"

import Link from "next/link";
import { useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ExternalLink, X, Sparkles } from "lucide-react";
import type { SpeculativeResult, ScorecardRow } from "@/lib/api";
import { FlagBadge } from "./flag-badge";
import { CohortBadge } from "./cohort-badge";
import { MetricCell } from "./metric-cell";
import { RuleOutcomesList } from "./rule-outcomes-list";
import { CompositeScorecardCard } from "@/components/scrip/scorecard-card";

// ─── Helpers (mirror ticker-result-card to keep formatting consistent) ─
function num(v: unknown, digits = 2): string | null {
  if (typeof v !== "number" || !Number.isFinite(v)) return null;
  return v.toFixed(digits);
}
function pct(v: unknown, digits = 1, isFraction = true): string | null {
  if (typeof v !== "number" || !Number.isFinite(v)) return null;
  const x = isFraction ? v * 100 : v;
  return `${x.toFixed(digits)}%`;
}
function signedPct(v: unknown, digits = 1, isFraction = false): string | null {
  if (typeof v !== "number" || !Number.isFinite(v)) return null;
  const x = isFraction ? v * 100 : v;
  return `${x >= 0 ? "+" : ""}${x.toFixed(digits)}%`;
}
function formatBillions(npr: number): string {
  if (npr >= 1e9) return `${(npr / 1e9).toFixed(2)}B`;
  if (npr >= 1e7) return `${(npr / 1e7).toFixed(2)}Cr`;
  return npr.toLocaleString("en-US");
}

function snapshotToScorecardRow(r: SpeculativeResult): ScorecardRow | null {
  const s = r.snapshot ?? {};
  if (s.scorecard_0_100 === undefined && s.quality_pct === undefined) return null;
  return {
    scrip:               r.scrip,
    sector:              r.sector,
    scorecard_0_100:     (s.scorecard_0_100 as number) ?? null,
    quality_pct:         (s.quality_pct as number) ?? null,
    valuation_pct:       (s.valuation_pct as number) ?? null,
    momentum_pct:        (s.momentum_pct as number) ?? null,
    risk_pct:            (s.risk_pct as number) ?? null,
    income_pct:          (s.income_pct as number) ?? null,
    quality_score_0_100: (s.quality_score_0_100 as number) ?? null,
  };
}

// ─── Component ──────────────────────────────────────────────────────
export function TickerDetailModal({
  result,
  onClose,
}: {
  result: SpeculativeResult;
  onClose: () => void;
}) {
  // Close on Escape
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    // Lock body scroll while modal is open
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  const s = result.snapshot ?? {};
  const scorecardRow = snapshotToScorecardRow(result);

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-8"
      style={{ background: "rgba(0,0,0,0.55)", backdropFilter: "blur(2px)" }}
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        className="flex max-h-[88vh] w-full max-w-[960px] flex-col overflow-hidden rounded-2xl bg-bg-panel shadow-2xl"
        style={{ border: "1px solid var(--border-subtle)", boxShadow: "var(--shadow-lg)" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* ── Header ─────────────────────────────────────────── */}
        <div
          className="flex items-start justify-between gap-4 border-b px-6 py-4"
          style={{ borderColor: "var(--border-subtle)" }}
        >
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="mono num text-[22px] font-bold tracking-tight" style={{ color: "var(--brand)" }}>
                {result.scrip}
              </h2>
              {result.company_name && (
                <span className="truncate text-[14px] text-fg-muted">{result.company_name}</span>
              )}
            </div>
            <div className="mt-1.5 flex items-center gap-2">
              <CohortBadge cohort={result.cohort} size="sm" />
              <FlagBadge   flag={result.flag}   size="sm" />
              {result.sector && (
                <span className="text-[11px] text-fg-dim">{result.sector}</span>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close detail"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-fg-muted transition-colors hover:bg-bg-hover hover:text-fg"
          >
            <X className="h-4 w-4" strokeWidth={2} />
          </button>
        </div>

        {/* ── Body (scrollable) ──────────────────────────────── */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {/* Descriptive verdict */}
          <section className="mb-6">
            <div className="mb-2 flex items-center gap-1.5">
              <Sparkles className="h-3.5 w-3.5" style={{ color: "var(--brand)" }} strokeWidth={1.75} />
              <h3 className="text-[12px] font-semibold uppercase tracking-widest" style={{ color: "var(--brand)" }}>
                Why this verdict
              </h3>
            </div>
            <div
              className="markdown rounded-lg p-4"
              style={{ background: "var(--brand-soft)", border: "1px solid var(--border-subtle)" }}
            >
              {result.detail_rationale ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{result.detail_rationale}</ReactMarkdown>
              ) : (
                <p className="text-[13px] text-fg-muted italic">No detailed verdict available.</p>
              )}
            </div>
          </section>

          {/* Vital statistics */}
          <section className="mb-6">
            <h3 className="mb-2 text-[12px] font-semibold uppercase tracking-widest text-fg-dim">
              Vital statistics
            </h3>
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-5">
              <MetricCell label="EPS (D)"           value={num(s.eps)} />
              <MetricCell label="Distributable EPS" value={null} tooltip="Not in current dataset — phase 2 vendor feed" />
              <MetricCell label="PE"                value={num(s.pe_ratio)} />
              <MetricCell label="PB"                value={num(s.pb_ratio)} />
              <MetricCell label="ROE"               value={pct(s.roe)} />
              <MetricCell label="CAR"               value={pct(s.car)} />
              <MetricCell label="NPL"               value={pct(s.npl_ratio)} />
              <MetricCell label="Dividend Yield"    value={pct(s.total_dividend_yield, 1, false)} />
              <MetricCell label="Credit Rating"     value={null} tooltip="Credit Rating not in current dataset — phase 2 vendor feed" />
              <MetricCell label="Profit YoY"        value={signedPct(s.net_profit_yoy_pct, 1, false)} />
              <MetricCell label="6m Return"         value={signedPct(s.return_6m, 1, true)} />
              <MetricCell label="Last Price"        value={num(s.last_price, 2)} />
              <MetricCell label="Market Cap"        value={s.market_cap ? formatBillions(s.market_cap as number) : null} />
              <MetricCell label="BVPS"              value={num(s.bvps, 2)} />
              <MetricCell label="Quadrant"          value={(s.quadrant as string) ?? null} />
            </div>
          </section>

          {/* Cohort placement */}
          {result.cohort_reason && (
            <section className="mb-6">
              <h3 className="mb-2 text-[12px] font-semibold uppercase tracking-widest text-fg-dim">
                Cohort placement
              </h3>
              <div
                className="rounded-md p-3 text-[13px] leading-relaxed text-fg"
                style={{ background: "var(--bg-subtle)" }}
              >
                {result.cohort_reason}
              </div>
            </section>
          )}

          {/* Scorecard + rule outcomes */}
          <section className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_260px]">
            <div>
              <h3 className="mb-2 text-[12px] font-semibold uppercase tracking-widest text-fg-dim">
                Composite scorecard
              </h3>
              {scorecardRow ? (
                <CompositeScorecardCard row={scorecardRow} />
              ) : (
                <div className="text-[12.5px] text-fg-muted italic">No scorecard data available.</div>
              )}
            </div>
            <div>
              <h3 className="mb-2 text-[12px] font-semibold uppercase tracking-widest text-fg-dim">
                Rule outcomes
              </h3>
              <RuleOutcomesList outcomes={result.rule_outcomes || []} />
            </div>
          </section>
        </div>

        {/* ── Footer ─────────────────────────────────────────── */}
        <div
          className="flex items-center justify-between gap-3 border-t bg-bg-subtle px-6 py-3"
          style={{ borderColor: "var(--border-subtle)" }}
        >
          <div className="text-[11px] text-fg-dim">
            Press <kbd className="rounded border px-1.5 py-0.5 font-mono text-[10px]" style={{ borderColor: "var(--border)" }}>Esc</kbd> to close
          </div>
          {result.flag !== "unknown" && (
            <Link
              href={`/scrip/${result.scrip}`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12.5px] font-semibold transition-opacity hover:opacity-90"
              style={{ background: "var(--brand)", color: "#ffffff" }}
            >
              Open in Research
              <ExternalLink className="h-3.5 w-3.5" strokeWidth={2} />
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
