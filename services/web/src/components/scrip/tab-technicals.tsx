"use client";

// Technicals tab renders the 5 rule votes (r1_trend..r5_bollinger) as a
// pass/fail grid with a neutral "Technical posture: N of 5 bullish" framing.
// We deliberately hide the BUY/SELL technical_signal label per the
// "data not verdicts" directive.

import { useQuery } from "@tanstack/react-query";
import { Check, X, Minus } from "lucide-react";
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine,
} from "recharts";
import { api } from "@/lib/api";
import {
  Panel, MetricCell, EmptyState, LoadingState,
} from "./primitives";

const RULES: Array<{ key: "r1_trend" | "r2_ma_align" | "r3_rsi" | "r4_macd" | "r5_bollinger"; label: string; hint: string }> = [
  { key: "r1_trend",     label: "Trend",        hint: "Price above SMA 200" },
  { key: "r2_ma_align",  label: "MA alignment", hint: "SMA 20 > SMA 50 > SMA 200" },
  { key: "r3_rsi",       label: "RSI",          hint: "RSI between 40 and 70" },
  { key: "r4_macd",      label: "MACD",         hint: "MACD above signal line" },
  { key: "r5_bollinger", label: "Bollinger",    hint: "Price above middle band" },
];

export function TabTechnicals({ scrip }: { scrip: string }) {
  const snap = useQuery({ queryKey: ["technicals", scrip], queryFn: () => api.scrip.technicals(scrip) });
  const prices = useQuery({ queryKey: ["prices", scrip, 180], queryFn: () => api.prices(scrip, 180) });

  const t = snap.data;
  const votes = t ? RULES.map((r) => t[r.key]) : [];
  const bullish = votes.filter((v) => v === 1).length;
  const available = votes.filter((v) => v !== null && v !== undefined).length;

  return (
    <div className="grid grid-cols-12 gap-4">
      <Panel
        title="Technical posture"
        hint="5-rule checklist — bullish when rule passes"
        className="col-span-12"
        right={
          t ? (
            <div className="text-[12px] font-semibold text-fg-muted">
              <span className="num text-[16px] text-fg">{bullish}</span> of {available} bullish
            </div>
          ) : null
        }
      >
        {snap.isLoading ? (
          <LoadingState rows={2} />
        ) : !t ? (
          <EmptyState message="No technical signal data." />
        ) : (
          <div className="grid grid-cols-5 gap-3">
            {RULES.map((r) => {
              const v = t[r.key];
              const pass = v === 1;
              const fail = v === 0;
              return (
                <div key={r.key} className="rounded-lg border border-border-subtle px-3 py-2.5 flex items-center gap-2.5">
                  <div className={`flex h-7 w-7 items-center justify-center rounded-md ${pass ? "bg-ok/15 text-ok" : fail ? "bg-err/10 text-err" : "bg-bg-hover text-fg-dim"}`}>
                    {pass ? <Check className="h-3.5 w-3.5" strokeWidth={2.5} /> : fail ? <X className="h-3.5 w-3.5" strokeWidth={2.5} /> : <Minus className="h-3.5 w-3.5" />}
                  </div>
                  <div className="min-w-0">
                    <div className="text-[12px] font-semibold text-fg">{r.label}</div>
                    <div className="text-[10.5px] text-fg-muted truncate">{r.hint}</div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Panel>

      <Panel title="Indicator snapshot" className="col-span-6">
        {snap.isLoading ? <LoadingState rows={3} /> : !t ? <EmptyState message="—" /> : (
          <div className="grid grid-cols-3 gap-4">
            <MetricCell label="Close" value={t.close?.toFixed(2) ?? "—"} />
            <MetricCell label="SMA 20"  value={t.sma_20?.toFixed(2) ?? "—"} />
            <MetricCell label="SMA 50"  value={t.sma_50?.toFixed(2) ?? "—"} />
            <MetricCell label="SMA 200" value={t.sma_200?.toFixed(2) ?? "—"} />
            <MetricCell label="RSI 14"  value={t.rsi_14?.toFixed(1) ?? "—"} tone={t.rsi_14 !== null && t.rsi_14 !== undefined ? (t.rsi_14 > 70 ? "warn" : t.rsi_14 < 30 ? "warn" : "default") : "default"} />
            <MetricCell label="MACD"    value={t.macd?.toFixed(2) ?? "—"} />
          </div>
        )}
      </Panel>

      <Panel title="Price with SMA 20 / 50 / 200" className="col-span-6">
        {prices.isLoading ? (
          <LoadingState rows={4} />
        ) : !prices.data?.length || !t ? (
          <EmptyState message="—" />
        ) : (
          <div className="h-[200px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={prices.data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="var(--border-subtle)" vertical={false} />
                <XAxis dataKey="date" hide />
                <YAxis tick={{ fontSize: 10, fill: "var(--fg-muted)" }} tickLine={false} axisLine={false} width={44} />
                <Tooltip contentStyle={{ background: "var(--bg-panel)", border: "1px solid var(--border)", borderRadius: 6, fontSize: 11 }} />
                {t.sma_20  !== null && <ReferenceLine y={t.sma_20}  stroke="var(--fg-muted)" strokeDasharray="2 3" strokeWidth={1} />}
                {t.sma_50  !== null && <ReferenceLine y={t.sma_50}  stroke="var(--fg-dim)" strokeDasharray="2 3" strokeWidth={1} />}
                {t.sma_200 !== null && <ReferenceLine y={t.sma_200} stroke="var(--warn)" strokeDasharray="4 2" strokeWidth={1} />}
                <Line type="monotone" dataKey="close" stroke="var(--fg)" strokeWidth={1.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </Panel>
    </div>
  );
}
