"use client";

// The design's Market-Intelligence "Research view" panels, wired to real data:
//   IndexStrip (NEPSE + breadth + sub-indices) · BrokerFlowPanel ·
//   NewsTimeline · AlertsFeed · CorrelationNetwork.

import Link from "next/link";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type IndexRow, type PulseScore, type MarketNewsItem } from "@/lib/api";
import { Spark, ImpactDot, Network, flagColor, deriveFlag, npr, type NetData } from "@/components/viz";

/* ---------- shared panel chrome ---------- */
function Panel({ title, eyebrow, right, children, pad = true }: { title: string; eyebrow?: string; right?: React.ReactNode; children: React.ReactNode; pad?: boolean }) {
  return (
    <div className="panel overflow-hidden">
      <div className="flex items-start justify-between gap-3 px-4 py-3" style={{ borderBottom: "1px solid var(--line)" }}>
        <div>
          <h3 className="text-[12.5px] font-semibold uppercase tracking-wider text-fg">{title}</h3>
          {eyebrow && <p className="mt-0.5 text-[11px] text-fg-muted">{eyebrow}</p>}
        </div>
        {right}
      </div>
      <div style={{ padding: pad ? 16 : 0 }}>{children}</div>
    </div>
  );
}

function timeAgo(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso).getTime();
  if (isNaN(d)) return "";
  const mins = Math.floor((Date.now() - d) / 60000);
  if (mins < 1) return "now";
  if (mins < 60) return `${mins}m`;
  if (mins < 1440) return `${Math.floor(mins / 60)}h`;
  return `${Math.floor(mins / 1440)}d`;
}

/* ============================================================ Index strip */
export function IndexStrip() {
  const indices = useQuery({ queryKey: ["indices"], queryFn: api.indices });
  const universe = useQuery({ queryKey: ["universe"], queryFn: api.universe });

  const rows = indices.data ?? [];
  const nepse = rows.find((r) => /nepse/i.test(r.index_name)) ?? rows[0] ?? null;
  const subs = rows.filter((r) => r !== nepse);
  const turnover = nepse?.turnover ?? rows.find((r) => r.turnover != null)?.turnover ?? null;

  const u = universe.data ?? [];
  const adv = u.filter((r) => (r.change_pct ?? 0) > 0).length;
  const dec = u.filter((r) => (r.change_pct ?? 0) < 0).length;
  const unch = u.filter((r) => (r.change_pct ?? 0) === 0).length;

  return (
    <div className="panel" style={{ padding: 18 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 0, flexWrap: "wrap" }}>
        {/* NEPSE */}
        <div style={{ display: "flex", alignItems: "center", gap: 18, paddingRight: 22, borderRight: "1px solid var(--line)" }}>
          <div>
            <div className="eyebrow">{nepse?.index_name ?? "NEPSE Index"}</div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
              <span className="display tnum" style={{ fontSize: 32, fontWeight: 700, letterSpacing: "-.02em" }}>{nepse ? npr(nepse.close, 2) : "—"}</span>
              {nepse?.percent_change != null && (
                <span className="mono" style={{ fontSize: 14, color: nepse.percent_change >= 0 ? "var(--pos)" : "var(--neg)" }}>
                  {nepse.percent_change >= 0 ? "▲" : "▼"} {npr(Math.abs(nepse.change ?? 0), 2)} ({nepse.percent_change.toFixed(2)}%)
                </span>
              )}
            </div>
          </div>
        </div>
        {/* Turnover + breadth */}
        <div style={{ display: "flex", alignItems: "center", gap: 26, padding: "0 22px" }}>
          <div>
            <div className="eyebrow">Turnover</div>
            <div className="mono tnum" style={{ fontSize: 16, fontWeight: 600, marginTop: 4 }}>{turnover != null ? `Rs ${npr(turnover / 1e9, 2)}B` : "—"}</div>
          </div>
          <div>
            <div className="eyebrow">Breadth</div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 4 }}>
              <span className="mono" style={{ fontSize: 14, color: "var(--pos)" }}>▲{adv}</span>
              <span className="mono" style={{ fontSize: 14, color: "var(--neg)" }}>▼{dec}</span>
              <span className="mono" style={{ fontSize: 13, color: "var(--ink-3)" }}>={unch}</span>
            </div>
          </div>
        </div>
        <div style={{ flex: 1 }} />
        {/* Sub-indices */}
        <div style={{ display: "flex", alignItems: "center", gap: 7, paddingLeft: 18, flexWrap: "wrap" }}>
          {subs.slice(0, 8).map((s) => (
            <div key={s.index_name} style={{ padding: "6px 11px", borderRadius: 9, background: "var(--panel-2)", border: "1px solid var(--line-soft)" }}>
              <div style={{ fontSize: 10.5, color: "var(--ink-3)" }}>{s.index_name}</div>
              <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                <span className="mono tnum" style={{ fontSize: 12.5 }}>{npr(s.close, 1)}</span>
                {s.percent_change != null && (
                  <span className="mono" style={{ fontSize: 10.5, color: s.percent_change >= 0 ? "var(--pos)" : "var(--neg)" }}>
                    {s.percent_change >= 0 ? "+" : ""}{s.percent_change.toFixed(1)}%
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ================================================= Market sentiment breadth */
export function SentimentBreadth() {
  const q = useQuery({ queryKey: ["market-pulse"], queryFn: api.marketPulse });
  const d = q.data;
  const total = d ? d.sentiment_bullish + d.sentiment_neutral + d.sentiment_bearish : 0;
  const pct = (n: number) => (total > 0 ? (n / total) * 100 : 0);
  return (
    <Panel title="Market Sentiment" eyebrow="live news · all sectors">
      {q.isLoading || !d ? (
        <Loading />
      ) : (
        <>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
            <span className="display tnum" style={{ fontSize: 28, fontWeight: 700, color: (d.sentiment_avg ?? 0) > 0 ? "var(--pos)" : (d.sentiment_avg ?? 0) < 0 ? "var(--neg)" : "var(--ink)" }}>
              {d.sentiment_avg != null ? `${d.sentiment_avg >= 0 ? "+" : ""}${d.sentiment_avg.toFixed(2)}` : "—"}
            </span>
            <span className="eyebrow">avg score</span>
          </div>
          <div style={{ display: "flex", height: 10, borderRadius: 99, overflow: "hidden", marginTop: 10, border: "1px solid var(--line)" }}>
            <div style={{ width: `${pct(d.sentiment_bullish)}%`, background: "var(--pos)" }} />
            <div style={{ width: `${pct(d.sentiment_neutral)}%`, background: "var(--ink-3)" }} />
            <div style={{ width: `${pct(d.sentiment_bearish)}%`, background: "var(--neg)" }} />
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 7, fontSize: 11 }}>
            <span style={{ color: "var(--pos)" }}>{d.sentiment_bullish} bullish</span>
            <span style={{ color: "var(--ink-3)" }}>{d.sentiment_neutral} neutral</span>
            <span style={{ color: "var(--neg)" }}>{d.sentiment_bearish} bearish</span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginTop: 16 }}>
            <Movers title="Most bullish" items={d.bullish_movers.slice(0, 4)} pos />
            <Movers title="Most bearish" items={d.bearish_movers.slice(0, 4)} />
          </div>
        </>
      )}
    </Panel>
  );
}

function Movers({ title, items, pos }: { title: string; items: PulseScore[]; pos?: boolean }) {
  return (
    <div>
      <div className="eyebrow" style={{ marginBottom: 8 }}>{title}</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {items.map((it) => (
          <Link key={it.scrip} href={`/scrip/${it.scrip}#news`} className="flex items-center justify-between text-[12px]">
            <span className="mono font-semibold text-fg">{it.scrip}</span>
            <span className="mono tnum" style={{ color: pos ? "var(--pos)" : "var(--neg)" }}>{it.value != null ? `${it.value >= 0 ? "+" : ""}${it.value.toFixed(2)}` : "—"}</span>
          </Link>
        ))}
        {items.length === 0 && <span style={{ fontSize: 11, color: "var(--ink-3)" }}>—</span>}
      </div>
    </div>
  );
}

/* ============================================== Broker accumulation panel */
export function BrokerFlowPanel() {
  const q = useQuery({ queryKey: ["market-pulse"], queryFn: api.marketPulse });
  const rows = q.data?.broker_accumulation ?? [];
  const max = Math.max(0.0001, ...rows.map((r) => r.value ?? 0));
  return (
    <Panel title="Broker Accumulation" eyebrow="single-broker volume share · flagged names">
      {q.isLoading ? (
        <Loading />
      ) : rows.length === 0 ? (
        <Empty msg="No flagged accumulation." />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
          {rows.map((r) => (
            <Link key={r.scrip} href={`/scrip/${r.scrip}#floorsheet`} className="grid items-center gap-3" style={{ gridTemplateColumns: "92px 1fr 48px" }}>
              <div className="min-w-0">
                <div className="mono text-[12px] font-semibold text-fg">{r.scrip}</div>
                <div className="truncate text-[9.5px] text-fg-dim">{r.extra}</div>
              </div>
              <div style={{ height: 9, borderRadius: 6, background: "var(--line)", overflow: "hidden" }}>
                <div style={{ width: `${((r.value ?? 0) / max) * 100}%`, height: "100%", background: "var(--pos)", opacity: 0.82 }} />
              </div>
              <span className="mono tnum text-right text-[12px]" style={{ color: "var(--pos)" }}>{r.value != null ? `${(r.value * 100).toFixed(0)}%` : "—"}</span>
            </Link>
          ))}
        </div>
      )}
    </Panel>
  );
}

/* ================================================= News impact timeline */
export function NewsTimeline() {
  const q = useQuery({ queryKey: ["market-news"], queryFn: () => api.marketNews(16) });
  const items = q.data ?? [];
  const sentOf = (n: MarketNewsItem): "pos" | "neg" | "neu" =>
    n.sentiment === "BULLISH" ? "pos" : n.sentiment === "BEARISH" ? "neg" : "neu";
  const impactColor = (n: MarketNewsItem) => {
    const a = Math.abs(n.sentiment_score ?? 0);
    return a >= 0.5 ? "var(--neg)" : a >= 0.2 ? "var(--warn)" : "var(--ink-3)";
  };
  const impactLabel = (n: MarketNewsItem) => {
    const a = Math.abs(n.sentiment_score ?? 0);
    return a >= 0.5 ? "high" : a >= 0.2 ? "med" : "low";
  };
  return (
    <Panel title="News Impact Timeline" eyebrow="market-moving headlines · all sectors">
      {q.isLoading ? (
        <Loading />
      ) : items.length === 0 ? (
        <Empty msg="No news yet — the live feed fills in as it runs." />
      ) : (
        <div style={{ position: "relative", paddingLeft: 16, maxHeight: 420, overflowY: "auto" }}>
          <div style={{ position: "absolute", left: 3.5, top: 4, bottom: 4, width: 1, background: "var(--line)" }} />
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {items.map((n, i) => (
              <a key={i} href={n.url} target="_blank" rel="noopener noreferrer" style={{ position: "relative", textDecoration: "none", color: "inherit", display: "block" }}>
                <span style={{ position: "absolute", left: -16, top: 4 }}><ImpactDot sent={sentOf(n)} /></span>
                <div style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
                  <span className="mono" style={{ fontSize: 10, color: "var(--ink-3)" }}>{timeAgo(n.published_at)}</span>
                  <span className="mono" style={{ fontSize: 9, color: impactColor(n), textTransform: "uppercase", letterSpacing: ".06em" }}>{impactLabel(n)} impact</span>
                </div>
                <div style={{ fontSize: 12.5, fontWeight: 500, marginTop: 2, lineHeight: 1.4 }}>{n.title}</div>
                {n.summary && n.summary !== n.title && <div style={{ fontSize: 11, color: "var(--ink-2)", marginTop: 3, lineHeight: 1.45 }}>{n.summary}</div>}
                <div style={{ display: "flex", gap: 5, marginTop: 6, flexWrap: "wrap" }}>
                  {n.source && <span className="mono" style={{ fontSize: 9.5, color: "var(--ink-3)" }}>{n.source}</span>}
                  {(n.scrip_tags ?? []).slice(0, 4).map((t, j) => <span key={j} className="mono" style={{ fontSize: 9.5, color: "var(--accent)" }}>· {t}</span>)}
                </div>
              </a>
            ))}
          </div>
        </div>
      )}
    </Panel>
  );
}

/* =========================================== Pattern & manipulation alerts */
export function AlertsFeed() {
  const q = useQuery({ queryKey: ["market-pulse"], queryFn: api.marketPulse });
  const alerts = q.data?.speculation_alerts ?? [];
  const sevColor = (tier: string | null) => (tier === "HIGH" ? "var(--neg)" : tier === "ELEVATED" ? "var(--warn)" : "var(--info)");
  return (
    <Panel title="Pattern & Manipulation Alerts" eyebrow="floor-sheet surveillance engine">
      {q.isLoading ? (
        <Loading />
      ) : alerts.length === 0 ? (
        <Empty msg="No elevated names." />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
          {alerts.map((a: PulseScore) => {
            const c = sevColor(a.tier);
            return (
              <Link
                key={a.scrip}
                href={`/scrip/${a.scrip}#floorsheet`}
                style={{ display: "flex", gap: 11, padding: "10px 12px", borderRadius: 10, background: "var(--panel-2)", border: "1px solid var(--line-soft)", borderLeft: `3px solid ${c}`, textDecoration: "none", color: "inherit" }}
              >
                <div style={{ flexShrink: 0, paddingTop: 1 }}>
                  <span className="mono" style={{ fontSize: 12, fontWeight: 700, color: c }}>{a.scrip}</span>
                </div>
                <div style={{ minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 12.5, fontWeight: 600 }}>Speculation risk</span>
                    <span className="mono" style={{ fontSize: 9.5, color: c, textTransform: "uppercase", letterSpacing: ".06em" }}>{a.tier}</span>
                  </div>
                  <div style={{ fontSize: 11.5, color: "var(--ink-2)", marginTop: 2, lineHeight: 1.45 }}>
                    {a.sector ?? "—"} · score {a.value != null ? a.value.toFixed(1) : "—"}/100 — concentration / circular-trade / block-trade signals
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </Panel>
  );
}

/* ============================================= Correlation network (co-movement) */
function pearson(a: number[], b: number[]): number {
  const n = Math.min(a.length, b.length);
  if (n < 5) return 0;
  let sa = 0, sb = 0;
  for (let i = 0; i < n; i++) { sa += a[i]; sb += b[i]; }
  const ma = sa / n, mb = sb / n;
  let num = 0, da = 0, db = 0;
  for (let i = 0; i < n; i++) {
    const xa = a[i] - ma, xb = b[i] - mb;
    num += xa * xb; da += xa * xa; db += xb * xb;
  }
  const den = Math.sqrt(da * db);
  return den === 0 ? 0 : num / den;
}
function toReturns(series: number[]): number[] {
  const r: number[] = [];
  for (let i = 1; i < series.length; i++) r.push(series[i - 1] ? (series[i] - series[i - 1]) / series[i - 1] : 0);
  return r;
}

export function CorrelationNetwork() {
  const universe = useQuery({ queryKey: ["universe"], queryFn: api.universe });
  const sparks = useQuery({ queryKey: ["universe-sparklines", 30], queryFn: () => api.universeSparklines(30) });

  const net: NetData = useMemo(() => {
    const u = universe.data ?? [];
    const sp = sparks.data ?? {};
    // top scrips by conviction score that actually have a sparkline
    const top = [...u]
      .filter((r) => (sp[r.scrip]?.length ?? 0) > 6)
      .sort((a, b) => (b.scorecard_0_100 ?? b.quality_score_0_100 ?? 0) - (a.scorecard_0_100 ?? a.quality_score_0_100 ?? 0))
      .slice(0, 14);
    const rets: Record<string, number[]> = {};
    top.forEach((r) => (rets[r.scrip] = toReturns(sp[r.scrip])));
    const edges: [string, string, number][] = [];
    for (let i = 0; i < top.length; i++) {
      for (let j = i + 1; j < top.length; j++) {
        const c = pearson(rets[top[i].scrip], rets[top[j].scrip]);
        if (Math.abs(c) >= 0.55) edges.push([top[i].scrip, top[j].scrip, Math.min(1, Math.abs(c))]);
      }
    }
    const nodes = top.map((r) => {
      const score = Math.round(r.scorecard_0_100 ?? r.quality_score_0_100 ?? 50);
      return { id: r.scrip, sector: r.sector, score, flag: deriveFlag(score, r.change_pct) };
    });
    return { nodes, edges };
  }, [universe.data, sparks.data]);

  return (
    <Panel title="Correlation Network" eyebrow="co-movement clusters · 30d returns" right={<span className="mono" style={{ fontSize: 9.5, color: "var(--ink-3)" }}>size = conviction</span>}>
      {universe.isLoading || sparks.isLoading ? (
        <Loading />
      ) : net.nodes.length === 0 ? (
        <Empty msg="Not enough price history yet." />
      ) : (
        <>
          <Network data={net} />
          <div style={{ display: "flex", gap: 14, justifyContent: "center", marginTop: 6 }}>
            {([["green", "Green flag"], ["amber", "Watch"], ["red", "Red flag"]] as const).map(([f, l]) => (
              <span key={f} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10.5, color: "var(--ink-3)" }}>
                <span style={{ width: 8, height: 8, borderRadius: 99, background: flagColor(f) }} />
                {l}
              </span>
            ))}
          </div>
        </>
      )}
    </Panel>
  );
}

/* ---------- shared states ---------- */
function Empty({ msg }: { msg: string }) {
  return <div className="py-6 text-center text-[12px] text-fg-muted">{msg}</div>;
}
function Loading() {
  return <div className="space-y-2">{[0, 1, 2].map((i) => <div key={i} className="h-4 rounded bg-bg-hover animate-pulse" style={{ width: `${80 - i * 12}%` }} />)}</div>;
}

// re-export so the dashboard can keep the sentiment + movers mini-cards too
export { Spark };
