"use client";

// SMTM fundamentals — deep statement history (all sectors, up to ~19 years),
// live from the SMTM Data API via /api/scrip/{scrip}/financials. Complements the
// CSV-sourced FinancialsExplorer (bank-centric, shallow) with cross-sector depth:
// headline per-share/return metrics + long-run trend charts. Monetary key-stats
// arrive in NPR '000, so money values are scaled ×1000 for display.

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ResponsiveContainer, ComposedChart, Line, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
} from "recharts";
import { api, type SmtmKeyStatsPeriod } from "@/lib/api";
import { Panel, MetricCell, EmptyState, LoadingState, ErrorState, npr, pct } from "./primitives";

type Period = "annual" | "quarterly";

function rs(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || !isFinite(v)) return "—";
  return `Rs ${v.toFixed(digits)}`;
}
function money000(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : npr(v * 1000);
}
function xmult(v: number | null | undefined): string {
  return v === null || v === undefined || v <= 0 ? "—" : `${v.toFixed(1)}×`;
}

const ACCENT = "var(--accent)";
const INK = "var(--fg)";
const INK_DIM = "var(--fg-dim)";
const CHART_GRID = "var(--border-subtle)";
const AXIS = { fontSize: 10, fill: "var(--fg-muted)" } as const;
const TOOLTIP = {
  background: "var(--bg-panel)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12,
} as const;

export function SmtmFundamentals({ scrip }: { scrip: string }) {
  const [period, setPeriod] = useState<Period>("annual");
  const q = useQuery({
    queryKey: ["smtm-financials", scrip],
    queryFn: () => api.scrip.financials(scrip),
    staleTime: 60 * 60_000,
  });

  if (q.isLoading) return <LoadingState rows={6} />;
  if (q.isError) return <ErrorState message="Could not load SMTM fundamentals." onRetry={() => q.refetch()} />;
  const d = q.data;
  if (!d || !d.has_data) {
    return <EmptyState message="No SMTM fundamentals available for this scrip." />;
  }

  const L = d.latest;
  const series = (period === "annual" ? d.annual : d.quarterly).map((p) => ({
    label: p.label ?? "",
    eps: p.eps,
    roe: p.roe != null ? p.roe * 100 : null,
    roa: p.roa != null ? p.roa * 100 : null,
    net_income: p.net_income != null ? p.net_income / 1000 : null, // '000 → M NPR
    revenue: p.total_revenue != null ? p.total_revenue / 1000 : null,
    bvps: p.book_value_per_share,
    npl: p.npl != null ? p.npl * 100 : null,
  }));

  const hasBankRatios = d.annual.some((p) => p.npl != null || p.capital_adequacy != null);
  const sourceTag = L?.data_source ? `${L.data_source} · ${L.label}` : d.data_source.toUpperCase();

  return (
    <div className="flex flex-col gap-4">
      {/* headline latest metrics */}
      <Panel
        title="Fundamentals · SMTM"
        hint={`Live from SMTM — ${d.counts.annual} annual periods · ${d.counts.quarterly} quarters`}
        right={<SourceBadge label={sourceTag} />}
      >
        <div className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
          <MetricCell label="EPS" value={rs(L?.eps)} hint="Annualized EPS (latest reported)" />
          <MetricCell label="P/E" value={xmult(L?.pe)} />
          <MetricCell label="Book value / sh" value={rs(L?.book_value_per_share)} />
          <MetricCell label="Div / sh" value={rs(L?.dividend_per_share)} />
          <MetricCell label="ROE" value={pct(L?.roe)} tone={roeTone(L?.roe)} />
          <MetricCell label="ROA" value={pct(L?.roa)} />
          <MetricCell label="Net income" value={money000(L?.net_income)} hint="Latest period" />
          <MetricCell label="Net margin" value={pct(L?.net_income_margin)} />
          {hasBankRatios && <MetricCell label="NPL" value={pct(L?.npl)} tone={nplTone(L?.npl)} />}
          {hasBankRatios && <MetricCell label="Capital adequacy" value={pct(L?.capital_adequacy)} />}
          <MetricCell label="Market price" value={rs(L?.mps)} />
          <MetricCell label="Market cap" value={money000(L?.market_cap)} />
        </div>
      </Panel>

      <div className="flex items-center gap-1">
        <PeriodToggle period={period} onChange={setPeriod} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title="EPS & ROE" hint="Per-share earnings vs return on equity">
          <div className="h-[240px]">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={series}>
                <CartesianGrid stroke={CHART_GRID} vertical={false} />
                <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={false} minTickGap={24} />
                <YAxis yAxisId="l" tick={AXIS} tickLine={false} axisLine={false} width={40} />
                <YAxis yAxisId="r" orientation="right" tick={AXIS} tickLine={false} axisLine={false} width={40}
                  tickFormatter={(v) => `${v}%`} />
                <Tooltip contentStyle={TOOLTIP} labelStyle={{ color: "var(--fg-muted)" }} />
                <Bar yAxisId="l" dataKey="eps" name="EPS (Rs)" fill={ACCENT} fillOpacity={0.6} radius={[2, 2, 0, 0]} />
                <Line yAxisId="r" type="monotone" dataKey="roe" name="ROE %" stroke={INK} strokeWidth={1.75} dot={false} connectNulls />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel title="Revenue & net income" hint="NPR millions">
          <div className="h-[240px]">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={series}>
                <CartesianGrid stroke={CHART_GRID} vertical={false} />
                <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={false} minTickGap={24} />
                <YAxis tick={AXIS} tickLine={false} axisLine={false} width={48}
                  tickFormatter={(v) => (Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(0)}B` : `${v}M`)} />
                <Tooltip contentStyle={TOOLTIP} labelStyle={{ color: "var(--fg-muted)" }}
                  formatter={(v) => (typeof v === "number" ? `NPR ${Math.round(v).toLocaleString("en-US")}M` : "—")} />
                <Bar dataKey="revenue" name="Revenue" fill={INK_DIM} fillOpacity={0.5} radius={[2, 2, 0, 0]} />
                <Line type="monotone" dataKey="net_income" name="Net income" stroke={ACCENT} strokeWidth={1.75} dot={false} connectNulls />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>

      <StatementsNote counts={d.counts} />
    </div>
  );
}

function roeTone(v: number | null | undefined): "ok" | "warn" | "default" {
  if (v == null) return "default";
  return v >= 0.15 ? "ok" : v < 0.08 ? "warn" : "default";
}
function nplTone(v: number | null | undefined): "ok" | "warn" | "err" | "default" {
  if (v == null) return "default";
  return v >= 0.05 ? "err" : v >= 0.03 ? "warn" : "ok";
}

function SourceBadge({ label }: { label: string }) {
  return (
    <span
      className="shrink-0 rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider"
      style={{
        color: "var(--accent)",
        border: "1px solid color-mix(in oklab, var(--accent) 40%, transparent)",
        background: "color-mix(in oklab, var(--accent) 12%, transparent)",
      }}
    >
      {label}
    </span>
  );
}

function PeriodToggle({ period, onChange }: { period: Period; onChange: (p: Period) => void }) {
  const opts: { v: Period; label: string }[] = [
    { v: "annual", label: "Annual" },
    { v: "quarterly", label: "Quarterly" },
  ];
  return (
    <div className="inline-flex rounded-lg p-0.5" style={{ background: "var(--bg-panel-2, var(--bg-panel))", border: "1px solid var(--border-subtle)" }}>
      {opts.map((o) => (
        <button
          key={o.v}
          onClick={() => onChange(o.v)}
          className="rounded-md px-3 py-1 text-[11.5px] font-semibold transition-colors"
          style={period === o.v
            ? { background: "var(--accent)", color: "#0b0d10" }
            : { color: "var(--fg-muted)" }}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function StatementsNote({ counts }: { counts: { income: number; balance: number; cashflow: number } }) {
  return (
    <p className="text-[11px] text-fg-muted">
      Full statements available from SMTM — income ({counts.income}), balance sheet ({counts.balance}),
      cash flow ({counts.cashflow}) annual periods.
    </p>
  );
}
