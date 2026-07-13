// Thin typed wrappers around the FastAPI backend. All data fetching in the
// app flows through here so the endpoint list is visible at a glance.

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8080";

// ----------------------------------------------------------- response types
export type UniverseRow = {
  scrip: string;
  company_name: string;
  sector: string;
  latest_close: number | null;
  latest_date: string | null;
  change_pct: number | null;
  roe: number | null;
  npl_ratio: number | null;
  car: number | null;
  cd_ratio: number | null;
  pe_ratio: number | null;
  composite_score: number | null;  // stage-2 legacy 0-1
  flags: string[];
  // Phase I+J enrichments (added for dashboard redesign)
  scorecard_0_100: number | null;
  quality_score_0_100: number | null;
  quality_tier: string | null;
  quadrant: string | null;
  return_6m: number | null;
  self_valuation_tier: string | null;
  total_dividend_yield: number | null;
  yield_tier: string | null;
  market_cap_npr: number | null;
  market_cap_tier: string | null;
};

export type IndexRow = {
  index_name: string;
  date: string;
  close: number;
  change: number | null;
  percent_change: number | null;
  turnover: number | null;
};

export type Stage2Row = {
  scrip: string;
  sector: string | null;
  composite_score: number;
  roe: number | null;
  roa: number | null;
  net_margin: number | null;
  npl_ratio: number | null;
  car: number | null;
  cd_ratio: number | null;
  flags: string[];
};

export type PricePoint = { date: string; close: number };

export type ToolCallSummary = {
  tool: string;
  input: Record<string, unknown>;
  latency_ms: number;
  error: string | null;
};

export type ChatResponse = {
  trace_id: string;
  answer: string;
  tool_calls: ToolCallSummary[];
  total_latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  model_used: string;
  intent_category: string;
  intent_reason: string;
};

// Page-context shape the chat drawer sends with each chat request.
// Backend (agent._system_prompt) reads and prepends a context line.
export type PageContext = {
  current_scrip?: string;
  current_scrips?: string[];
  current_screen?: string;
};

// ---------------------------------------------------------------- Phase I+J
// One scrip's rollup — used by universe overview and scrip detail header.
export type ScripSummary = {
  scrip: string;
  company_name: string;
  sector: string;
  latest_close: number | null;
  latest_date: string | null;
  change_pct: number | null;
  market_cap_npr: number | null;
  market_cap_tier: string | null;
  quadrant: string | null;
  quality_score_0_100: number | null;
  quality_tier: string | null;
  week52_high: number | null;
  week52_low: number | null;
};

export type ScripProfile = {
  scrip: string;
  company_name: string;
  sector: string;
  sub_sector: string | null;
  listed_shares: number | null;
  paid_up_value: number | null;
  paid_up_capital: number | null;
  registered_date: string | null;
  shares_outstanding: number | null;
  market_cap_npr: number | null;
  market_cap_tier: string | null;
  eps: number | null;
  bvps: number | null;
  pe_ratio: number | null;
  pb_ratio: number | null;
  roe: number | null;
  fiscal_year_bs: number | null;
  quarter: number | null;
  dividend_yield: number | null;
  bonus_pct: number | null;
  promoter_pct: number | null;
  public_pct: number | null;
  ownership_available: boolean;
  data_as_of: string | null;
};

export type ScorecardRow = {
  scrip: string;
  sector: string | null;
  quality_pct: number | null;
  valuation_pct: number | null;
  momentum_pct: number | null;
  risk_pct: number | null;
  income_pct: number | null;
  quality_score_0_100: number | null;
  scorecard_0_100: number | null;
};

export type QuadrantRow = {
  scrip: string;
  sector: string | null;
  quality_score_0_100: number | null;
  quality_tier: string | null;
  return_6m: number | null;
  quadrant: string | null;
  sector_quality_median: number | null;
  sector_return_6m_median: number | null;
};

export type FundamentalsHistoryRow = {
  fiscal_year_bs: number;
  quarter: number;
  net_profit: number | null;
  operating_profit: number | null;
  net_interest_income: number | null;
  roe: number | null;
  roa: number | null;
  npl_ratio: number | null;
  car: number | null;
  cd_ratio: number | null;
  eps: number | null;
  bvps: number | null;
  pe_ratio: number | null;
  pb_ratio: number | null;
  total_deposits: number | null;
  total_loans: number | null;
  ttm_net_profit: number | null;
  ttm_roe: number | null;
  ttm_roa: number | null;
  ttm_nim: number | null;
  net_profit_yoy_pct: number | null;
  net_profit_qoq_pct: number | null;
  total_operating_income_yoy_pct: number | null;
  total_loans_yoy_pct: number | null;
  total_deposits_yoy_pct: number | null;
};

export type ValuationHistoryRow = {
  fiscal_year_bs: number;
  quarter: number;
  pe_ratio: number | null;
  pb_ratio: number | null;
  pe_self_pct_5y: number | null;
  pb_self_pct_5y: number | null;
  pe_self_pct_all: number | null;
  self_valuation_tier: string | null;
};

export type ReturnsSnapshot = {
  scrip: string;
  as_of: string | null;
  close: number | null;
  return_1m: number | null;
  return_3m: number | null;
  return_6m: number | null;
  return_1y: number | null;
  return_3y: number | null;
  return_5y: number | null;
  drawdown_from_peak: number | null;
  realized_vol_20d: number | null;
  position_in_20d_range: number | null;
  tsr_1y: number | null;
  tsr_3y: number | null;
  tsr_5y: number | null;
  beta: number | null;
  alpha_annual: number | null;
  r_squared: number | null;
  annualized_vol: number | null;
  sharpe_ratio_2y: number | null;
};

export type PiotroskiRow = {
  fiscal_year_bs: number;
  quarter: number;
  p1_positive_profit: number | null;
  p2_positive_roa: number | null;
  p3_profit_grew: number | null;
  p4_roa_improved: number | null;
  p5_npl_not_worse: number | null;
  p6_car_not_worse: number | null;
  p7_no_large_issuance: number | null;
  p8_nim_improved: number | null;
  p9_cti_improved: number | null;
  f_score: number | null;
  n_signals_available: number | null;
};

export type DupontRow = {
  fiscal_year_bs: number;
  quarter: number;
  roe_computed: number | null;
  roa: number | null;
  equity_multiplier: number | null;
  net_profit_margin: number | null;
  asset_turnover: number | null;
  tax_burden: number | null;
  interest_burden: number | null;
  operating_margin: number | null;
  nim: number | null;
};

export type AssetQualityRow = {
  fiscal_year_bs: number;
  quarter: number;
  npl_ratio: number | null;
  llp_to_npl_ratio: number | null;
  npl_qoq_change_abs: number | null;
  npl_yoy_change_abs: number | null;
  llp_coverage_yoy_change: number | null;
  credit_loss_rate_ttm: number | null;
  asset_quality_tier: string | null;
};

export type CapitalRow = {
  fiscal_year_bs: number;
  quarter: number;
  car: number | null;
  tier1_capital: number | null;
  tier2_capital: number | null;
  total_capital: number | null;
  tier1_share: number | null;
  car_buffer: number | null;
  car_yoy_change: number | null;
  capital_tier: string | null;
};

export type DividendRow = {
  fiscal_year_bs: number;
  annual_cash_div_pct: number | null;
  annual_bonus_pct: number | null;
  market_value_per_share: number | null;
  cash_dividend_yield: number | null;
  total_dividend_yield: number | null;
  yield_tier: string | null;
};

export type CorporateActionRow = {
  action_type: string;
  ratio: number | null;
  amount: number | null;
  announcement_date: string | null;
  fiscal_year_bs: number | null;
};

export type DividendsResponse = {
  annual: DividendRow[];
  actions: CorporateActionRow[];
};

export type TechnicalsSnapshot = {
  scrip: string;
  as_of: string | null;
  close: number | null;
  sma_20: number | null;
  sma_50: number | null;
  sma_200: number | null;
  ema_12: number | null;
  ema_26: number | null;
  rsi_14: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_histogram: number | null;
  bollinger_upper: number | null;
  bollinger_middle: number | null;
  bollinger_lower: number | null;
  atr_14: number | null;
  r1_trend: number | null;
  r2_ma_align: number | null;
  r3_rsi: number | null;
  r4_macd: number | null;
  r5_bollinger: number | null;
  signal_sum: number | null;
  technical_signal: string | null;
};

export type QualityRow = {
  fiscal_year_bs: number;
  quarter: number;
  profitability_pct: number | null;
  asset_quality_pct: number | null;
  growth_pct: number | null;
  capital_pct: number | null;
  efficiency_pct: number | null;
  piotroski_pct: number | null;
  quality_score_0_100: number | null;
  quality_tier: string | null;
};

export type SectorMomentumRow = {
  sector: string;
  n_scrips: number | null;
  avg_return_3m: number | null;
  avg_return_6m: number | null;
  avg_return_1y: number | null;
  median_return_6m: number | null;
  return_6m_dispersion: number | null;
  rank_by_6m: number | null;
  momentum_tier: string | null;
};

export type ScreenResponse = {
  preset: string;
  description: string;
  rows: UniverseRow[];
};

// ─── Pipeline trigger ────────────────────────────────────────────
export type PipelineState = {
  status: "idle" | "running" | "succeeded" | "failed" | "queued" | "canceled";
  run_id: string | null;
  started_at: string | null;
  ended_at: string | null;
  exit_code: number | null;
  message: string | null;
  dagster_url?: string | null;
  jobs?: string[];
};

export type TradebookFiles = {
  dir: string;
  count: number;
  files: { name: string; size: number; modified_at: string }[];
};

// ─── Speculative Analysis types ──────────────────────────────────
export type Flag = "green" | "amber" | "red" | "unknown";
export type Cohort = "value_universe" | "fundamental_universe" | "out_of_universe" | "unknown";

export type SpeculativeUploadResponse = {
  session_id: string;
  title: string;
  mode: "screen" | "review";
  n_tickers: number;
  tickers: string[];
  unknown_tickers: string[];
  status: string;
};

export type SpeculativeAnalyzeResponse = {
  session_id: string;
  status: string;
  n_results: number;
};

export type SpeculativeSessionListItem = {
  session_id: string;
  title: string;
  notes: string | null;
  n_tickers: number;
  n_green: number;
  n_amber: number;
  n_red: number;
  n_unknown: number;
  // Cohort counters
  n_value: number;
  n_fundamental: number;
  n_out: number;
  status: string;
  created_at: string;
  completed_at: string | null;
};

export type RuleOutcome = {
  rule: string;
  status: "green" | "amber" | "red";
  value: number | string;
  threshold: string;
};

export type SpeculativeResult = {
  scrip: string;
  company_name: string | null;
  sector: string | null;
  flag: Flag;
  flag_score: number | null;
  cohort: Cohort;
  cohort_reason: string | null;
  headline: string | null;
  detail_rationale: string | null;
  rule_outcomes: RuleOutcome[];
  snapshot: Record<string, unknown>;
  error: string | null;
};

export type SpeculativeChatTurn = {
  turn_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

export type ReviewClaim = {
  scrip: string | null;
  claim_text: string;
  claim_type: string | null;
  verdict: "supported" | "contradicted" | "unverifiable" | null;
  actual_value: string | null;
  evidence: Record<string, unknown>;
};
export type ReviewAspect = {
  scrip: string | null;
  aspect: string;
  rating: "positive" | "neutral" | "negative" | null;
  score: number | null;
  assessment: string | null;
};
export type ReviewDebateTurn = { role: "bull" | "bear" | "judge"; content: string };

export type SpeculativeSessionDetail = {
  session: SpeculativeSessionListItem;
  mode: "screen" | "review";
  tickers: string[];
  results: SpeculativeResult[];
  narrative_md: string | null;
  narrative_model: string | null;
  chat: SpeculativeChatTurn[];
  // Review-mode fields
  verdict: "GREEN" | "AMBER" | "RED" | null;
  verdict_confidence: number | null;
  claims: ReviewClaim[];
  aspects: ReviewAspect[];
  debate: ReviewDebateTurn[];
};

// -------------------------------------------------------------- fetchers
async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${BACKEND}${path}`);
  if (!res.ok) throw new Error(`${path} → ${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}

async function postJSON<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BACKEND}${path}`, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${path} → ${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}

async function postForm<T>(path: string, fields: Record<string, string | File | undefined>): Promise<T> {
  const fd = new FormData();
  for (const [k, v] of Object.entries(fields)) {
    if (v === undefined || v === null) continue;
    fd.append(k, v);
  }
  const res = await fetch(`${BACKEND}${path}`, { method: "POST", body: fd });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${path} → ${res.status} ${res.statusText}${text ? ` · ${text}` : ""}`);
  }
  return (await res.json()) as T;
}

async function del(path: string): Promise<unknown> {
  const res = await fetch(`${BACKEND}${path}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`${path} → ${res.status} ${res.statusText}`);
  return await res.json();
}

// --- Floor-sheet / broker-flow (Phase 2 microstructure) ---
export interface SpeculationRow {
  speculation_score: number | null;
  speculation_tier: string | null;
  c_concentration: number | null;
  c_control: number | null;
  c_circular: number | null;
  c_accumulation: number | null;
  c_block: number | null;
  has_self_trade: number | null;
}
export interface BrokerConcentrationDay {
  trade_date: string;
  n_brokers: number | null;
  hhi_buy: number | null;
  hhi_sell: number | null;
  top1_buy_share: number | null;
  top3_buy_share: number | null;
  top1_sell_share: number | null;
  top3_sell_share: number | null;
  concentration_flag: boolean | null;
}
export interface BrokerPositionRow {
  broker: number;
  cum_net_qty: number | null;
  volume_share: number | null;
  days_net_buy: number | null;
  days_active: number | null;
  accumulation_flag: boolean | null;
  distribution_flag: boolean | null;
  phase: string | null;            // accumulating | distributing | flat
  accum_start_date: string | null;
  peak_date: string | null;
  dist_start_date: string | null;
  days_since_peak: number | null;
}

export interface BrokerTimeline {
  broker: number;
  points: { date: string; cum_net_qty: number | null }[];
}
export interface FloorsheetResponse {
  scrip: string;
  speculation: SpeculationRow | null;
  concentration_recent: BrokerConcentrationDay[];
  top_accumulators: BrokerPositionRow[];
  top_distributors: BrokerPositionRow[];
  position_timeline: BrokerTimeline[];
  data_as_of: string | null;
}

// --- News & sentiment ---
export interface NewsItem {
  title: string;
  url: string;
  source: string | null;
  published_at: string | null;
  sentiment: string | null;
  sentiment_score: number | null;
  summary: string | null;
  event_type: string | null;
}
export interface NewsSentimentResponse {
  scrip: string;
  sentiment_label: string | null;
  sentiment_score: number | null;
  n_articles: number;
  bullish_count: number;
  neutral_count: number;
  bearish_count: number;
  latest_published_at: string | null;
  articles: NewsItem[];
}

export type PulseScore = {
  scrip: string;
  company_name: string | null;
  sector: string | null;
  value: number | null;
  tier: string | null;
  extra: string | null;
};
export type MarketPulse = {
  sentiment_bullish: number;
  sentiment_neutral: number;
  sentiment_bearish: number;
  sentiment_avg: number | null;
  speculation_alerts: PulseScore[];
  broker_accumulation: PulseScore[];
  bullish_movers: PulseScore[];
  bearish_movers: PulseScore[];
};

export type MarketNewsItem = {
  title: string;
  url: string;
  source: string | null;
  published_at: string | null;
  sentiment: string | null;
  sentiment_score: number | null;
  summary: string | null;
  event_type: string | null;
  scrip_tags: string[];
  sector_tags: string[];
};

export type AlertRow = {
  signal_key: string;
  scrip: string;
  company_name: string | null;
  sector: string | null;
  alert_type: string;   // spec | accum | conc
  level: string | null; // HIGH | FLAG
  score: number | null;
  title: string | null;
  detail: string | null;
  mode: string;
  status: string;
  first_seen_at: string | null;
  sent_at: string | null;
  cleared_at: string | null;
};

export type SurveillanceTrade = {
  contract_number: number;
  trade_date: string;
  scrip: string;
  client_code: string;
  client_name: string | null;
  side: string;                 // 'B' | 'S'
  our_qty: number | null;
  our_value: number | null;
  our_price: number | null;
  day_vwap: number | null;
  our_broker: number | null;
  our_broker_name: string | null;
  counterparty_broker: number | null;
  counterparty_broker_name: string | null;
  slippage_vs_vwap_pct: number | null;
  slippage_npr: number | null;
  worse_than_range_flag: boolean | null;
  interval_vwap: number | null;
  markout_5d_pct: number | null;
  cp_surprise_z: number | null;
  exit_liquidity_flag: boolean | null;
  cross_flag: boolean | null;
  churn_flag: boolean | null;
  bought_near_peak_flag: boolean | null;
  scrip_speculation_tier: string | null;
  scrip_concentration_flag: boolean | null;
  scrip_pump_flag: boolean | null;
  surveillance_score: number | null;
  surveillance_tier: string | null;
  flag_reasons: string[] | null;
};

export type CounterpartyExposure = {
  client_code: string;
  client_name: string | null;
  counterparty_broker: number;
  counterparty_broker_name: string | null;
  scrip: string;
  n_trades: number;
  total_qty: number | null;
  total_amount: number | null;
  n_days: number | null;
  first_date: string | null;
  last_date: string | null;
  share_of_fund_qty: number | null;
  cp_market_share: number | null;
  surprise_z: number | null;
  cp_is_accumulator: boolean | null;
  cp_is_distributor: boolean | null;
  cp_in_wash_pair: boolean | null;
  cp_flagged: boolean | null;
};

export type SurveillanceSummary = {
  total: number;
  flagged: number;
  clean_rate: number | null;
  flagged_notional: number;
  n_funds: number;
  first_date: string | null;
  last_date: string | null;
  computed_at: string | null;
  book_first_date: string | null;
  book_last_date: string | null;
  book_n_sessions: number;
  book_sessions: string[];
  by_tier: Record<string, number>;
  by_client: { client_code: string; client_name: string | null; n_trades: number; n_flagged: number }[];
};

export type SurveillanceCase = {
  case_key: string;
  case_id: string;
  client_code: string;
  client_name: string | null;
  scrip: string;
  trade_date: string;
  side: string;                // BUY | SELL | CROSS
  n_fills: number;
  n_fills_total: number;
  qty: number;
  notional: number;
  price: number | null;
  vwap: number | null;
  slippage_pct: number | null;
  markout_5d_pct: number | null;
  score: number;                 // integrated verdict 0-100 (fuses all lenses)
  microstructure_score?: number; // execution/manipulation-only sub-score
  tier: string | null;
  pattern: string;
  // Integrated-verdict factor breakdown — one entry per lens, sorted by contribution.
  factors?: { lens: string; label: string; value: number; weight: number; contribution: number; note: string }[];
  drivers?: { lens: string; label: string; value: number; weight: number; contribution: number; note: string }[];
  fundamental?: { score: number; health: number; posture: string; tier: string | null; flags: string[]; npl_ratio: number | null; car: number | null; roe: number | null; pe_ratio: number | null; basis: string } | null;
  technical?: { score: number; posture: string; rsi: number | null; pos_in_range: number | null; as_of: string | null; basis: string } | null;
  counterparty: string | null;
  concentration: { label: string; value: number; expected: number; surprise_z: number } | null;
  market_context: {
    trade_date: { buy_share: number | null; sell_share: number | null; total_share: number | null; n_days: number; rank: number | null; n_brokers: number; dominant: boolean };
    hist_30d: { buy_share: number | null; sell_share: number | null; total_share: number | null; n_days: number };
    hist_90d: { buy_share: number | null; sell_share: number | null; total_share: number | null; n_days: number };
    positioning_7d: { net_qty: number; label: string };
    positioning_30d: { net_qty: number; label: string };
  } | null;
  classification: { label: string; confidence: number; ratio: number; rationale: string } | null;
  flag_reasons: string[];
  tags: string[];
  scrip_speculation_tier: string | null;
  window: string | null;
  explanation: string | null;
  explanation_model: string | null;
  responses: CaseResponse[];
  fills: { t: string; side: string; qty: number; px: number }[];
  markout_curve: number[] | null;
};

export type CaseResponse = {
  id: number;
  author: string;
  body: string;
  created_at: string | null;
};

export type CaseChatTurn = {
  id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string | null;
};

// --- SMTM live fundamentals + timeseries (on-demand from the SMTM Data API) ---
export type SmtmKeyStatsPeriod = {
  year: string | null;
  quarter: number | null;
  label: string | null;
  data_source: string | null;
  eps: number | null;
  pe: number | null;
  roe: number | null;
  roa: number | null;
  book_value_per_share: number | null;
  dividend_per_share: number | null;
  total_revenue: number | null;
  net_income: number | null;
  net_income_margin: number | null;
  gross_profit_margin: number | null;
  market_cap: number | null;
  mps: number | null;
  npl: number | null;
  capital_adequacy: number | null;
};

export type SmtmFinancials = {
  scrip: string;
  has_data: boolean;
  data_source: string;
  latest: SmtmKeyStatsPeriod | null;
  annual: SmtmKeyStatsPeriod[];
  quarterly: SmtmKeyStatsPeriod[];
  statements: {
    income: Record<string, unknown>[];
    balance: Record<string, unknown>[];
    cashflow: Record<string, unknown>[];
  };
  counts: { annual: number; quarterly: number; income: number; balance: number; cashflow: number };
};

export type IntradayPoint = { t: string; price: number | null; volume: number | null; amount: number | null };
export type IntradayResponse = { scrip: string; points: number; series: IntradayPoint[] };

export type IndexTsPoint = { t: string; value: number | null; turnover: number | null };
export type IndexTimeseriesResponse = { slug: string; name: string; points: number; series: IndexTsPoint[] };

export const api = {
  universe: () => getJSON<UniverseRow[]>("/api/universe"),
  marketPulse: () => getJSON<MarketPulse>("/api/market-pulse"),
  marketNews: (limit = 18) => getJSON<MarketNewsItem[]>(`/api/market-news?limit=${limit}`),
  alerts: {
    recent: (limit = 30, activeOnly = false) =>
      getJSON<AlertRow[]>(`/api/alerts/recent?limit=${limit}${activeOnly ? "&active_only=true" : ""}`),
    run: (mode: "incremental" | "digest" = "incremental") => postJSON<{ ok: boolean }>(`/api/alerts/run?mode=${mode}`),
  },
  surveillance: {
    trades: (params: { tier?: string; client_code?: string; scrip?: string; min_score?: number; limit?: number; from_date?: string; to_date?: string } = {}) => {
      const q = new URLSearchParams();
      if (params.tier) q.set("tier", params.tier);
      if (params.client_code) q.set("client_code", params.client_code);
      if (params.scrip) q.set("scrip", params.scrip);
      if (params.min_score != null) q.set("min_score", String(params.min_score));
      if (params.limit != null) q.set("limit", String(params.limit));
      if (params.from_date) q.set("from_date", params.from_date);
      if (params.to_date) q.set("to_date", params.to_date);
      const qs = q.toString();
      return getJSON<SurveillanceTrade[]>(`/api/surveillance/trades${qs ? `?${qs}` : ""}`);
    },
    summary: (fromDate?: string, toDate?: string) => {
      const q = new URLSearchParams();
      if (fromDate) q.set("from_date", fromDate);
      if (toDate) q.set("to_date", toDate);
      const qs = q.toString();
      return getJSON<SurveillanceSummary>(`/api/surveillance/summary${qs ? `?${qs}` : ""}`);
    },
    cases: (minScore = 25, fromDate?: string, toDate?: string) => {
      const q = new URLSearchParams({ min_score: String(minScore) });
      if (fromDate) q.set("from_date", fromDate);
      if (toDate) q.set("to_date", toDate);
      return getJSON<SurveillanceCase[]>(`/api/surveillance/cases?${q.toString()}`);
    },
    explain: (caseKeys: string[], minScore = 25) =>
      postJSON<{ ok: boolean; generated: number }>(`/api/surveillance/explain?min_score=${minScore}`, { case_keys: caseKeys }),
    addResponse: (caseKey: string, body: string, author?: string) =>
      postJSON<{ ok: boolean; response: CaseResponse }>(
        `/api/surveillance/cases/${encodeURIComponent(caseKey)}/responses`, { body, author }),
    counterparties: (minTrades = 2, limit = 50) =>
      getJSON<CounterpartyExposure[]>(`/api/surveillance/counterparties?min_trades=${minTrades}&limit=${limit}`),
    caseChat: (caseKey: string) =>
      getJSON<CaseChatTurn[]>(`/api/surveillance/cases/${encodeURIComponent(caseKey)}/chat`),
    saveCaseFinding: (caseKey: string, author?: string) =>
      postJSON<{ ok: boolean; response?: CaseResponse; error?: string }>(
        `/api/surveillance/cases/${encodeURIComponent(caseKey)}/chat/save-finding`, { body: "", author }),
    // SSE chat scoped to one surveillance case — mirrors chatStream.
    caseChatStream: (
      caseKey: string,
      query: string,
      onToken: (token: string) => void,
      onDone: () => void,
      onError: (err: Error) => void,
      onStatus?: (text: string) => void,
    ): AbortController => {
      const ctrl = new AbortController();
      (async () => {
        try {
          const res = await fetch(`${BACKEND}/api/surveillance/cases/${encodeURIComponent(caseKey)}/chat/stream`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query }),
            signal: ctrl.signal,
          });
          if (!res.ok) throw new Error(`case chat → ${res.status} ${res.statusText}`);
          const reader = res.body!.getReader();
          const decoder = new TextDecoder();
          let buf = "";
          for (;;) {
            const { value, done } = await reader.read();
            if (done) break;
            buf += decoder.decode(value, { stream: true });
            const lines = buf.split("\n");
            buf = lines.pop() ?? "";
            for (const line of lines) {
              if (!line.startsWith("data: ")) continue;
              const raw = line.slice(6).trim();
              if (!raw) continue;
              const ev = JSON.parse(raw) as { type: string; text?: string; message?: string };
              if (ev.type === "token" && ev.text) onToken(ev.text);
              else if (ev.type === "status" && ev.text && onStatus) onStatus(ev.text);
              else if (ev.type === "error") throw new Error(ev.message || "stream error");
              else if (ev.type === "done") onDone();
            }
          }
        } catch (e) {
          if ((e as Error).name !== "AbortError") onError(e as Error);
        }
      })();
      return ctrl;
    },
  },
  universeSparklines: (days = 30) =>
    getJSON<Record<string, number[]>>(`/api/universe/sparklines?days=${days}`),
  indices: () => getJSON<IndexRow[]>("/api/indices"),
  stage2: () => getJSON<Stage2Row[]>("/api/stage2"),
  prices: (scrip: string, days = 90) => getJSON<PricePoint[]>(`/api/prices/${scrip}?days=${days}`),
  health: () => getJSON<{ status: string; checks?: Record<string, boolean> }>("/ready"),

  // --- Phase I+J universe-scoped ---
  scorecard:       () => getJSON<ScorecardRow[]>("/api/scorecard"),
  quadrant:        () => getJSON<QuadrantRow[]>("/api/quadrant"),
  sectorMomentum:  () => getJSON<SectorMomentumRow[]>("/api/sector-momentum"),

  // --- Phase I+J scrip-scoped ---
  scrip: {
    summary:            (s: string) => getJSON<ScripSummary>(`/api/scrip/${s}/summary`),
    profile:            (s: string) => getJSON<ScripProfile>(`/api/scrip/${s}/profile`),
    fundamentalsHistory:(s: string, q = 20) => getJSON<FundamentalsHistoryRow[]>(`/api/scrip/${s}/fundamentals-history?quarters=${q}`),
    valuationHistory:   (s: string, q = 20) => getJSON<ValuationHistoryRow[]>(`/api/scrip/${s}/valuation-history?quarters=${q}`),
    returns:            (s: string) => getJSON<ReturnsSnapshot>(`/api/scrip/${s}/returns`),
    piotroski:          (s: string, q = 20) => getJSON<PiotroskiRow[]>(`/api/scrip/${s}/piotroski?quarters=${q}`),
    dupont:             (s: string, q = 20) => getJSON<DupontRow[]>(`/api/scrip/${s}/dupont?quarters=${q}`),
    assetQuality:       (s: string, q = 20) => getJSON<AssetQualityRow[]>(`/api/scrip/${s}/asset-quality?quarters=${q}`),
    capital:            (s: string, q = 20) => getJSON<CapitalRow[]>(`/api/scrip/${s}/capital?quarters=${q}`),
    dividends:          (s: string) => getJSON<DividendsResponse>(`/api/scrip/${s}/dividends`),
    technicals:         (s: string) => getJSON<TechnicalsSnapshot>(`/api/scrip/${s}/technicals`),
    quality:            (s: string, q = 20) => getJSON<QualityRow[]>(`/api/scrip/${s}/quality?quarters=${q}`),
    floorsheet:         (s: string) => getJSON<FloorsheetResponse>(`/api/scrip/${s}/floorsheet`),
    newsSentiment:      (s: string) => getJSON<NewsSentimentResponse>(`/api/scrip/${s}/news-sentiment`),
    // Live SMTM: deep statement history (all sectors, ~19y) + today's intraday bars.
    financials:         (s: string, statements = 6) => getJSON<SmtmFinancials>(`/api/scrip/${s}/financials?statements=${statements}`),
    intraday:           (s: string) => getJSON<IntradayResponse>(`/api/scrip/${s}/intraday`),
  },

  // --- Index intraday/history timeseries (live SMTM) ---
  indexTimeseries: (slug = "nepse") => getJSON<IndexTimeseriesResponse>(`/api/index/${slug}/timeseries`),

  // --- Compare / Screen ---
  compare: (scrips: string[]) => getJSON<ScripSummary[]>(`/api/compare?scrips=${encodeURIComponent(scrips.join(","))}`),
  screen:  (preset: "top-quality" | "cheap-vs-self" | "high-yield" | "contrarian" | "turnaround") =>
    getJSON<ScreenResponse>(`/api/screen/${preset}`),

  // --- Pipeline trigger ---
  pipeline: {
    refresh: (jobs?: string[]) =>
      postJSON<PipelineState>("/api/pipeline/refresh", jobs?.length ? { jobs } : undefined),
    status:  () => getJSON<PipelineState>("/api/pipeline/status"),
    tradebookFiles: () =>
      getJSON<TradebookFiles>("/api/pipeline/tradebook-files"),
  },

  // --- Speculative analysis ---
  speculative: {
    upload: (file: File, title?: string, notes?: string) =>
      postForm<SpeculativeUploadResponse>("/api/speculative/upload", { file, title, notes }),
    analyze: (sessionId: string) =>
      postJSON<SpeculativeAnalyzeResponse>(`/api/speculative/${sessionId}/analyze`),
    listSessions: () =>
      getJSON<SpeculativeSessionListItem[]>("/api/speculative/sessions"),
    getSession: (sessionId: string) =>
      getJSON<SpeculativeSessionDetail>(`/api/speculative/sessions/${sessionId}`),
    deleteSession: (sessionId: string) =>
      del(`/api/speculative/sessions/${sessionId}`),
    sampleTemplateUrl: () => `${BACKEND}/api/speculative/sample-template.csv`,
  },

  chatStream: (
    query: string,
    sessionId: string,
    onToken: (token: string) => void,
    onDone: (traceId?: string) => void,
    onError: (err: Error) => void,
    onStatus?: (text: string) => void,
    // Page-context from the chat drawer — agent reads and prepends a
    // "User is viewing NABIL" line to its system prompt. Missing = no change.
    context?: PageContext | null,
  ): AbortController => {
    const ctrl = new AbortController();
    (async () => {
      try {
        const res = await fetch(`${BACKEND}/chat/stream`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query,
            session_id: sessionId,
            ...(context ? { context } : {}),
          }),
          signal: ctrl.signal,
        });
        if (!res.ok) throw new Error(`POST /chat/stream → ${res.status} ${res.statusText}`);

        const reader = res.body!.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const lines = buf.split("\n");
          buf = lines.pop() ?? "";
          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const raw = line.slice(6).trim();
            if (!raw) continue;
            const ev = JSON.parse(raw) as { type: string; text?: string; trace_id?: string; message?: string };
            if (ev.type === "token" && ev.text) {
              onToken(ev.text);
              // 25ms minimum between token paints — gives the browser a macrotask
              // boundary so flushSync's DOM commit gets actually painted each time.
              await new Promise<void>(r => setTimeout(r, 25));
            }
            if (ev.type === "status" && ev.text) onStatus?.(ev.text);
            if (ev.type === "done") onDone(ev.trace_id);
            if (ev.type === "error") onError(new Error(ev.message ?? "stream error"));
          }
        }
        onDone();
      } catch (e) {
        if ((e as Error).name !== "AbortError") onError(e instanceof Error ? e : new Error(String(e)));
      }
    })();
    return ctrl;
  },

  clearSession: async (sessionId: string): Promise<void> => {
    await fetch(`${BACKEND}/chat/session/${sessionId}`, { method: "DELETE" });
  },

  marketStreamUrl: (scrips?: string): string => {
    const qs = scrips ? `?scrips=${encodeURIComponent(scrips)}` : "";
    return `${BACKEND}/stream/market${qs}`;
  },
};
