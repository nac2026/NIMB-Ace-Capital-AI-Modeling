"use client";

import { useQuery } from "@tanstack/react-query";
import { api, type NewsItem } from "@/lib/api";
import { EmptyState, LoadingState } from "./primitives";

function timeAgo(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso).getTime();
  if (isNaN(d)) return "";
  const mins = Math.floor((Date.now() - d) / 60000);
  if (mins < 60) return `${mins}m ago`;
  if (mins < 1440) return `${Math.floor(mins / 60)}h ago`;
  return `${Math.floor(mins / 1440)}d ago`;
}

function tone(a: NewsItem): "bull" | "bear" | "neutral" {
  if (a.sentiment === "BULLISH") return "bull";
  if (a.sentiment === "BEARISH") return "bear";
  return "neutral";
}

export function TabNewsSentiment({ scrip }: { scrip: string }) {
  const q = useQuery({
    queryKey: ["news-sentiment", scrip],
    queryFn: () => api.scrip.newsSentiment(scrip),
  });
  const d = q.data;

  if (q.isLoading) return <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap)" }}><LoadingState rows={3} /></div>;
  if (!d || d.n_articles === 0) {
    return <EmptyState message="No recent news for this stock yet — the live feed fills in as it runs." />;
  }

  const articles = d.articles ?? [];
  const bull = articles.filter((a) => tone(a) === "bull");
  const bear = articles.filter((a) => tone(a) === "bear");
  const neutral = articles.filter((a) => tone(a) === "neutral");
  const nb = bull.length,
    nbr = bear.length;
  const bullPct = Math.round((nb / (nb + nbr || 1)) * 100);
  const netLabel = bullPct >= 55 ? "Positive" : bullPct <= 40 ? "Negative" : "Mixed";
  const netColor = bullPct >= 55 ? "var(--pos)" : bullPct <= 40 ? "var(--neg)" : "var(--warn)";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap)" }}>
      {/* sentiment header */}
      <div className="panel" style={{ background: "var(--panel-2)", padding: 20 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 18, flexWrap: "wrap" }}>
          <div style={{ flex: 1, minWidth: 240 }}>
            <div style={{ marginBottom: 12 }}>
              <h3 className="serif" style={{ margin: 0, fontSize: 19, fontWeight: 600 }}>News sentiment</h3>
              <p style={{ margin: "3px 0 0", fontSize: 12.5, color: "var(--ink-3)" }}>
                Based on {d.n_articles} recent items, weighted by source &amp; recency
              </p>
            </div>
            <div style={{ height: 12, borderRadius: 99, overflow: "hidden", display: "flex", border: "1px solid var(--line)" }}>
              <div style={{ width: `${bullPct}%`, background: "var(--pos)" }} />
              <div style={{ width: `${100 - bullPct}%`, background: "var(--neg)" }} />
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8 }}>
              <span style={{ fontSize: 12, color: "var(--pos)", fontWeight: 600 }}>{bullPct}% Bullish · {nb} items</span>
              <span style={{ fontSize: 12, color: "var(--neg)", fontWeight: 600 }}>{100 - bullPct}% Bearish · {nbr} items</span>
            </div>
          </div>
          <div style={{ textAlign: "center" }}>
            <div className="display" style={{ fontSize: 30, fontWeight: 700, color: netColor }}>{netLabel}</div>
            <div className="eyebrow">net news tone</div>
          </div>
        </div>
      </div>

      {/* bull / bear columns */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--gap)", alignItems: "start" }}>
        <NewsColumn title="Bullish signals" dot="var(--pos)" items={bull} t="bull" empty="No bullish items in the period." />
        <NewsColumn title="Bearish signals" dot="var(--neg)" items={bear} t="bear" empty="No bearish items in the period." />
      </div>

      {neutral.length > 0 && (
        <div>
          <ColHead title="Neutral / informational" dot="var(--ink-3)" />
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            {neutral.map((n, i) => <NewsCard key={i} n={n} t="neutral" />)}
          </div>
        </div>
      )}
    </div>
  );
}

function ColHead({ title, dot }: { title: string; dot: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
      <span style={{ width: 9, height: 9, borderRadius: 99, background: dot }} />
      <h3 className="serif" style={{ margin: 0, fontSize: 18, fontWeight: 600 }}>{title}</h3>
    </div>
  );
}

function NewsColumn({ title, dot, items, t, empty }: { title: string; dot: string; items: NewsItem[]; t: "bull" | "bear" | "neutral"; empty: string }) {
  return (
    <div>
      <ColHead title={title} dot={dot} />
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {items.map((n, i) => <NewsCard key={i} n={n} t={t} />)}
        {items.length === 0 && <div style={{ fontSize: 12.5, color: "var(--ink-3)", padding: 14 }}>{empty}</div>}
      </div>
    </div>
  );
}

function NewsCard({ n, t }: { n: NewsItem; t: "bull" | "bear" | "neutral" }) {
  const c = t === "bull" ? "var(--pos)" : t === "bear" ? "var(--neg)" : "var(--ink-3)";
  return (
    <a
      href={n.url}
      target="_blank"
      rel="noopener noreferrer"
      style={{ display: "block", padding: 14, borderRadius: 12, background: "var(--panel)", border: "1px solid var(--line)", borderLeft: `3px solid ${c}`, textDecoration: "none", color: "inherit" }}
    >
      <div style={{ fontSize: 13.5, fontWeight: 500, lineHeight: 1.45, color: "var(--ink)" }}>{n.title}</div>
      {n.summary && n.summary !== n.title && (
        <div style={{ fontSize: 12, color: "var(--ink-2)", marginTop: 6, lineHeight: 1.5 }}>{n.summary}</div>
      )}
      <div style={{ display: "flex", gap: 8, marginTop: 9, alignItems: "center" }}>
        {n.source && <span className="mono" style={{ fontSize: 10, color: "var(--ink-3)" }}>{n.source}</span>}
        {n.published_at && <span className="mono" style={{ fontSize: 10, color: "var(--ink-4)" }}>· {timeAgo(n.published_at)}</span>}
        {n.event_type && n.event_type !== "other" && <span className="mono" style={{ fontSize: 10, color: "var(--ink-4)" }}>· {n.event_type}</span>}
      </div>
    </a>
  );
}
