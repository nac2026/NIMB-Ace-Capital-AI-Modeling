"use client";

// "Metrics" tab content for /help — every calculated metric, with a plain-
// English definition, the formula, how to interpret it, and the Postgres
// source. Structured as categories so new metrics slot into the right
// bucket without the page growing unwieldy.

import type { ReactNode } from "react";
import {
  QualityTierChip, SelfValuationChip, MarketCapChip, Pill,
} from "@/components/dashboard/chips";
import { Code, Formula, SourceTag, Labeled } from "./primitives";

export type Metric = {
  name: string;
  slug: string;                   // #hash id
  summary: ReactNode;             // what it represents in plain English
  formula?: ReactNode;            // shown in a monospace box
  interpretation?: ReactNode;     // rules of thumb, bucket thresholds
  source?: string;                // postgres table/column
  example?: ReactNode;            // live chip
};

export type MetricCategory = {
  id: string;
  title: string;
  blurb?: ReactNode;
  metrics: Metric[];
};

export const METRIC_CATEGORIES: MetricCategory[] = [
  {
    id: "composites",
    title: "Composite scores & classifications",
    blurb: <>Rollups that summarise many signals into one number or label. These are what the dashboard table uses as primary sort keys.</>,
    metrics: [
      {
        name: "Scorecard 0–100",
        slug: "scorecard",
        summary: "Cross-sectional composite rank of a scrip against all 19 banks. Combines five pillars equally: Quality, Valuation, Momentum, Risk, Income.",
        formula: <Formula>scorecard_0_100 = round(<br />&nbsp;&nbsp;100 × mean(quality_pct, valuation_pct, momentum_pct, risk_pct, income_pct)<br />)</Formula>,
        interpretation: <>Each pillar is already a percentile 0-1 within the universe. <Code>70+</Code> = strong, <Code>40-70</Code> = middle of the pack, <Code>&lt;40</Code> = weak vs peers.</>,
        source: "investment_scorecard.scorecard_0_100",
      },
      {
        name: "Quality score 0–100",
        slug: "quality-score",
        summary: "Fundamental-quality-only composite. Independent of price, so two stocks with identical Quality scores can sit anywhere on the valuation spectrum.",
        formula: <Formula>quality_score = round(100 × mean(<br />&nbsp;&nbsp;profitability_pct, asset_quality_pct, growth_pct,<br />&nbsp;&nbsp;capital_pct, efficiency_pct, piotroski_pct<br />))</Formula>,
        interpretation: <>Bucketed into <Code>TOP_DECILE</Code> / <Code>STRONG</Code> / <Code>AVERAGE</Code> / <Code>BELOW_AVERAGE</Code> / <Code>WEAK</Code> by universe rank.</>,
        source: "fundamental_quality_composite.quality_score_0_100",
      },
      {
        name: "Quality tier",
        slug: "quality-tier",
        summary: "Bucketed version of Quality score 0-100.",
        interpretation: <><Code>TOP_DECILE</Code> = top 10%, <Code>STRONG</Code> = top 25% excluding top decile, <Code>AVERAGE</Code> = middle 50%, <Code>BELOW_AVERAGE</Code> = bottom 25% excluding weakest, <Code>WEAK</Code> = bottom 10%.</>,
        source: "fundamental_quality_composite.quality_tier",
        example: <QualityTierChip tier="TOP_DECILE" />,
      },
      {
        name: "Quadrant",
        slug: "quadrant",
        summary: "2×2 classification of Quality score vs 6-month return, cut at sector medians.",
        interpretation: <>
          <div className="grid grid-cols-2 gap-2 mt-2">
            <div className="rounded px-2 py-1.5" style={{ border: "1px solid var(--border-subtle)", background: "color-mix(in srgb, var(--ok) 8%, transparent)" }}>
              <div className="text-[11px] font-semibold text-ok uppercase tracking-wider">Quality leader</div>
              <div className="text-[11px] text-fg-muted">High quality + high momentum. Market already rewards these.</div>
            </div>
            <div className="rounded px-2 py-1.5" style={{ border: "1px solid var(--border-subtle)", background: "color-mix(in srgb, var(--warn) 10%, transparent)" }}>
              <div className="text-[11px] font-semibold text-warn uppercase tracking-wider">Contrarian bet</div>
              <div className="text-[11px] text-fg-muted">High quality + weak momentum. Unloved but fundamentally strong.</div>
            </div>
            <div className="rounded px-2 py-1.5" style={{ border: "1px solid var(--border-subtle)", background: "color-mix(in srgb, var(--warn) 10%, transparent)" }}>
              <div className="text-[11px] font-semibold text-warn uppercase tracking-wider">Momentum trap</div>
              <div className="text-[11px] text-fg-muted">Low quality + high momentum. Running on sentiment — watch out.</div>
            </div>
            <div className="rounded px-2 py-1.5" style={{ border: "1px solid var(--border-subtle)", background: "color-mix(in srgb, var(--err) 8%, transparent)" }}>
              <div className="text-[11px] font-semibold text-err uppercase tracking-wider">Avoid</div>
              <div className="text-[11px] text-fg-muted">Low quality + low momentum.</div>
            </div>
          </div>
        </>,
        source: "quality_momentum_matrix.quadrant",
      },
      {
        name: "Piotroski F-score",
        slug: "piotroski",
        summary: "Bank-adapted 9-signal 'getting better?' score, 0-9. Each signal is a directional QoQ or YoY test.",
        formula: <Formula>
          f_score = p1 + p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9<br /><br />
          p1 = 1 if net_profit &gt; 0<br />
          p2 = 1 if roa &gt; 0<br />
          p3 = 1 if net_profit_yoy &gt; 0<br />
          p4 = 1 if roa &gt; prior_year_roa<br />
          p5 = 1 if npl_ratio ≤ prior_year_npl<br />
          p6 = 1 if car ≥ prior_year_car<br />
          p7 = 1 if shares_outstanding did not grow &gt; 5% yoy<br />
          p8 = 1 if nim &gt; prior_year_nim<br />
          p9 = 1 if cost_to_income &lt; prior_year_cost_to_income
        </Formula>,
        interpretation: <><Code>7+</Code> strong, <Code>4–6</Code> mixed, <Code>0–3</Code> weak. Always cite specific failed signals when explaining a low score — the number alone is less useful than which levers slipped.</>,
        source: "piotroski_f_score.f_score",
      },
      {
        name: "DuPont decomposition",
        slug: "dupont",
        summary: "Splits ROE into its drivers so you can see whether profitability is powered by margin, turnover, or leverage.",
        formula: <Formula>
          ROE = ROA × Equity Multiplier<br />
          &nbsp;&nbsp;&nbsp;&nbsp;= (Net Margin × Asset Turnover) × Leverage<br /><br />
          Net Margin = net_profit / operating_income<br />
          Asset Turnover = operating_income / avg_assets<br />
          Equity Multiplier = avg_assets / avg_equity
        </Formula>,
        interpretation: <>Two banks can have the same ROE from very different mixes: one via thin margins + heavy leverage, another via fat margins + conservative balance sheet. DuPont reveals the distinction.</>,
        source: "dupont_decomposition",
      },
    ],
  },

  {
    id: "profitability",
    title: "Profitability",
    blurb: <>How efficiently the bank converts assets and capital into profit.</>,
    metrics: [
      {
        name: "ROE (Return on Equity)",
        slug: "roe",
        summary: "Net profit as a percent of average shareholders' equity. The headline 'how well is management using my capital' metric.",
        formula: <Formula>ROE = net_profit_ttm / avg_equity</Formula>,
        interpretation: <>Nepali commercial banks typically run <Code>12–18%</Code>. <Code>&gt;20%</Code> exceptional, <Code>&lt;10%</Code> weak. Cross-reference with leverage — a high ROE with high leverage is riskier than a high ROE from strong margins.</>,
        source: "fundamental_snapshots.roe",
      },
      {
        name: "ROA (Return on Assets)",
        slug: "roa",
        summary: "Net profit as a percent of average assets. Leverage-neutral; measures raw earnings power per rupee on the balance sheet.",
        formula: <Formula>ROA = net_profit_ttm / avg_total_assets</Formula>,
        interpretation: <>Banks typically <Code>1.0–1.8%</Code>. Leverage amplifies ROA into ROE, so high ROA + modest leverage is the cleanest profile.</>,
        source: "fundamental_snapshots.roa",
      },
      {
        name: "NIM (Net Interest Margin)",
        slug: "nim",
        summary: "Net interest income as a percent of average earning assets. Core banking profitability — how much spread the bank earns on lending.",
        formula: <Formula>NIM = net_interest_income_ttm / avg_earning_assets</Formula>,
        interpretation: <>Nepali banks generally <Code>3.5–4.5%</Code>. Persistent NIM compression often flags intensifying deposit competition or asset-repricing lag.</>,
        source: "ttm_fundamentals.ttm_nim",
      },
      {
        name: "Cost-to-Income ratio",
        slug: "cti",
        summary: "Operating expenses divided by operating income. Lower = more efficient.",
        formula: <Formula>CTI = operating_expenses / operating_income</Formula>,
        interpretation: <><Code>&lt;45%</Code> efficient, <Code>45–55%</Code> typical, <Code>&gt;55%</Code> bloated. Watch the trajectory more than the level — efficiency tiers reward improvement.</>,
        source: "cost_efficiency.cost_to_income",
      },
    ],
  },

  {
    id: "asset-quality",
    title: "Asset quality",
    blurb: <>How clean the loan book is and how well the bank has reserved for trouble.</>,
    metrics: [
      {
        name: "NPL ratio",
        slug: "npl-ratio",
        summary: "Non-performing loans as a fraction of gross loans. The primary asset-quality gauge.",
        formula: <Formula>npl_ratio = non_performing_loans / gross_loans</Formula>,
        interpretation: <><Code>&lt;2%</Code> clean, <Code>2–5%</Code> moderate, <Code>&gt;5%</Code> concerning. Direction matters more than level: a scrip at 4% rising is worse than a scrip at 5% falling.</>,
        source: "fundamental_snapshots.npl_ratio",
      },
      {
        name: "LLP / NPL (coverage)",
        slug: "llp-coverage",
        summary: "Loan-loss provisions divided by NPL. Shows how well the bank has reserved for existing bad loans.",
        formula: <Formula>coverage = loan_loss_provisions / non_performing_loans</Formula>,
        interpretation: <><Code>&gt;1.0</Code> = provisions exceed current bad loans (conservative). <Code>0.8–1.0</Code> adequate. <Code>&lt;0.8</Code> under-provisioned — future earnings hit likely.</>,
        source: "asset_quality_trends.llp_to_npl_ratio",
      },
      {
        name: "NPL QoQ / YoY change (pp)",
        slug: "npl-delta",
        summary: "Absolute change in NPL ratio in percentage points, QoQ and YoY. Isolates the trajectory from the level.",
        formula: <Formula>npl_qoq_change_abs = npl_this_q − npl_prev_q<br />npl_yoy_change_abs = npl_this_q − npl_same_q_prior_year</Formula>,
        interpretation: <>Rising (positive delta) is a warning. A +0.5pp YoY move on a 3% base is a 17% relative deterioration.</>,
        source: "asset_quality_trends.npl_{qoq,yoy}_change_abs",
      },
      {
        name: "Credit-loss rate (TTM)",
        slug: "credit-loss",
        summary: "Trailing 12-month credit-loss expense as a fraction of average loans. The income-statement view of bad-loan cost.",
        formula: <Formula>credit_loss_rate_ttm = credit_losses_ttm / avg_loans</Formula>,
        interpretation: <>Banks typically <Code>0.3–1.2%</Code>. Spikes foreshadow NPL upticks by 1-2 quarters.</>,
        source: "asset_quality_trends.credit_loss_rate_ttm",
      },
      {
        name: "Asset-quality tier",
        slug: "asset-quality-tier",
        summary: "Composite label over NPL level + trajectory.",
        interpretation: <><Code>STRONG</Code>: low NPL + improving / stable. <Code>MODERATE</Code>: mid-range or mixed signals. <Code>WEAK</Code>: high NPL or deteriorating trajectory.</>,
        source: "asset_quality_trends.asset_quality_tier",
        example: <Pill label="STRONG" tone="ok" />,
      },
    ],
  },

  {
    id: "capital",
    title: "Capital",
    blurb: <>Whether the bank has enough cushion to absorb losses and keep lending.</>,
    metrics: [
      {
        name: "CAR (Capital Adequacy Ratio)",
        slug: "car",
        summary: "Total regulatory capital divided by risk-weighted assets. The NRB's primary solvency metric.",
        formula: <Formula>CAR = (tier_1_capital + tier_2_capital) / risk_weighted_assets</Formula>,
        interpretation: <>NRB minimum <Code>11%</Code>. <Code>11–12%</Code> tight, <Code>12–14%</Code> adequate, <Code>&gt;14%</Code> strong. Sustained sub-11% triggers supervisory action.</>,
        source: "fundamental_snapshots.car",
      },
      {
        name: "Tier 1 share",
        slug: "tier1-share",
        summary: "Tier 1 (common equity + retained earnings) as a share of total capital.",
        formula: <Formula>tier1_share = tier_1_capital / (tier_1 + tier_2)</Formula>,
        interpretation: <><Code>&gt;70%</Code> means most capital is highest-quality equity — the best shock absorber.</>,
        source: "capital_strength.tier1_share",
      },
      {
        name: "CAR buffer",
        slug: "car-buffer",
        summary: "Distance between current CAR and the NRB 11% minimum, in percentage points.",
        formula: <Formula>car_buffer = car − 0.11</Formula>,
        interpretation: <>Positive = cushion exists. Negative = breach. Tight capital (&lt;1pp buffer) constrains lending growth.</>,
        source: "capital_strength.car_buffer",
      },
      {
        name: "Capital tier",
        slug: "capital-tier",
        summary: "Bucketed label.",
        interpretation: <><Code>STRONG</Code>: CAR &gt; 14%. <Code>ADEQUATE</Code>: 12–14%. <Code>TIGHT_CAPITAL</Code>: 11–12%. <Code>BREACH</Code>: &lt;11%.</>,
        source: "capital_strength.capital_tier",
        example: <Pill label="ADEQUATE" tone="muted" />,
      },
    ],
  },

  {
    id: "liquidity",
    title: "Liquidity & balance sheet",
    blurb: <>How much of the deposit base is currently lent out and how fast the book is growing.</>,
    metrics: [
      {
        name: "CD ratio (Credit to Deposit)",
        slug: "cd-ratio",
        summary: "Total loans divided by total deposits.",
        formula: <Formula>cd_ratio = total_loans / total_deposits</Formula>,
        interpretation: <>NRB cap <Code>90%</Code>. <Code>&gt;85%</Code> tight liquidity — further lending growth would require new funding. <Code>&lt;75%</Code> suggests capacity for loan growth.</>,
        source: "fundamental_snapshots.cd_ratio",
      },
      {
        name: "Growth rates (YoY / QoQ)",
        slug: "growth",
        summary: "Period-over-period percent changes for net profit, operating income, loans, deposits.",
        formula: <Formula>yoy_pct = (value_this_q − value_same_q_prior_year) / value_same_q_prior_year</Formula>,
        interpretation: <>Deposit growth funds loan growth. A bank growing loans fast with flat deposits will hit a CD-ratio wall.</>,
        source: "quarterly_growth.{field}_{yoy,qoq}_pct",
      },
      {
        name: "TTM (Trailing Twelve Months)",
        slug: "ttm",
        summary: "Rolling 4-quarter sum (for flows like profit) or average (for stocks like assets). Smooths out quarterly seasonality.",
        formula: <Formula>ttm_net_profit = sum(net_profit over last 4 quarters)</Formula>,
        interpretation: <>Always prefer TTM over single-quarter numbers for comparisons — Q2 vs Q2 prior year is still subject to one-off items; TTM averages those out.</>,
        source: "ttm_fundamentals.ttm_*",
      },
    ],
  },

  {
    id: "valuation",
    title: "Valuation",
    blurb: <>What the market is paying for a rupee of earnings or book value, and whether that's cheap vs history.</>,
    metrics: [
      {
        name: "P/E ratio",
        slug: "pe-ratio",
        summary: "Price per share divided by trailing EPS. How many rupees investors pay per rupee of annual profit.",
        formula: <Formula>pe = market_price / ttm_eps</Formula>,
        interpretation: <>A level alone tells you little. Compare to (a) the scrip's own history via self-percentile, and (b) peer P/E distribution.</>,
        source: "fundamental_snapshots.pe_ratio",
      },
      {
        name: "P/B ratio",
        slug: "pb-ratio",
        summary: "Price per share divided by book value per share.",
        formula: <Formula>pb = market_price / bvps</Formula>,
        interpretation: <><Code>&lt;1</Code> = trading below book value (rare for healthy banks). <Code>1–2</Code> typical range. Pair with ROE: high ROE justifies higher P/B; low ROE + high P/B is expensive.</>,
        source: "fundamental_snapshots.pb_ratio",
      },
      {
        name: "P/E self-percentile (5Y)",
        slug: "pe-self-pct",
        summary: "Where today's P/E sits inside the scrip's own trailing 5-year distribution.",
        formula: <Formula>pe_self_pct_5y = rank(current_pe among last_20_quarters_pe) / 20</Formula>,
        interpretation: <><Code>0.15</Code> → cheaper than 85% of the scrip's own past 5 years. Answers "is NABIL cheap vs its own past?" — complements peer-relative P/E.</>,
        source: "valuation_history.pe_self_pct_5y",
      },
      {
        name: "Self-valuation tier",
        slug: "self-valuation-tier",
        summary: "Bucketed self-percentile.",
        interpretation: <><Code>VERY_CHEAP</Code>: &lt;10th pct. <Code>CHEAP</Code>: 10-30th. <Code>FAIR</Code>: 30-70th. <Code>EXPENSIVE</Code>: 70-90th. <Code>VERY_EXPENSIVE</Code>: &gt;90th.</>,
        source: "valuation_history.self_valuation_tier",
        example: <SelfValuationChip tier="CHEAP" />,
      },
    ],
  },

  {
    id: "returns-risk",
    title: "Returns & risk",
    blurb: <>Historical price returns and the risk profile of getting them.</>,
    metrics: [
      {
        name: "Price returns (1M / 3M / 6M / 1Y / 3Y / 5Y)",
        slug: "returns",
        summary: "Cumulative price-only returns over each window. Excludes dividends.",
        formula: <Formula>return_N = (close_today − close_N_trading_days_ago) / close_N_trading_days_ago</Formula>,
        source: "price_returns.return_{1m,3m,6m,1y,3y,5y}",
      },
      {
        name: "TSR (Total Shareholder Return)",
        slug: "tsr",
        summary: "Price returns plus reinvested dividends. The true 'what did I make' number.",
        formula: <Formula>tsr_1y = (total_return_incl_dividends_1y) − 1</Formula>,
        interpretation: <>Always higher than price-only return for a dividend-paying stock. The gap = cash yield contribution.</>,
        source: "total_shareholder_return.tsr_{1y,3y,5y}",
      },
      {
        name: "Beta vs NEPSE",
        slug: "beta",
        summary: "Sensitivity of scrip daily returns to NEPSE index daily returns.",
        formula: <Formula>beta = slope of OLS(scrip_daily_return ~ nepse_daily_return, 2Y window)</Formula>,
        interpretation: <><Code>1.0</Code> = moves with the index. <Code>&gt;1</Code> amplifies market moves, <Code>&lt;1</Code> dampens them. <Code>&lt;0</Code> (rare) = moves opposite to NEPSE.</>,
        source: "beta_and_volatility.beta",
      },
      {
        name: "Alpha (annualized)",
        slug: "alpha",
        summary: "OLS regression intercept × 252. Annual excess return NOT explained by market beta.",
        formula: <Formula>alpha_annual = intercept × 252</Formula>,
        interpretation: <>Positive = outperforming after adjusting for systematic risk. Keep in mind the 2Y window — a single great year inflates alpha.</>,
        source: "beta_and_volatility.alpha_annual",
      },
      {
        name: "R²",
        slug: "r-squared",
        summary: "How much of the scrip's daily moves are explained by NEPSE moves.",
        interpretation: <><Code>0.6+</Code> highly correlated to market, <Code>&lt;0.2</Code> idiosyncratic. Low R² means beta is less meaningful as a risk proxy — the scrip marches to its own drum.</>,
        source: "beta_and_volatility.r_squared",
      },
      {
        name: "Sharpe ratio (2Y)",
        slug: "sharpe",
        summary: "Risk-adjusted return — excess return per unit of volatility.",
        formula: <Formula>sharpe = (annual_return − risk_free_rate) / annual_vol</Formula>,
        interpretation: <><Code>&gt;1</Code> good, <Code>&gt;2</Code> exceptional, <Code>&lt;0</Code> underperforming the risk-free rate even after taking equity risk.</>,
        source: "beta_and_volatility.sharpe_ratio_2y",
      },
      {
        name: "Realized volatility",
        slug: "vol",
        summary: "Standard deviation of daily returns, annualized.",
        formula: <Formula>annualized_vol = stdev(daily_returns) × √252</Formula>,
        interpretation: <>Nepali banks typically <Code>15–30%</Code> annualized. A sudden rise foreshadows either big moves or deteriorating fundamentals.</>,
        source: "beta_and_volatility.annualized_vol",
      },
      {
        name: "Drawdown from peak",
        slug: "drawdown",
        summary: "How far today's price is below the trailing 1-year high.",
        formula: <Formula>drawdown = (current_close / max(close, 1Y)) − 1</Formula>,
        interpretation: <><Code>−0.20</Code> = 20% below the year's high. Deep drawdowns on still-healthy fundamentals are classic CONTRARIAN_BET territory.</>,
        source: "price_returns.drawdown_from_peak",
      },
    ],
  },

  {
    id: "dividends",
    title: "Dividends & income",
    blurb: <>Cash and bonus distributions plus derived yields.</>,
    metrics: [
      {
        name: "Cash dividend %",
        slug: "cash-div",
        summary: "Cash dividend rate on par value (not on market price). Nepali convention.",
        formula: <Formula>annual_cash_div_pct = sum(cash_div_rate) for fiscal year, on par = NPR 100</Formula>,
        source: "corporate_actions.amount (action_type = 'cash_dividend')",
      },
      {
        name: "Bonus share %",
        slug: "bonus-share",
        summary: "Bonus share rate for the fiscal year, also on par. Effectively a stock dividend — shares go up, price adjusts.",
        source: "corporate_actions.ratio (action_type = 'bonus_share')",
      },
      {
        name: "Cash dividend yield",
        slug: "cash-yield",
        summary: "Cash dividend value divided by current market price.",
        formula: <Formula>cash_yield = (annual_cash_div_pct × par) / market_price</Formula>,
        interpretation: <>The recurring cash income a shareholder collects — the part most directly comparable to an FD interest rate.</>,
        source: "dividend_yield.cash_dividend_yield",
      },
      {
        name: "Total dividend yield",
        slug: "total-yield",
        summary: "Cash + bonus combined (bonus treated as dividend-equivalent value).",
        formula: <Formula>total_yield = (annual_cash_div_pct + annual_bonus_pct) × par / market_price</Formula>,
        interpretation: <><Code>≥8%</Code> = above FD rate (income-attractive). The dashboard bolds these green.</>,
        source: "dividend_yield.total_dividend_yield",
      },
      {
        name: "Yield tier",
        slug: "yield-tier",
        summary: "Bucketed total yield.",
        interpretation: <><Code>ABOVE_FD_RATE</Code>: ≥8%. <Code>NEAR_FD_RATE</Code>: 6-8%. <Code>BELOW_FD_RATE</Code>: &lt;6%. <Code>NONE</Code>: 0.</>,
        source: "dividend_yield.yield_tier",
        example: <Pill label="ABOVE_FD_RATE" tone="ok" />,
      },
    ],
  },

  {
    id: "size-momentum",
    title: "Size & momentum",
    blurb: <>Market-cap classification and 6-month momentum used for the Quadrant.</>,
    metrics: [
      {
        name: "Market cap",
        slug: "market-cap",
        summary: "Total outstanding shares × current market price.",
        formula: <Formula>market_cap_npr = shares_outstanding × market_price</Formula>,
        source: "market_cap_metrics.market_cap_npr",
      },
      {
        name: "Market-cap tier",
        slug: "market-cap-tier",
        summary: "Bucketed market cap (cross-sectional, Nepali-bank context).",
        interpretation: <><Code>LARGE</Code>: ≥100B NPR. <Code>MID</Code>: 20–100B. <Code>SMALL</Code>: 5–20B. <Code>MICRO</Code>: &lt;5B.</>,
        source: "market_cap_metrics.market_cap_tier",
        example: <MarketCapChip tier="LARGE" />,
      },
      {
        name: "6-month return (momentum axis)",
        slug: "return-6m",
        summary: "Same as price_returns.return_6m. Used as the momentum axis on the Quality × Momentum quadrant.",
        source: "price_returns.return_6m",
      },
      {
        name: "Sector momentum",
        slug: "sector-momentum",
        summary: "Sector-level average and median of 3M / 6M / 1Y returns with a rank column. Used to answer 'is NEPSE rotating into banks?'",
        source: "sector_momentum",
      },
    ],
  },

  {
    id: "technicals",
    title: "Technicals",
    blurb: <>Price-only indicators and the 5-rule bullish posture. Presented as data; no BUY/SELL label.</>,
    metrics: [
      {
        name: "SMA 20 / 50 / 200",
        slug: "sma",
        summary: "Simple moving averages over 20, 50, and 200 trading days.",
        formula: <Formula>sma_N = mean(close over last N trading days)</Formula>,
        source: "indicators_daily.sma_{20,50,200}",
      },
      {
        name: "RSI (14)",
        slug: "rsi",
        summary: "Relative Strength Index over 14 days. Momentum oscillator, bounded 0–100.",
        interpretation: <><Code>&gt;70</Code> typically considered overbought, <Code>&lt;30</Code> oversold. Our rule checks the 40-70 'healthy uptrend' band.</>,
        source: "indicators_daily.rsi_14",
      },
      {
        name: "MACD",
        slug: "macd",
        summary: "Moving-average convergence-divergence: difference of 12 and 26-day EMAs, with a 9-day EMA signal line.",
        formula: <Formula>macd = ema_12 − ema_26<br />macd_signal = ema_9(macd)</Formula>,
        interpretation: <>MACD above signal line = bullish crossover.</>,
        source: "indicators_daily.{macd, macd_signal}",
      },
      {
        name: "Bollinger bands",
        slug: "bollinger",
        summary: "20-day SMA ± 2 standard deviations. Upper, middle (=SMA), lower bands.",
        interpretation: <>Price above middle band = short-term strength. Squeeze (narrow bands) often precedes a breakout.</>,
        source: "indicators_daily.bollinger_{upper,middle,lower}",
      },
      {
        name: "5-rule technical posture",
        slug: "technical-posture",
        summary: "Five independent checks, each 1 (pass) or 0 (fail). Reported as 'N of 5 bullish' — no BUY/SELL chip.",
        formula: <Formula>
          r1_trend = 1 if close &gt; sma_200<br />
          r2_ma_align = 1 if sma_20 &gt; sma_50 &gt; sma_200<br />
          r3_rsi = 1 if 40 &lt; rsi_14 &lt; 70<br />
          r4_macd = 1 if macd &gt; macd_signal<br />
          r5_bollinger = 1 if close &gt; bollinger_middle<br /><br />
          signal_sum = r1 + r2 + r3 + r4 + r5
        </Formula>,
        interpretation: <>When explaining a low posture, always cite which specific rules failed — the sum alone is less informative than the failing components.</>,
        source: "technical_signal_summary.{r1..r5, signal_sum}",
      },
    ],
  },

  {
    id: "fiscal-calendar",
    title: "Fiscal calendar context",
    blurb: <>Nepali accounting convention that underpins all fundamental numbers.</>,
    metrics: [
      {
        name: "Fiscal year (BS)",
        slug: "fiscal-year-bs",
        summary: "Nepal's fiscal year follows the Bikram Sambat calendar. FY2082 (BS) corresponds roughly to 2025-06-16 → 2026-07-16 in AD.",
        interpretation: <>All quarterly fundamentals use BS years. <Code>FY2082 Q4</Code> = the Apr–Jul 2026 quarter. Market data and prices still use AD dates.</>,
      },
      {
        name: "Quarter",
        slug: "quarter",
        summary: "1–4, where Q1 is Shrawan–Ashwin (Jul–Oct), Q2 is Kartik–Poush (Oct–Jan), Q3 is Magh–Chaitra (Jan–Apr), Q4 is Baisakh–Ashad (Apr–Jul).",
      },
    ],
  },
];

export function MetricCardView({ metric }: { metric: Metric }) {
  return (
    <div
      id={metric.slug}
      className="scroll-mt-20 rounded-lg px-4 py-4"
      style={{ background: "var(--bg-panel)", border: "1px solid var(--border-subtle)" }}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[14px] font-semibold text-fg">{metric.name}</span>
        {metric.example && <span className="shrink-0">{metric.example}</span>}
      </div>
      <div className="mt-1.5 text-[12.5px] leading-relaxed text-fg-muted">
        {metric.summary}
      </div>

      {metric.formula && (
        <Labeled label="Formula">
          <div className="text-[12.5px]">{metric.formula}</div>
        </Labeled>
      )}
      {metric.interpretation && (
        <Labeled label="How to read it">{metric.interpretation}</Labeled>
      )}
      {metric.source && <SourceTag>{metric.source}</SourceTag>}
    </div>
  );
}
