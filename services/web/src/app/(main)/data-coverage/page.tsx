"use client";

// Data coverage page — single source of truth for "what's actually in
// this prototype." Reached by clicking the prototype banner at the top
// of every dashboard page.

import {
  Database, Calendar, TrendingUp, Wallet, Layers, BarChart3,
  Activity, AlertCircle, CheckCircle2, Clock,
} from "lucide-react";
import {
  PROTOTYPE_VERSION,
  PROTOTYPE_SECTOR,
  PROTOTYPE_SCRIP_COUNT,
  PROTOTYPE_DATA_THROUGH,
} from "@/components/prototype-banner";
import { RefreshPipelineButton } from "@/components/refresh-pipeline-button";

const BANKS = [
  ["ADBL", "Agricultural Development Bank Limited"],
  ["CZBIL", "Citizens Bank International Limited"],
  ["EBL", "Everest Bank Limited"],
  ["GBIME", "Global IME Bank Limited"],
  ["HBL", "Himalayan Bank Limited"],
  ["KBL", "Kumari Bank Limited"],
  ["LSL", "Laxmi Sunrise Bank Limited"],
  ["MBL", "Machhapuchchhre Bank Limited"],
  ["NABIL", "Nabil Bank Limited"],
  ["NBL", "Nepal Bank Limited"],
  ["NICASIA", "NIC Asia Bank Limited"],
  ["NIMB", "Nepal Investment Mega Bank Limited"],
  ["NMB", "NMB Bank Limited"],
  ["PCBL", "Prime Commercial Bank Limited"],
  ["PRVU", "Prabhu Bank Limited"],
  ["SANIMA", "Sanima Bank Limited"],
  ["SBI", "Nepal SBI Bank Limited"],
  ["SBL", "Siddhartha Bank Limited"],
  ["SCB", "Standard Chartered Bank Nepal Limited"],
] as const;

const DOMAINS = [
  {
    title: "Daily price bars",
    icon: TrendingUp,
    coverage: "2025-04-20 → 2026-04-20",
    rows: "4,237",
    description: "OHLCV (open / high / low / close / volume) + turnover, per scrip per trading day.",
    uses: "Performance tab · sparklines · return calculations · 52-week ranges",
  },
  {
    title: "Technical indicators",
    icon: Activity,
    coverage: "2007-12-27 → 2026-04-20",
    rows: "55,686",
    description: "SMA (20/50/200), RSI, MACD, Bollinger bands computed daily.",
    uses: "Technicals tab · technical posture panel · 5-rule signal scoring",
  },
  {
    title: "Quarterly fundamentals",
    icon: Wallet,
    coverage: "FY 2067 Q1 → FY 2082 Q2",
    rows: "1,151",
    description: "15+ years of quarterly balance sheet and income statement metrics from regulatory filings.",
    uses: "Fundamentals · Asset Quality · Capital · Quality tabs",
  },
  {
    title: "Corporate actions",
    icon: Layers,
    coverage: "FY 2067 → FY 2081",
    rows: "398",
    description: "Cash dividends, bonus shares, rights issues, stock splits — board-decision records.",
    uses: "Income tab · dividend history · TSR computation",
  },
  {
    title: "Index data",
    icon: BarChart3,
    coverage: "2024-04-21 → 2026-04-20",
    rows: "902",
    description: "NEPSE main index + Commercial Banking sub-index, OHLCV daily.",
    uses: "Dashboard header · sector momentum · beta calculation",
  },
  {
    title: "Live market ticks",
    icon: Clock,
    coverage: "Real-time (simulated)",
    rows: "Streaming",
    description: "Sub-second tick stream replayed from historical daily bars. Demo-only — replaces real exchange feed.",
    uses: "Live Market page · real-time price displays",
  },
];

const ANALYTICS = [
  "TTM fundamentals",
  "Quarterly growth (QoQ + YoY)",
  "DuPont decomposition",
  "Cost efficiency ratios",
  "Revenue quality",
  "Asset quality trends",
  "Capital strength tiers",
  "Dividend yield",
  "Piotroski F-score (9 signals)",
  "Price returns (1m/3m/6m/1y/3y/5y)",
  "Fundamental quality composite",
  "Quality-momentum matrix (quadrant)",
  "Valuation history (P/E, P/B percentile)",
  "Operating leverage",
  "Market cap metrics",
  "Beta & volatility",
  "Total shareholder return",
  "Technical signal summary",
  "Sector momentum",
  "Investment scorecard (0-100)",
  "Peer rankings (quarterly)",
  "Stage-1 screen results",
  "Stage-2 bank screen",
  "Indicators daily",
  "Live quotes",
];

const DEFERRED = [
  {
    title: "Other sectors",
    detail: "Hydropower, Manufacturing, Development Banks, Microfinance, Insurance, Trading — ~390 listed scrips not yet ingested.",
  },
  {
    title: "Real exchange tick feed",
    detail: "v1 uses a tick simulator. Production live data requires SMTM or SWP API integration (Phase 2 of roadmap).",
  },
  {
    title: "Floor-sheet & broker flows",
    detail: "Buyer/seller broker IDs per trade — needed for broker-wise net flow and accumulation/distribution signals. Depends on SMTM API.",
  },
  {
    title: "News & disclosures",
    detail: "NEPSE announcements, company press releases, SEBON circulars. Phase 5 — to be ingested into pgvector for RAG.",
  },
  {
    title: "Promoter & insider data",
    detail: "Public float, locked-in share schedules, promoter pledging, insider transactions. Vendor TBD.",
  },
  {
    title: "Streaming intraday data",
    detail: "Currently EOD only. Intraday bars + circuit events deferred to Phase 5.",
  },
];

export default function DataCoveragePage() {
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[1100px] px-8 py-10">
        {/* ── Hero ─────────────────────────────────────────────── */}
        <div className="mb-10 flex items-start gap-4">
          <div
            className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl"
            style={{ background: "var(--brand)" }}
          >
            <Database className="h-6 w-6 text-white" strokeWidth={1.75} />
          </div>
          <div>
            <h1 className="text-[28px] font-semibold tracking-tight text-fg">
              Prototype data coverage
            </h1>
            <p className="mt-1.5 text-[14px] text-fg-muted">
              Exactly what's loaded into this build, where it comes from, and what's deliberately out of scope for v1.
            </p>
          </div>
        </div>

        {/* ── Top-level summary cards ───────────────────────────── */}
        <div className="mb-4 grid grid-cols-4 gap-3">
          <SummaryCard label="Version" value={PROTOTYPE_VERSION} accent />
          <SummaryCard label="Sector" value={PROTOTYPE_SECTOR} />
          <SummaryCard label="Active scrips" value={`${PROTOTYPE_SCRIP_COUNT}`} />
          <SummaryCard label="Data through" value={PROTOTYPE_DATA_THROUGH} mono />
        </div>

        {/* ── On-demand refresh ─────────────────────────────────── */}
        <div className="mb-8">
          <RefreshPipelineButton />
        </div>

        {/* ── Banks list ───────────────────────────────────────── */}
        <Section title="Coverage — the 19 active commercial banks" subtitle="All currently trading on NEPSE. Excluded: 10 inactive / delisted scrips in the same sector.">
          <div className="panel overflow-hidden">
            <table className="tbl">
              <thead>
                <tr>
                  <th style={{ width: 96 }}>Ticker</th>
                  <th>Company name</th>
                </tr>
              </thead>
              <tbody>
                {BANKS.map(([ticker, name]) => (
                  <tr key={ticker}>
                    <td className="mono num" style={{ color: "var(--brand)", fontWeight: 600 }}>{ticker}</td>
                    <td>{name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>

        {/* ── Data domains ─────────────────────────────────────── */}
        <Section title="Data domains" subtitle="Six raw data layers feed the analytics. Coverage windows reflect what currently lives in Postgres.">
          <div className="grid grid-cols-2 gap-3">
            {DOMAINS.map((d) => (
              <DomainCard key={d.title} {...d} />
            ))}
          </div>
        </Section>

        {/* ── Gold analytics ───────────────────────────────────── */}
        <Section title="25 computed analytics tables" subtitle="Derived from the raw domains above via dbt. Refreshed nightly by the Dagster daily_eod_job.">
          <div className="panel p-5">
            <div className="grid grid-cols-3 gap-x-6 gap-y-2 text-[13px] text-fg-muted">
              {ANALYTICS.map((a) => (
                <div key={a} className="flex items-center gap-2">
                  <CheckCircle2 className="h-3.5 w-3.5 shrink-0" style={{ color: "var(--ok)" }} strokeWidth={2} />
                  <span>{a}</span>
                </div>
              ))}
            </div>
          </div>
        </Section>

        {/* ── Deferred ─────────────────────────────────────────── */}
        <Section title="Out of scope for v1.0.0" subtitle="Items deferred to later phases. Listed here so demos and scope conversations stay aligned.">
          <div className="space-y-2">
            {DEFERRED.map((d) => (
              <DeferredCard key={d.title} {...d} />
            ))}
          </div>
        </Section>

        {/* ── Footer note ──────────────────────────────────────── */}
        <div
          className="mt-10 rounded-xl p-4 text-[12.5px] text-fg-muted"
          style={{ background: "var(--brand-soft)", border: "1px solid var(--border-subtle)" }}
        >
          <div className="flex items-start gap-2.5">
            <Calendar className="mt-0.5 h-4 w-4 shrink-0" style={{ color: "var(--brand)" }} strokeWidth={1.75} />
            <div>
              As scope expands (new sectors ingested, data refreshed to a later date, new analytics added),
              update the constants in <code className="rounded bg-bg-panel px-1.5 py-0.5 font-mono text-[11.5px]">prototype-banner.tsx</code> and
              the lists in <code className="rounded bg-bg-panel px-1.5 py-0.5 font-mono text-[11.5px]">data-coverage/page.tsx</code> — the top banner reflects the change automatically.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function SummaryCard({ label, value, accent, mono }: { label: string; value: string; accent?: boolean; mono?: boolean }) {
  return (
    <div
      className="panel px-4 py-3.5"
      style={accent ? { borderColor: "var(--brand)", borderWidth: 1.5 } : undefined}
    >
      <div className="label">{label}</div>
      <div
        className={`mt-1 text-[18px] font-semibold tracking-tight ${mono ? "mono num" : ""}`}
        style={accent ? { color: "var(--brand)" } : { color: "var(--fg)" }}
      >
        {value}
      </div>
    </div>
  );
}

function Section({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <section className="mb-9">
      <h2 className="text-[16px] font-semibold tracking-tight text-fg">{title}</h2>
      {subtitle && <p className="mt-1 mb-4 text-[12.5px] text-fg-muted">{subtitle}</p>}
      <div className={subtitle ? "" : "mt-4"}>{children}</div>
    </section>
  );
}

function DomainCard({
  title, icon: Icon, coverage, rows, description, uses,
}: {
  title: string;
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  coverage: string;
  rows: string;
  description: string;
  uses: string;
}) {
  return (
    <div className="panel p-4">
      <div className="flex items-start gap-3">
        <div
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg"
          style={{ background: "var(--brand-soft)", color: "var(--brand)" }}
        >
          <Icon className="h-4.5 w-4.5" strokeWidth={1.75} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-2">
            <div className="text-[14px] font-semibold text-fg">{title}</div>
            <div className="mono num text-[11.5px] text-fg-dim">{rows}</div>
          </div>
          <div className="mt-0.5 mono num text-[11.5px]" style={{ color: "var(--brand)" }}>
            {coverage}
          </div>
          <p className="mt-2 text-[12.5px] leading-relaxed text-fg-muted">{description}</p>
          <div className="mt-2.5 text-[11px] uppercase tracking-widest text-fg-dim">Used by</div>
          <div className="text-[12px] text-fg-muted">{uses}</div>
        </div>
      </div>
    </div>
  );
}

function DeferredCard({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="panel flex items-start gap-3 p-3.5">
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" style={{ color: "var(--warn)" }} strokeWidth={1.75} />
      <div className="min-w-0">
        <div className="text-[13px] font-semibold text-fg">{title}</div>
        <p className="mt-0.5 text-[12.5px] leading-relaxed text-fg-muted">{detail}</p>
      </div>
    </div>
  );
}
