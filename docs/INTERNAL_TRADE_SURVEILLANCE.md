# Internal Trade Surveillance

> Automated review of NIMB Ace Capital's **own** executed trades — flagging fills that
> warrant a closer look before they become a problem. A flag for review, not a verdict.
>
> Status: **shipped & verified** (Increments 1–3 + scoring v2 + market context + LLM case
> notes + per-case chat). Built 2026-06-11 → 2026-06-12.

---

## 1. Why this exists

The CEO suspects some of the firm's trades — placed by traders/scheme managers, possibly in
coordination with brokers — land on the wrong side of market manipulation: bad fills,
wash-trading counterparties, buying into operator-controlled or pumped scrips. The platform
already detected *market-wide* manipulation (speculation score, broker concentration, wash
pairs). This feature inverts those signals onto the firm's **own trade book**:

**"Are our own funds' trades hitting the wrong side of these signals?"**

Attribution is at the **fund/portfolio level** (`client_code`), deliberately not
person-level.

## 2. The key data unlock

The desk's daily trade-book dump (`Trade_Book_Details *.xlsx`: CONTRACT NO, CLIENT,
CLIENT NAME, SYMBOL, TYPE, PRICE, QTY, VALUE, ORDER ID, TRADE TIME) carries the **NEPSE
contract number** — the same key as `silver.floorsheet.contract_number`. Joining the two
recovers, for every internal fill, **which broker the fund traded through and who the
counterparty broker was** — the spine of everything below.

- `CONTRACT NO` / `ORDER ID` are 16-digit ids → always read as **strings** in Bronze
  (float parsing would round them); Silver casts to BIGINT for the join.
- `client_name` is canonicalized to UPPERCASE in Silver (the dumps spell the same fund
  inconsistently — `NIBL Sahabhagita Fund` vs `NIBL SAHABHAGITA FUND`). `client_code`
  remains the account identity (the same scheme can have multiple accounts — needed for
  cross-trade detection).

**Verified join quality:** on a floorsheet-covered date, 32/32 internal fills matched by
contract_number with price & quantity reconciling exactly and correct side derivation
(`TYPE=Buy` ⇒ fund is `buyer_broker`).

## 3. Pipeline architecture

```
internal-trade-data/*.xlsx                       SMTM live API (floorsheet)
  └► bronze.internal_trades_raw                    └► bronze.floorsheet_raw
       └► silver.internal_trades                        └► silver.floorsheet
            └► dbt gold (JOIN on contract_number + market signals):
                 ├ internal_trade_enriched         broker/counterparty + benchmarks + markouts
                 ├ internal_counterparty_exposure  fund×broker×scrip surprise statistics
                 ├ internal_cross_trade            near-simultaneous intra-firm pairs
                 └ internal_trade_surveillance     HEADLINE: scored row per fill
                      └► Postgres serving ─► /surveillance board + agent tools + case chat
```

### Files (follow the existing medallion conventions)

| Layer | Path |
|---|---|
| Contract | `libs/contracts/nrc_contracts/internal_trade.py` (`InternalTrade`) |
| Bronze ingest | `services/ingestion/nrc_ingestion/sources/client_internal/internal_trades.py` (+ CLI `nrc-ingest internal-trades`) |
| Silver | `services/processing/nrc_processing/silver_internal_trades.py` (**BIGINT cast**, name canonicalization, dedup on contract+client+side) |
| Gold (dbt) | `dbt/models/gold/internal_trade_{enriched,surveillance}.sql`, `internal_counterparty_exposure.sql`, `internal_cross_trade.sql` |
| Serving schema | `infra/postgres/schema/014…019_*.sql` |
| Sync | `services/processing/nrc_processing/sync_postgres.py` (4 `_SyncSpec` rows; drops dbt-duckdb's all-NULL empty-model artifact rows) |
| Dagster | `services/pipelines/nrc_pipelines/assets/bronze_internal.py`, `assets/silver.py` (`silver_internal_trades`), `jobs.py` (`floorsheet_job`), `schedules.py` |
| API | `services/orchestrator/nrc_orchestrator/api_surveillance.py` + `surveillance_cases.py` |
| Agent tools | `services/tools/nrc_tools/get_internal_surveillance.py`, `get_counterparty_exposure.py` |
| Frontend | `services/web/src/app/(main)/surveillance/page.tsx` (+ `lib/api.ts` types/clients) |

## 4. Scoring (v2) — five components, per fill

`surveillance_score = 100 × (0.25·exec + 0.20·manip + 0.25·counterparty + 0.15·cross + 0.15·outcome)`
Tiers: **HIGH ≥ 70 · ELEVATED ≥ 45 · MODERATE ≥ 25 · LOW**. All inputs date-aligned, not snapshots.

| Component | What it measures |
|---|---|
| **exec** (.25) | Slippage vs the **±15-min interval VWAP** (whole-day VWAP fallback; own contract excluded from the window), in **sigmas of the scrip's 20-day volatility** (3σ saturates). Outside the day's traded range = hard 1.0. |
| **manip** (.20) | Worst market signal on the scrip: speculation tier (HIGH 1.0 / ELEVATED .6 / MODERATE .3), that-day concentration flag (.6), wash circular score, pump pattern (.7). |
| **counterparty** (.25) | Collusion proxy: **binomial surprise z** of fund-vs-broker pairing frequency against the broker's market share (z/4, ≥3 fills); market-flagged counterparty (.6, ≥2 fills); **exit-liquidity** — fund bought while the counterparty was unwinding an accumulated position (.7, from `broker_flow_daily` cumulative). |
| **cross** (.15) | Intra-firm wash: opposite fills across the firm's books within 5 min (1.0); same-fund same-day buy+sell churn (.5). |
| **outcome** (.15) | **Markouts** — post-trade drift at T+1/5/20 in trading days, signed so negative = adverse ("we bought, it fell"), in sigmas; bought in the top decile of the 20-day range (.5). |

`flag_reasons` lists which checks fired, in plain language.

## 5. Market-context intelligence (per concentration case)

Computed at case-build time from `broker_flow_daily`
(`surveillance_cases._market_context`):

- **Historical participation** — broker's buy/sell/total volume share over the previous
  **30 and 90 trading days** (trade date excluded), with data-depth reported.
- **Trade-date participation** — share of all market volume, buy/sell split, **volume rank
  among all brokers**, and a *dominant* flag (≥25% share or rank ≤2).
- **Positioning trend** — 7/30-day net qty → **accumulating / distributing / balanced**
  (net ≥ ±25% of gross).

**Classification** (`_classify_concentration`), with
`ratio = fund_share / max(day_share, hist_30d)`:

| Verdict | Rule |
|---|---|
| **Likely Normal Market Behavior** | broker dominant that day and ratio ≤ 2.5×, or ratio low overall |
| **Elevated Concentration** | ratio ≥ 2× or z ≥ 3, but not extreme |
| **Potentially Exceptional Concentration** | ratio ≥ 4× **and** z ≥ 3 |

Confidence (0.30–0.95) scales with history depth, fill count, and how clear-cut the ratio
is. A templated rationale explains the verdict; the classification is part of the
explanation-cache signature so notes regenerate when the verdict changes.

**Verified live:** MNBBL×Ashutosh (z=3.6) demoted to LIKELY NORMAL — the broker was rank #1
with 27.9% of all market volume that day (it *was* the liquidity). NMB×ABC Securities
(76.2% of our flow vs 4.1% market share, 8.5×) and MEN×Online Securities (71.9% vs 3.6%,
10.1×) → POTENTIALLY EXCEPTIONAL.

## 6. Investigation cases + LLM case notes

Flagged fills (score ≥ 25) are **grouped into cases** = fund × scrip × day fill-clusters
(`surveillance_cases.build_cases`), each carrying: score/tier, pattern headline,
counterparty roll-up (named via the broker map), concentration meter (observed vs
expected), **D+0→D+5 markout curve** (from daily bars), the fill cluster, market context,
classification, and the **LLM case note**.

**Case notes** (`generate_explanations`):
- Written by the synthesizer LLM with a **domain glossary system prompt** (interval VWAP,
  markout, surprise z, exit liquidity, cross/churn, market context, classification) and
  strict rules: 3–5 sentences, concrete numbers, observed-vs-expected, **must state whether
  the concentration is market-supported or exceptional**, never an accusation, ends with
  what the desk should confirm.
- **Cached** in `surveillance_explanations` keyed by a **signature** =
  md5(score | flag_reasons | n_fills | classification). One LLM call per case per material
  change — shared across all users/sessions. Regenerates only when the case actually
  changes (markouts maturing, new history matching fills, flags appearing, classification
  flipping). Timestamps deliberately NOT in the signature.
- **Lazy generation**: the frontend requests notes only for the case_keys **visible on the
  current page** (5 cases/page), once per case per browser session, hard-capped 10/call —
  300 MODERATE cases cost exactly the pages someone actually reads.

## 7. Findings & per-case analyst chat

- **`surveillance_case_responses`** — human findings on a case (read-only list on the
  card). Findings are injected into the note prompt as *analyst ground truth*: a resolved
  case regenerates reading as resolved.
- **Per-case floating chat** (`surveillance_case_chat` + SSE
  `POST /api/surveillance/cases/{key}/chat/stream`): "Discuss case" on each card opens a
  clippy-style panel scoped to that case. The agent's system prompt is pre-loaded with the
  full case dossier (`case_context_block` → `surveillance_case_block` branch in
  `agent.py`) + glossary + surveillance-analyst persona, and keeps the full research tool
  set. Every turn persists — reopening restores the thread.
- **"Save finding"** distills the chat thread (LLM) into a 1–3 sentence conclusion →
  recorded in `surveillance_case_responses` (`[from case chat]` prefix) → shows on the
  card and feeds future note regenerations. The loop: screen flags → human investigates in
  chat → saves conclusion → the screen's own note absorbs it.

## 8. The board (`/surveillance`)

Investigation-first design (per the UI-REVAMP mock):
- **Triage strip** — donut of cases needing review, "N of M fills", session range, severity
  dots, flagged notional (lakh/Cr), funds monitored (distinct *names*), clean rate, scan
  freshness.
- **Case cards** — severity rail + pill + dashed **classification chip**
  (LIKELY NORMAL / ELEVATED CONC. / EXCEPTIONAL · confidence%), risk-score gauge,
  expandable: trade-facts strip → LLM note (tinted callout) → evidence grid (concentration
  meter with expected-marker, markout curve SVG, fill cluster, **broker market context
  tile**) → recorded findings → tags + *Open scrip* / *Discuss case*.
- **Clean book** — LOW fills collapse to one line, expandable.
- Severity filter chips; 5 cases/page pagination.

## 9. API surface

| Endpoint | Purpose |
|---|---|
| `GET /api/surveillance/cases?min_score=&from_date=&to_date=` | grouped investigation cases (full dossier); optional session-window filter |
| `POST /api/surveillance/explain` `{case_keys}` | lazy LLM note generation (visible page only) |
| `GET /api/surveillance/summary?from_date=&to_date=` | triage-strip stats over the window; always returns unfiltered `book_first/last_date`, `book_n_sessions`, `book_sessions` for the UI pickers |
| `GET /api/surveillance/trades?…&from_date=&to_date=` | raw per-fill rows (broker names joined) |
| `GET /api/pipeline/tradebook-files` | lists the xlsx drop folder (`NRC_INTERNAL_TRADES_DIR`) the board will ingest |
| `POST /api/pipeline/refresh {jobs:["tradebook_job"]}` | one-click trade-book reload (see §10) |
| `GET /api/surveillance/counterparties` | repeat-counterparty patterns by surprise z |
| `POST /api/surveillance/cases/{key}/responses` | record a finding |
| `GET/POST /api/surveillance/cases/{key}/chat[/stream]` | persistent per-case chat (SSE) |
| `POST /api/surveillance/cases/{key}/chat/save-finding` | distill chat → finding |

Agent tools (copilot): `get_internal_surveillance`, `get_counterparty_exposure`.

## 10. Operations — the things that MUST keep running

- **SMTM floorsheet is session-only.** Verified 2026-06-12: date params silently ignored,
  no history endpoints (404), JWT scope `live-data` only. Each session *replaces* the
  last — **a missed trading day's floorsheet is unrecoverable**.
- Therefore **`floorsheet_schedule` is RUNNING by default** (the only auto-started
  schedule): `floorsheet_job` at **15:30 NPT Sun–Thu** pulls the session, rebuilds broker
  gold + internal surveillance, syncs serving tables. The Dagster daemon must be up at that
  time — strongest argument for moving Dagster to an always-on box.
- `floorsheet_job` also re-ingests the trade-book xlsx drop
  (`NRC_INTERNAL_TRADES_DIR`, default sibling `internal-trade-data/`), so the CEO board
  refreshes the same evening.
- **On-demand reload — `tradebook_job`** (added 2026-06-12): drop new
  `Trade_Book_Details*.xlsx` into the folder and click **"Load new trade-book data"** on
  `/surveillance`. Runs bronze ingest → silver → the 4 internal dbt models → Postgres
  sync, *without* touching the SMTM floorsheet (works at any hour, no live-API risk;
  the inline index refresh is skipped too). The button shows the drop-folder file count
  (`/api/pipeline/tradebook-files`), polls run status, and refreshes the board on
  success. Requires `dagster dev` (port 3001) to be up. Idempotent — the whole folder
  re-ingests and Silver dedups.
- **Session-window filter** (added 2026-06-12): the board's date-range picker (+ presets
  All / Latest session / Last 5 sessions) filters triage stats, cases, and the clean book
  server-side via `from_date`/`to_date`; case_keys are unchanged so cached LLM notes
  still match.
- **Broker code → name map**: 92 brokers (codes 1–101) seeded from
  hamroshare.com.np/nepse/brokers in `015_brokers.sql` (idempotent upsert). The fund's own
  broker: **#65 = Sharepro Securities**.

## 11. Real findings from the first data (June 2026, ~559 fills)

| Case | Signal | Verdict |
|---|---|---|
| NMB buys vs **ABC Securities** | 76.2% of our flow vs 4.1% market share, z=6.3; broker was distributing (net −7,151) — we bought into their unwind | **Potentially Exceptional** |
| MEN sells vs **Online Securities** | 71.9% of our flow vs 3.6% market share, z=6.4; broker is a minor participant historically | **Potentially Exceptional** |
| MNBBL buys vs **Ashutosh Brokerage** | 57.7% of flow, z=3.6 — but broker was **rank #1 with 27.9% of all market volume** that day | **Likely Normal** (liquidity) |
| MBL buys vs **South Asian Bulls** | 14.3% of flow; broker was rank #2 seller that day | **Likely Normal** |
| Execution quality overall | fills ≈ at VWAP, zero outside-range; avg 5-day markout +1.4% | clean |
| Intra-firm crosses | none within 5 minutes | clean |

## 12. Open items / data-asks

1. **SMTM bulk floorsheet backfill** (or `historical` API scope) — single biggest accuracy
   unlock; back-fills VWAP benchmarks, counterparty baselines, markouts across the whole
   internal history. (They store it — their docs show Aug-2024 samples.)
2. **OMS order-level data** — order placement timestamps, limit prices, modifications →
   implementation shortfall + true front-running detection.
3. **Ongoing daily trade-book feed** + months of internal history → reliable per-fund
   baselines.
4. **Account → scheme reference sheet** (one scheme arrives under multiple client codes).
5. Scheme holdings/NAV (churn vs AUM), approved-list per scheme, employee/related-party
   broker declarations.
6. Pending build items: scrip-page `tab-internal`, threshold calibration with the desk.

## 13. Email alerts on new cases (added 2026-06-12)

- `evaluate_internal_surv` in `nrc_processing.speculation_alerts` detects cases
  (fund × scrip × day, score ≥ 25, last 21 sessions — the window lets old cases age out
  of `alert_dispatch_log` without ever re-alerting) and feeds them into `detect_all()`
  as `alert_type="surv"`. Severity maps from the tier (HIGH→critical, ELEVATED→elevated,
  MODERATE→watch); the dominant counterparty + share-of-our-flow ride in broker /
  volume_share; fund/tier/date ride in `tags`.
- **Dedicated email** (`render_internal_urgent` in nrc_notifications): "🔎 N new internal
  trade cases flagged" — per-case card with fund, counterparty share bar, flag chips,
  score, CTA → `/surveillance`. Separate from the market-manipulation email so they can
  be routed/filtered apart. **Incremental-only** — surv is excluded from the daily digest
  (cases never clear day-to-day; a digest would repeat them forever).
- Dedup via the existing `alert_dispatch_log` reconcile: each case_key emails exactly once.
- **Triggers**: (1) the alerts background loop (15-min incremental during session);
  (2) a **post-close incremental pass at 15:45 NPT** right before the digest — so cases
  from the 15:30 floorsheet/trade-book load email the same evening; (3) the
  **"Load new trade-book data" button** fires `POST /api/alerts/run?mode=incremental`
  after a successful pipeline run, so a manual drop alerts immediately at any hour.
- `/alerts` board shows them under the "Internal trade" type chip.

---
*Maintained alongside the plan file; signature-cached LLM notes mean re-running pipelines
is always safe and never re-bills generation unless a case materially changed.*
