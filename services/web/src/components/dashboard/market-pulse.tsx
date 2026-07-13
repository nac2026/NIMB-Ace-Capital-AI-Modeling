"use client";

// Market Pulse — the distinctive live-intel strip: news-sentiment breadth,
// speculation/manipulation alerts, broker accumulation, and sentiment movers.
// This is the "more than generic metrics" layer (broker flow + live news).

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api, type PulseScore } from "@/lib/api";

const TIER_COLOR: Record<string, string> = {
  HIGH: "var(--err)", ELEVATED: "var(--warn)",
  BULLISH: "var(--ok)", BEARISH: "var(--err)", NEUTRAL: "var(--fg-muted)",
};

function pctShare(v: number | null): string {
  return v == null ? "—" : `${(v * 100).toFixed(0)}%`;
}
function score(v: number | null): string {
  return v == null ? "—" : v.toFixed(1);
}
function signed(v: number | null): string {
  return v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(2)}`;
}

export function MarketPulse() {
  const q = useQuery({ queryKey: ["market-pulse"], queryFn: api.marketPulse });
  const d = q.data;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
      {/* Sentiment breadth */}
      <Card title="Market sentiment" hint="live news, all sectors">
        {!d ? <Skeleton /> : (
          <div>
            <div className="flex items-end gap-3">
              <div className="num text-[24px] font-semibold tabular-nums"
                   style={{ color: (d.sentiment_avg ?? 0) > 0 ? "var(--ok)" : (d.sentiment_avg ?? 0) < 0 ? "var(--err)" : "var(--fg)" }}>
                {signed(d.sentiment_avg)}
              </div>
              <div className="mb-0.5 text-[11px] text-fg-muted">avg score</div>
            </div>
            <div className="mt-2 flex h-2 overflow-hidden rounded-full" style={{ background: "var(--bg-hover)" }}>
              <Bar n={d.sentiment_bullish} color="var(--ok)" total={d.sentiment_bullish + d.sentiment_neutral + d.sentiment_bearish} />
              <Bar n={d.sentiment_neutral} color="var(--fg-dim)" total={d.sentiment_bullish + d.sentiment_neutral + d.sentiment_bearish} />
              <Bar n={d.sentiment_bearish} color="var(--err)" total={d.sentiment_bullish + d.sentiment_neutral + d.sentiment_bearish} />
            </div>
            <div className="mt-1.5 flex justify-between text-[11px] text-fg-muted">
              <span style={{ color: "var(--ok)" }}>{d.sentiment_bullish} bullish</span>
              <span>{d.sentiment_neutral} neutral</span>
              <span style={{ color: "var(--err)" }}>{d.sentiment_bearish} bearish</span>
            </div>
          </div>
        )}
      </Card>

      {/* Speculation alerts */}
      <Card title="Speculation alerts" hint="floor-sheet manipulation risk">
        {!d ? <Skeleton /> : <ScoreList items={d.speculation_alerts} render={(it) => score(it.value)} sub={(it) => it.tier} empty="No elevated names." />}
      </Card>

      {/* Broker accumulation */}
      <Card title="Broker accumulation" hint="who's quietly building">
        {!d ? <Skeleton /> : <ScoreList items={d.broker_accumulation} render={(it) => pctShare(it.value)} sub={(it) => it.extra} empty="No flagged accumulation." />}
      </Card>

      {/* Sentiment movers */}
      <Card title="News movers" hint="most bullish / bearish">
        {!d ? <Skeleton /> : (
          <div className="space-y-1">
            {d.bullish_movers.slice(0, 3).map((it) => <MoverRow key={"b" + it.scrip} it={it} />)}
            {d.bearish_movers.slice(0, 2).map((it) => <MoverRow key={"x" + it.scrip} it={it} />)}
            {d.bullish_movers.length === 0 && d.bearish_movers.length === 0 && <Empty msg="No sentiment yet." />}
          </div>
        )}
      </Card>
    </div>
  );
}

function Card({ title, hint, children }: { title: string; hint: string; children: React.ReactNode }) {
  return (
    <div className="panel p-4">
      <div className="mb-2">
        <h3 className="text-[12px] font-semibold uppercase tracking-wider text-fg">{title}</h3>
        <p className="text-[10.5px] text-fg-dim">{hint}</p>
      </div>
      {children}
    </div>
  );
}

function Bar({ n, total, color }: { n: number; total: number; color: string }) {
  const w = total > 0 ? (n / total) * 100 : 0;
  return <div style={{ width: `${w}%`, background: color }} />;
}

function ScoreList({ items, render, sub, empty }: {
  items: PulseScore[]; render: (it: PulseScore) => string; sub: (it: PulseScore) => string | null; empty: string;
}) {
  if (!items.length) return <Empty msg={empty} />;
  return (
    <div className="space-y-1.5">
      {items.slice(0, 5).map((it) => (
        <Link key={it.scrip} href={`/scrip/${it.scrip}#floorsheet`}
              className="flex items-center justify-between gap-2 text-[12.5px] hover:opacity-80">
          <span className="num font-semibold text-fg">{it.scrip}</span>
          <span className="flex items-center gap-1.5">
            <span className="text-[10.5px] text-fg-dim">{sub(it)}</span>
            <span className="num tabular-nums font-medium" style={{ color: it.tier ? TIER_COLOR[it.tier] ?? "var(--fg)" : "var(--fg)" }}>
              {render(it)}
            </span>
          </span>
        </Link>
      ))}
    </div>
  );
}

function MoverRow({ it }: { it: PulseScore }) {
  const c = it.tier ? TIER_COLOR[it.tier] ?? "var(--fg)" : "var(--fg)";
  return (
    <Link href={`/scrip/${it.scrip}#news`} className="flex items-center justify-between text-[12.5px] hover:opacity-80">
      <span className="num font-semibold text-fg">{it.scrip}</span>
      <span className="num tabular-nums" style={{ color: c }}>{signed(it.value)}</span>
    </Link>
  );
}

function Empty({ msg }: { msg: string }) {
  return <div className="py-3 text-center text-[11.5px] text-fg-dim">{msg}</div>;
}
function Skeleton() {
  return <div className="space-y-2">{[0, 1, 2].map((i) => <div key={i} className="h-4 rounded bg-bg-hover animate-pulse" style={{ width: `${80 - i * 12}%` }} />)}</div>;
}
