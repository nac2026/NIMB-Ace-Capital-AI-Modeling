"use client";

// "System" tab content for /help — how to USE the portal. Everything here
// describes UI surfaces, not the numbers themselves (those live in the
// Metrics tab).

import type { ReactNode } from "react";
import {
  QualityTierChip, QuadrantChip, SelfValuationChip, MarketCapChip, ScoreBadge,
} from "@/components/dashboard/chips";
import { Kbd, Code, Card, Labeled } from "./primitives";

export type SystemItem = {
  term: ReactNode;
  description?: ReactNode;
  howToUse?: ReactNode;
  example?: ReactNode;
};

export type SystemSection = {
  id: string;
  title: string;
  intro: ReactNode;
  items?: SystemItem[];
  custom?: ReactNode;
};

export const SYSTEM_SECTIONS: SystemSection[] = [
  {
    id: "getting-started",
    title: "Getting started",
    intro: (
      <>
        A research cockpit for NIMB analysts covering NEPSE Commercial Banks. Every number
        traces back to the Gold analytics layer in the lakehouse; the UI exposes data and
        attribution, never a BUY / SELL call. Use the left sidebar to navigate, the right
        chat drawer for ad-hoc questions, and <Kbd>⌘K</Kbd> to jump anywhere.
      </>
    ),
    items: [
      {
        term: "Data freshness",
        description: "Every panel has an 'as of' timestamp in the page header.",
        howToUse: "If it looks stale, the daily ingest probably hasn't completed yet. Check the green HealthDot in the sidebar footer, or curl /ready on the backend.",
      },
      {
        term: "No verdicts",
        description: "The UI deliberately hides BUY / SELL / STRONG_BUY labels.",
        howToUse: "If you want the machine's recommendation, ask the chat ('what's the investment_scorecard.recommendation for NABIL?'). The underlying field is still computed — we just don't render it.",
      },
      {
        term: "Every number is sourced",
        description: "Hover any metric card and you'll see which Postgres table it came from.",
        howToUse: "Use the source to reconcile against dbt models in the repo or the raw Parquet on MinIO.",
      },
    ],
  },

  {
    id: "sidebar",
    title: "Left sidebar",
    intro: <>Main way to navigate. <Kbd>⌘B</Kbd> toggles between expanded (240px) and icon-only (56px). It auto-collapses when you focus the chat input so the conversation gets maximum width. Hover any icon for a tooltip label.</>,
    items: [
      { term: "Dashboard",    description: "Universe overview: all 19 active banks, sortable and filterable." },
      { term: "Compare",      description: "Pick 2–5 scrips from a typeahead, see side-by-side with best-in-row heatmap." },
      { term: "Live Market",  description: "Deferred — placeholder until floor-sheet vendor access is live." },
      { term: "Chat history", description: "Browse past chat sessions. Shares the same session store as the drawer." },
      { term: "Screens",      description: "Five pre-built strategy filters. See the Screens section for what each one selects." },
      { term: "Help & docs",  description: "This page. Always opens in a new tab so you can keep reading while working on another tab." },
      { term: "Health dot",   description: "Green = backend reachable, red = down. Sits in the footer next to the theme toggle." },
      { term: "Theme toggle", description: "Cycles Light → Dark → System. Persists across reloads." },
    ],
  },

  {
    id: "dashboard",
    title: "Dashboard",
    intro: <>The morning scan. Four stat tiles at the top summarize the sector; below, a sortable / filterable table of every active bank.</>,
    custom: (
      <>
        <div className="mt-4">
          <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-fg-dim">Stat tiles</h3>
          <div className="flex flex-col gap-2.5">
            <Card title="Sector market cap">Sum of market cap across all active banks. A rough proxy for sector size.</Card>
            <Card title="Median composite">50th-percentile Scorecard 0-100 across the universe. Tells you where the 'middle' bank sits today.</Card>
            <Card title="Top-decile quality">Count of banks classified TOP_DECILE on fundamental quality. Subhint shows the first four tickers.</Card>
            <Card title="Contrarian bets">Count of banks in the CONTRARIAN_BET quadrant (strong quality but weak 6-month momentum).</Card>
          </div>
        </div>

        <div className="mt-5">
          <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-fg-dim">Table columns</h3>
          <div className="flex flex-col gap-2.5">
            <Card title="Bank">Scrip ticker + full name. Click the row to open the detail page.</Card>
            <Card title="Price">Latest close. Date shown in the page header.</Card>
            <Card title="1D">Percent change vs previous session's close.</Card>
            <Card title="6M">Six-month total return. Sparkline next to it is the last 30 daily closes.</Card>
            <Card title="Scorecard" chip={<ScoreBadge v={86} />}>Composite 0-100 rollup. Click the column header to sort.</Card>
            <Card title="Quality" chip={<QualityTierChip tier="TOP_DECILE" />}>Fundamental-quality bucket.</Card>
            <Card title="Quadrant" chip={<QuadrantChip quadrant="QUALITY_LEADER" />}>2×2 position: Quality × 6M momentum vs sector medians.</Card>
            <Card title="Vs own P/E" chip={<SelfValuationChip tier="CHEAP" />}>Where today's P/E sits inside the scrip's own 5-year distribution.</Card>
            <Card title="Div yield">Total dividend yield. 8%+ bolded (above FD rate).</Card>
            <Card title="Size" chip={<MarketCapChip tier="LARGE" />}>Market-cap bucket.</Card>
            <Card title="NPL">Non-performing loans as % of gross loans. &gt;5% flagged warn.</Card>
            <Card title="CAR">Capital adequacy ratio. &lt;11% (NRB minimum) flagged err.</Card>
            <Card title="P/E">Trailing price / earnings.</Card>
          </div>
        </div>

        <div className="mt-5">
          <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-fg-dim">Filter chip bar</h3>
          <div className="flex flex-col gap-2.5">
            <Card title="How filters combine">AND across filter groups, OR within a group. Pick one quadrant AND one size, or multiple quadrants (any-match).</Card>
            <Card title="Quality">Multi-select by Quality tier chip.</Card>
            <Card title="Quadrant">Multi-select by quadrant position.</Card>
            <Card title="Size">Multi-select by market-cap tier.</Card>
            <Card title="NPL band">Three buckets: &lt; 2% / 2-5% / &gt; 5%.</Card>
          </div>
        </div>
      </>
    ),
  },

  {
    id: "scrip-detail",
    title: "Scrip detail",
    intro: <>Navigate here by clicking any dashboard row or typing the ticker in <Kbd>⌘K</Kbd>. URL is <Code>/scrip/[SYMBOL]</Code>; tabs are hash-linked so you can share a direct link to a specific view — e.g. <Code>/scrip/NABIL#valuation</Code>.</>,
    items: [
      { term: "Header strip", description: "Ticker, company, sector, current price, 1D%, 52-week range bar, sparkline, market cap, size chip, quadrant chip, quality score." },
      { term: "Performance tab", description: "1-year price chart + price-return grid (1M/3M/6M/1Y/3Y/5Y), TSR, beta / Sharpe / vol panel." },
      { term: "Fundamentals tab", description: "TTM snapshot + 6 small-multiple QoQ line charts (ROE, ROA, NIM, NPL, CAR, CD)." },
      { term: "Valuation tab", description: "P/E and P/B history with 5-year shaded band + self-valuation tier chip." },
      { term: "Asset quality tab", description: "NPL trajectory + LLP coverage + QoQ/YoY deltas in pp + TTM credit-loss rate." },
      { term: "Capital tab", description: "CAR vs NRB 11% reference line + Tier 1 / Tier 2 stacked area." },
      { term: "Income tab", description: "Annual dividend bar chart (cash vs bonus) with 8% FD reference + yield_tier chip." },
      { term: "Technicals tab", description: "Five rule checklist (trend / MA align / RSI / MACD / Bollinger). Framed as 'N of 5 bullish' — no BUY/SELL chip." },
      { term: "Quality tab", description: "CompositeScorecardCard + 9-signal Piotroski grid + Quality × Momentum scatter with this scrip highlighted." },
    ],
  },

  {
    id: "compare",
    title: "Compare",
    intro: <>Click Compare in the sidebar or type <Code>compare NABIL NICA HBL</Code> in <Kbd>⌘K</Kbd>. Limited to 2–5 scrips — beyond that the grid becomes unreadable.</>,
    items: [
      { term: "Typeahead picker", description: "Add scrips by searching ticker or company name. Remove with the X on each chip." },
      { term: "Price overlay", description: "All selected scrips normalized to 100 at the earliest shared date. Makes % moves directly comparable regardless of absolute price." },
      { term: "Metric grid", description: "Transposed: scrips as columns, metrics as rows, grouped by category." },
      { term: "Best-in-row heat", description: "For numeric rows, the best value (higher or lower depending on metric) is highlighted green. Chip rows (tiers) aren't heat-mapped since they're categorical." },
    ],
  },

  {
    id: "screens",
    title: "Screen presets",
    intro: <>Pre-filtered views of the universe table. Reach them from the Screens section in the sidebar or via <Kbd>⌘K</Kbd>. Custom filter builder is deferred; for now these are curated strategies.</>,
    items: [
      { term: "Top quality", description: "Composite analytics score ≥ 70. Use when you want the quantitative cream." },
      { term: "Cheap vs own", description: "P/E self-percentile tier is VERY_CHEAP or CHEAP. Trading below their own historical norm — not necessarily cheap vs peers." },
      { term: "High yield", description: "Total dividend yield ≥ 8% (above Nepali FD rate). Income-focused screen." },
      { term: "Contrarian bets", description: "Quadrant = CONTRARIAN_BET (strong fundamentals, weak 6M momentum). Candidates for patient capital." },
      { term: "Turnaround", description: "Weak or below-average quality tier + positive 6M return. Fundamentals are bad but the tape is recovering." },
    ],
  },

  {
    id: "chat",
    title: "Chat & research drawer",
    intro: <>Two surfaces for the same chat backend. The drawer is on the right of every dashboard page; the full <Code>/chat</Code> page is the history browser. Both share <Code>localStorage.nrc.session_id</Code> — start a conversation in the drawer, hit 'Open in full page' to see its charts at full size.</>,
    items: [
      { term: "Context-aware", description: "On /scrip/NABIL the drawer tells the agent 'user is viewing NABIL'. Questions that omit a ticker default to NABIL." },
      { term: "Session continuity", description: "Navigate pages — the thread follows you. Drawer and /chat page are the same conversation." },
      { term: "Visual panel", description: "On /chat, assistant answers with charts or tables render in a separate panel on the right so you can read prose and data side-by-side." },
      { term: "New conversation", description: "Plus icon in the drawer/history header. The old session stays in history." },
      { term: "Auto-collapse", description: "Focusing the chat input collapses both sidebars + the visual panel for max reading space. Expand manually when you want them back." },
    ],
  },

  {
    id: "command-palette",
    title: "Command palette (⌘K)",
    intro: <>Global overlay. The fastest way to jump around.</>,
    items: [
      { term: "Scrip search", description: "Type any ticker or company name — results navigate to /scrip/[SYMBOL]." },
      { term: "Navigate", description: "Match on sidebar destinations (Dashboard, Compare, any Screen, Chat)." },
      { term: "Ask chat", description: "Hit Enter on any free-form query — opens /chat with that query already submitted." },
      { term: "Run", description: <><Code>compare NABIL NICA HBL</Code> parses the tickers and opens the Compare view with them pre-selected.</> },
    ],
  },

  {
    id: "shortcuts",
    title: "Keyboard shortcuts",
    intro: <>Everything in one place.</>,
    items: [
      { term: <><Kbd>⌘K</Kbd> / <Kbd>Ctrl K</Kbd></>, description: "Open the command palette." },
      { term: <><Kbd>⌘B</Kbd> / <Kbd>Ctrl B</Kbd></>, description: "Toggle the app sidebar between expanded and icon-only." },
      { term: <><Kbd>⌘/</Kbd> / <Kbd>Ctrl /</Kbd></>, description: "Focus the chat drawer input (opens drawer if collapsed)." },
      { term: <Kbd>Esc</Kbd>, description: "Close command palette; collapse chat drawer (if input isn't focused)." },
      { term: <><Kbd>↑</Kbd> / <Kbd>↓</Kbd></>, description: "Move selection within the command palette." },
      { term: <Kbd>Enter</Kbd>, description: "Submit the selected command-palette item, or send a chat message." },
      { term: <><Kbd>Shift</Kbd>+<Kbd>Enter</Kbd></>, description: "New line in chat input without sending." },
    ],
  },

  {
    id: "troubleshooting",
    title: "Troubleshooting",
    intro: <>Quick answers to the usual questions.</>,
    items: [
      { term: "A page shows 'No data'", description: "The dbt Gold build for that scrip hasn't completed since its last base-table change. Check Dagster UI → assets → the relevant Gold model." },
      { term: "Prices look old", description: "The daily EOD job runs on schedule. 'as of' date in the page header tells you what snapshot you're seeing." },
      { term: "Chat says 'Error'", description: "FastAPI orchestrator or Claude key is down. Check /ready on the backend; orange state means the serving DB or lakehouse read failed." },
      { term: "I can't find a scrip", description: "If it's not Commercial Bank, it isn't in this cut. Phase 1 scope is the 19 active commercial banks; other sectors arrive in later phases." },
    ],
  },
];

export function SystemCard({ item }: { item: SystemItem }) {
  return (
    <div
      className="rounded-lg px-4 py-3"
      style={{ background: "var(--bg-panel)", border: "1px solid var(--border-subtle)" }}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[13.5px] font-semibold text-fg">{item.term}</span>
        {item.example && <span className="shrink-0">{item.example}</span>}
      </div>
      {item.description && (
        <div className="mt-1 text-[12.5px] leading-relaxed text-fg-muted">{item.description}</div>
      )}
      {item.howToUse && <Labeled label="How to use">{item.howToUse}</Labeled>}
    </div>
  );
}
