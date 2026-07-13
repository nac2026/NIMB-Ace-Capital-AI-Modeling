"use client";

/* ============================================================
   viz.tsx — SVG visualization primitives (theme-aware)
   Ported from the "Dark Intelligence Terminal" design (viz.jsx).
   All colors reference CSS vars so they re-skin with the theme.
   ============================================================ */

import { useId, useMemo, useState } from "react";

export type Flag = "green" | "amber" | "red";

const V_POS = "var(--pos)";
const V_NEG = "var(--neg)";
const V_WARN = "var(--warn)";

export function flagColor(f: Flag | string | null | undefined): string {
  return f === "green" ? V_POS : f === "red" ? V_NEG : V_WARN;
}

// Map a 0–100 conviction/quality score (+ optional momentum) onto the
// green / amber / red flag the design uses everywhere.
export function deriveFlag(score: number | null | undefined, changePct?: number | null): Flag {
  const s = score ?? 50;
  if (s >= 62) return "green";
  if (s <= 42) return "red";
  if ((changePct ?? 0) < -1.5) return "red";
  return "amber";
}

export function npr(n: number | null | undefined, d = 0): string {
  if (n === null || n === undefined || !isFinite(n)) return "—";
  return n.toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d });
}

/* ---------- Sparkline / area ---------- */
export function Spark({
  data,
  w = 120,
  h = 36,
  color,
  fill = true,
  strokeW = 1.6,
  fullWidth = false,
}: {
  data: number[];
  w?: number;
  h?: number;
  color?: string;
  fill?: boolean;
  strokeW?: number;
  // When true the SVG fills its container width (height stays fixed) — use
  // inside flex/grid cards so the sparkline never overflows the card.
  fullWidth?: boolean;
}) {
  const id = useId().replace(/:/g, "");
  const { d, area, up } = useMemo(() => {
    if (!data.length) return { d: "", area: "", up: true };
    const min = Math.min(...data),
      max = Math.max(...data),
      rng = max - min || 1;
    const X = (i: number) => (i / (data.length - 1 || 1)) * w;
    const Y = (v: number) => h - ((v - min) / rng) * (h - 4) - 2;
    let dd = `M ${X(0)} ${Y(data[0])}`;
    data.forEach((v, i) => {
      if (i) dd += ` L ${X(i)} ${Y(v)}`;
    });
    const ar = dd + ` L ${w} ${h} L 0 ${h} Z`;
    return { d: dd, area: ar, up: data[data.length - 1] >= data[0] };
  }, [data, w, h]);
  const c = color || (up ? V_POS : V_NEG);
  if (!data.length) return fullWidth ? <div style={{ height: h }} /> : <svg width={w} height={h} />;
  const sizeProps = fullWidth
    ? ({ width: "100%", height: h, viewBox: `0 0 ${w} ${h}`, preserveAspectRatio: "none" } as const)
    : ({ width: w, height: h } as const);
  return (
    <svg {...sizeProps} style={{ display: "block", maxWidth: "100%" }}>
      <defs>
        <linearGradient id={id} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor={c} stopOpacity="0.28" />
          <stop offset="1" stopColor={c} stopOpacity="0" />
        </linearGradient>
      </defs>
      {fill && <path d={area} fill={`url(#${id})`} />}
      <path
        d={d}
        fill="none"
        stroke={c}
        strokeWidth={strokeW}
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect={fullWidth ? "non-scaling-stroke" : undefined}
      />
    </svg>
  );
}

/* ---------- Conviction score gauge + flag (signature) ---------- */
export function ScoreGauge({
  score = 50,
  flag = "amber",
  size = 132,
  label = "Conviction",
  thick = 9,
}: {
  score?: number;
  flag?: Flag;
  size?: number;
  label?: string;
  thick?: number;
}) {
  const r = (size - thick) / 2 - 2;
  const cx = size / 2,
    cy = size / 2;
  const start = Math.PI * 0.75,
    end = Math.PI * 2.25; // 270deg arc
  const ang = start + (end - start) * (Math.max(0, Math.min(100, score)) / 100);
  const pt = (a: number, rad = r): [number, number] => [cx + Math.cos(a) * rad, cy + Math.sin(a) * rad];
  const arc = (a0: number, a1: number) => {
    const [x0, y0] = pt(a0),
      [x1, y1] = pt(a1);
    const large = a1 - a0 > Math.PI ? 1 : 0;
    return `M ${x0} ${y0} A ${r} ${r} 0 ${large} 1 ${x1} ${y1}`;
  };
  const c = flagColor(flag);
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
      <svg width={size} height={size}>
        <path d={arc(start, end)} fill="none" stroke="var(--line)" strokeWidth={thick} strokeLinecap="round" />
        <path
          d={arc(start, ang)}
          fill="none"
          stroke={c}
          strokeWidth={thick}
          strokeLinecap="round"
          style={{ transition: "all .7s var(--ease)", filter: `drop-shadow(0 0 6px ${c}66)` }}
        />
        <text x={cx} y={cy - 2} textAnchor="middle" fontFamily="var(--font-display)" fontWeight="700" fontSize={size * 0.3} fill="var(--ink)">
          {score}
        </text>
        <text x={cx} y={cy + size * 0.15} textAnchor="middle" fontFamily="var(--font-mono)" fontSize="9" letterSpacing="1" fill="var(--ink-3)">
          / 100
        </text>
      </svg>
      <div className="eyebrow" style={{ marginTop: -4, whiteSpace: "nowrap" }}>
        {label}
      </div>
    </div>
  );
}

/* ---------- Flag pill ---------- */
export function FlagPill({ flag, children, sm }: { flag: Flag; children?: React.ReactNode; sm?: boolean }) {
  const c = flagColor(flag);
  const txt = flag === "green" ? "GREEN" : flag === "red" ? "RED" : "WATCH";
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        fontFamily: "var(--font-mono)",
        fontSize: sm ? 9.5 : 11,
        fontWeight: 600,
        letterSpacing: ".08em",
        color: c,
        background: `color-mix(in oklab, ${c} 14%, transparent)`,
        border: `1px solid color-mix(in oklab, ${c} 35%, transparent)`,
        padding: sm ? "2px 7px" : "3px 9px",
        borderRadius: 999,
        textTransform: "uppercase",
        whiteSpace: "nowrap",
      }}
    >
      <span style={{ width: 6, height: 6, borderRadius: 99, background: c, boxShadow: `0 0 6px ${c}` }} />
      {children || txt}
    </span>
  );
}

/* ---------- Candlestick + volume + pattern callouts ---------- */
export type Candle = { o: number; h: number; l: number; c: number; v: number };
export type MaLine = { data: (number | null)[]; color: string };
export type HLine = { v: number; label: string; color: string };
export type Callout = { at: number; label: string; color?: string };

export function Candles({
  data,
  w = 640,
  h = 280,
  callouts = [],
  showVol = true,
  ma = [],
  hlines = [],
}: {
  data: Candle[];
  w?: number;
  h?: number;
  callouts?: Callout[];
  showVol?: boolean;
  ma?: MaLine[];
  hlines?: HLine[];
}) {
  const padR = 52,
    padL = 10,
    padT = 12;
  const volH = showVol ? 46 : 0;
  const cH = h - volH - padT - 6;
  const { bars, yToPx, hi, lo, vmax } = useMemo(() => {
    if (!data.length) return { bars: [], yToPx: (v: number) => v, hi: 0, lo: 0, vmax: 0 };
    const hi = Math.max(...data.map((d) => d.h)),
      lo = Math.min(...data.map((d) => d.l));
    const rng = hi - lo || 1;
    const vmax = Math.max(...data.map((d) => d.v)) || 1;
    const cw = (w - padL - padR) / data.length;
    const yToPx = (v: number) => padT + (1 - (v - lo) / rng) * cH;
    const bars = data.map((d, i) => {
      const x = padL + i * cw + cw / 2;
      const up = d.c >= d.o;
      return { x, cw, up, oY: yToPx(d.o), cY: yToPx(d.c), hY: yToPx(d.h), lY: yToPx(d.l), v: d.v, i };
    });
    return { bars, yToPx, hi, lo, vmax };
  }, [data, w, h, cH]);

  const ticks = useMemo(() => {
    const arr: { v: number; y: number }[] = [];
    const steps = 4;
    for (let i = 0; i <= steps; i++) {
      const v = lo + (hi - lo) * (i / steps);
      arr.push({ v, y: yToPx(v) });
    }
    return arr;
  }, [hi, lo, yToPx]);

  if (!data.length) return <svg width="100%" viewBox={`0 0 ${w} ${h}`} />;

  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} style={{ display: "block" }}>
      {ticks.map((t, i) => (
        <g key={i}>
          <line x1={padL} x2={w - padR} y1={t.y} y2={t.y} stroke="var(--line-soft)" strokeWidth="1" />
          <text x={w - padR + 6} y={t.y + 3.5} fontSize="9.5" fill="var(--ink-3)" fontFamily="var(--font-mono)">
            {npr(t.v)}
          </text>
        </g>
      ))}
      {bars.map((b) => (
        <g key={b.i}>
          <line x1={b.x} x2={b.x} y1={b.hY} y2={b.lY} stroke={b.up ? V_POS : V_NEG} strokeWidth="1" opacity=".85" />
          <rect
            x={b.x - Math.max(1.2, b.cw * 0.3)}
            width={Math.max(2.4, b.cw * 0.6)}
            y={Math.min(b.oY, b.cY)}
            height={Math.max(1, Math.abs(b.cY - b.oY))}
            fill={b.up ? V_POS : V_NEG}
            opacity={b.up ? 0.9 : 0.92}
            rx="0.5"
          />
        </g>
      ))}
      {showVol &&
        bars.map((b) => {
          const vh = (b.v / vmax) * (volH - 6);
          return (
            <rect
              key={"v" + b.i}
              x={b.x - Math.max(1.2, b.cw * 0.3)}
              width={Math.max(2.4, b.cw * 0.6)}
              y={h - vh}
              height={vh}
              fill={b.up ? V_POS : V_NEG}
              opacity=".22"
            />
          );
        })}
      {hlines.map((hl, i) => {
        if (hl.v < lo || hl.v > hi) return null;
        const y = yToPx(hl.v);
        return (
          <g key={"hl" + i}>
            <line x1={padL} x2={w - padR} y1={y} y2={y} stroke={hl.color} strokeWidth="1" strokeDasharray="5 4" opacity=".7" />
            <g transform={`translate(${padL + 2}, ${y})`}>
              <rect x="0" y="-8" width={hl.label.length * 5.6 + 10} height="15" rx="3" fill="var(--panel-3)" stroke={hl.color} strokeOpacity=".5" />
              <text x="5" y="3" fontSize="9" fill={hl.color} fontFamily="var(--font-mono)">
                {hl.label}
              </text>
            </g>
          </g>
        );
      })}
      {ma.map((m, mi) => {
        let d = "";
        m.data.forEach((v, i) => {
          if (v == null) return;
          const x = padL + i * ((w - padL - padR) / data.length) + (w - padL - padR) / data.length / 2;
          d += (d ? " L " : "M ") + x + " " + yToPx(v);
        });
        return <path key={"ma" + mi} d={d} fill="none" stroke={m.color} strokeWidth="1.5" opacity=".9" strokeLinejoin="round" />;
      })}
      {callouts.map((c, i) => {
        const b = bars[Math.round(c.at * (bars.length - 1))];
        if (!b) return null;
        const cy = yToPx(hi) + 4;
        return (
          <g key={"c" + i}>
            <line x1={b.x} x2={b.x} y1={b.hY - 6} y2={cy + 16} stroke={c.color || V_WARN} strokeDasharray="3 3" strokeWidth="1" opacity=".8" />
            <circle cx={b.x} cy={b.hY - 6} r="3" fill={c.color || V_WARN} />
            <g transform={`translate(${Math.min(Math.max(b.x, 44), w - padR - 70)}, ${cy})`}>
              <rect x="-4" y="-2" width={c.label.length * 5.4 + 14} height="16" rx="4" fill="var(--panel-3)" stroke={c.color || V_WARN} strokeOpacity=".5" />
              <text x="4" y="9.5" fontSize="9" fill="var(--ink)" fontFamily="var(--font-mono)">
                {c.label}
              </text>
            </g>
          </g>
        );
      })}
    </svg>
  );
}

/* ---------- Diverging accumulation/distribution bars ---------- */
export type AccumRow = { broker: string; buy: number; sell: number };

export function AccumBars({ rows, w = 300 }: { rows: AccumRow[]; w?: number }) {
  const max = Math.max(1, ...rows.map((r) => Math.max(r.buy, r.sell)));
  const mid = w / 2;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
      {rows.map((r, i) => {
        const bw = (r.buy / max) * (mid - 4);
        const sw = (r.sell / max) * (mid - 4);
        const net = r.buy - r.sell;
        return (
          <div key={i} style={{ display: "grid", gridTemplateColumns: "96px 1fr 64px", alignItems: "center", gap: 8 }}>
            <span className="mono" style={{ fontSize: 10.5, color: "var(--ink-2)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {r.broker}
            </span>
            <svg width="100%" height="14" viewBox={`0 0 ${w} 14`} preserveAspectRatio="none">
              <line x1={mid} x2={mid} y1="0" y2="14" stroke="var(--line)" strokeWidth="1" />
              <rect x={mid - sw} y="2" width={sw} height="10" rx="2" fill={V_NEG} opacity=".75" />
              <rect x={mid} y="2" width={bw} height="10" rx="2" fill={V_POS} opacity=".82" />
            </svg>
            <span className="mono tnum" style={{ fontSize: 10.5, textAlign: "right", color: net >= 0 ? V_POS : V_NEG }}>
              {net >= 0 ? "+" : ""}
              {npr(net)}
            </span>
          </div>
        );
      })}
      {rows.length === 0 && <div style={{ fontSize: 12, color: "var(--ink-3)", padding: 8 }}>No broker activity in the period.</div>}
    </div>
  );
}

/* ---------- Sentiment / flow heatmap ---------- */
export type HeatRow = { sector: string; sentiment: number; flow: number };

export function Heatmap({ rows, colLabels = ["Sentiment", "Net Flow"] }: { rows: HeatRow[]; colLabels?: [string, string] }) {
  const cell = (v: number) => {
    const c = v >= 0 ? V_POS : V_NEG;
    return `color-mix(in oklab, ${c} ${Math.round(Math.min(1, Math.abs(v)) * 70 + 8)}%, var(--panel))`;
  };
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 5 }}>
      <div style={{ display: "grid", gridTemplateColumns: "128px 1fr 1fr", gap: 6, paddingBottom: 2 }}>
        <span></span>
        <span className="eyebrow" style={{ textAlign: "center" }}>
          {colLabels[0]}
        </span>
        <span className="eyebrow" style={{ textAlign: "center" }}>
          {colLabels[1]}
        </span>
      </div>
      {rows.map((r, i) => (
        <div key={i} style={{ display: "grid", gridTemplateColumns: "128px 1fr 1fr", gap: 6, alignItems: "center" }}>
          <span style={{ fontSize: 11.5, color: "var(--ink-2)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.sector}</span>
          <div style={{ height: 24, borderRadius: 6, background: cell(r.sentiment), display: "flex", alignItems: "center", justifyContent: "center", border: "1px solid var(--line-soft)" }}>
            <span className="mono tnum" style={{ fontSize: 10, color: "var(--ink)", opacity: 0.9 }}>
              {r.sentiment > 0 ? "+" : ""}
              {r.sentiment.toFixed(2)}
            </span>
          </div>
          <div style={{ height: 24, borderRadius: 6, background: cell(r.flow), display: "flex", alignItems: "center", justifyContent: "center", border: "1px solid var(--line-soft)" }}>
            <span className="mono tnum" style={{ fontSize: 10, color: "var(--ink)", opacity: 0.9 }}>
              {r.flow > 0 ? "+" : ""}
              {r.flow.toFixed(2)}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

/* ---------- mini donut ---------- */
export type DonutSeg = { value: number; color: string };

export function Donut({ segments, size = 96, thick = 12, center }: { segments: DonutSeg[]; size?: number; thick?: number; center?: React.ReactNode }) {
  const r = (size - thick) / 2,
    cx = size / 2,
    cy = size / 2,
    circ = 2 * Math.PI * r;
  let off = 0;
  return (
    <svg width={size} height={size}>
      <g transform={`rotate(-90 ${cx} ${cy})`}>
        {segments.map((s, i) => {
          const len = (s.value / 100) * circ;
          const el = (
            <circle
              key={i}
              cx={cx}
              cy={cy}
              r={r}
              fill="none"
              stroke={s.color}
              strokeWidth={thick}
              strokeDasharray={`${len} ${circ - len}`}
              strokeDashoffset={-off}
              strokeLinecap="butt"
            />
          );
          off += len;
          return el;
        })}
      </g>
      {center && (
        <text x={cx} y={cy + 4} textAnchor="middle" fontSize="15" fontWeight="700" fontFamily="var(--font-display)" fill="var(--ink)">
          {center}
        </text>
      )}
    </svg>
  );
}

/* ---------- 52-week (or any) range bar ---------- */
export function RangeBar({ low, high, cur, label }: { low: number; high: number; cur: number; label?: string }) {
  const pctPos = high > low ? Math.max(0, Math.min(100, ((cur - low) / (high - low)) * 100)) : 50;
  return (
    <div>
      {label && <div style={{ fontSize: 11.5, color: "var(--ink-3)", marginBottom: 8 }}>{label}</div>}
      <div style={{ position: "relative", height: 8, borderRadius: 99, background: "linear-gradient(90deg, var(--neg), var(--warn), var(--pos))", opacity: 0.85 }}>
        <div style={{ position: "absolute", top: -4, left: `${pctPos}%`, transform: "translateX(-50%)", width: 4, height: 16, borderRadius: 3, background: "var(--ink)", boxShadow: "0 0 0 3px var(--panel)" }} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 7 }}>
        <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>{npr(low)}</span>
        <span className="mono" style={{ fontSize: 11, fontWeight: 600 }}>{npr(cur, 1)}</span>
        <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>{npr(high)}</span>
      </div>
    </div>
  );
}

/* ---------- Fear & Greed semicircle gauge ---------- */
export function FearGreed({ value = 50, size = 168 }: { value?: number; size?: number }) {
  const cx = size / 2,
    cy = size * 0.62,
    r = size * 0.42;
  const a = Math.PI + (Math.max(0, Math.min(100, value)) / 100) * Math.PI;
  const seg = (f: number, t: number, col: string) => {
    const a0 = Math.PI + f * Math.PI,
      a1 = Math.PI + t * Math.PI;
    const x0 = cx + Math.cos(a0) * r,
      y0 = cy + Math.sin(a0) * r;
    const x1 = cx + Math.cos(a1) * r,
      y1 = cy + Math.sin(a1) * r;
    return <path d={`M ${x0} ${y0} A ${r} ${r} 0 0 1 ${x1} ${y1}`} fill="none" stroke={col} strokeWidth="10" strokeLinecap="butt" opacity=".9" />;
  };
  const nx = cx + Math.cos(a) * (r - 2),
    ny = cy + Math.sin(a) * (r - 2);
  const label = value >= 75 ? "Extreme Greed" : value >= 55 ? "Greed" : value >= 45 ? "Neutral" : value >= 25 ? "Fear" : "Extreme Fear";
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
      <svg width={size} height={size * 0.7}>
        {seg(0, 0.25, V_NEG)}
        {seg(0.26, 0.45, V_WARN)}
        {seg(0.46, 0.55, "var(--ink-3)")}
        {seg(0.56, 0.74, "color-mix(in oklab, var(--pos) 60%, var(--warn))")}
        {seg(0.75, 1, V_POS)}
        <line x1={cx} y1={cy} x2={nx} y2={ny} stroke="var(--ink)" strokeWidth="2.5" strokeLinecap="round" />
        <circle cx={cx} cy={cy} r="5" fill="var(--ink)" />
        <text x={cx} y={cy - 14} textAnchor="middle" fontFamily="var(--font-display)" fontWeight="700" fontSize="26" fill="var(--ink)">
          {value}
        </text>
      </svg>
      <div style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-2)", marginTop: -8 }}>{label}</div>
    </div>
  );
}

/* ---------- News impact dot ---------- */
export function ImpactDot({ sent }: { sent: "pos" | "neg" | "neu" }) {
  const c = sent === "pos" ? V_POS : sent === "neg" ? V_NEG : "var(--ink-3)";
  return <span style={{ width: 8, height: 8, borderRadius: 99, background: c, boxShadow: `0 0 6px ${c}`, flexShrink: 0 }} />;
}

/* ---------- Correlation / co-movement network ---------- */
export type NetNode = { id: string; sector: string; score: number; flag: Flag };
export type NetData = { nodes: NetNode[]; edges: [string, string, number][] };

export function Network({ data, w = 460, h = 320 }: { data: NetData; w?: number; h?: number }) {
  const [hover, setHover] = useState<string | null>(null);
  const pos = useMemo(() => {
    const sectors = [...new Set(data.nodes.map((n) => n.sector))];
    const map: Record<string, NetNode & { x: number; y: number }> = {};
    data.nodes.forEach((n) => {
      const si = sectors.indexOf(n.sector);
      const base = (si / (sectors.length || 1)) * Math.PI * 2;
      const within = data.nodes.filter((x) => x.sector === n.sector).indexOf(n);
      const cnt = data.nodes.filter((x) => x.sector === n.sector).length;
      const a = base + (within - (cnt - 1) / 2) * 0.32;
      const R = w * 0.34;
      map[n.id] = { ...n, x: w / 2 + Math.cos(a) * R, y: h / 2 + Math.sin(a) * R * 0.86 };
    });
    return map;
  }, [data, w, h]);
  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} style={{ display: "block" }}>
      {data.edges.map(([a, b, wt], i) => {
        const pa = pos[a],
          pb = pos[b];
        if (!pa || !pb) return null;
        const active = hover != null && (hover === a || hover === b);
        return (
          <line
            key={i}
            x1={pa.x}
            y1={pa.y}
            x2={pb.x}
            y2={pb.y}
            stroke={active ? "var(--accent)" : "var(--line)"}
            strokeWidth={active ? 1.8 : wt * 1.6}
            opacity={hover ? (active ? 0.9 : 0.12) : wt * 0.5}
          />
        );
      })}
      {Object.values(pos).map((n) => {
        const c = flagColor(n.flag);
        const rr = 8 + (n.score / 100) * 8;
        const active = hover === n.id;
        return (
          <g key={n.id} onMouseEnter={() => setHover(n.id)} onMouseLeave={() => setHover(null)} style={{ cursor: "pointer" }}>
            <circle
              cx={n.x}
              cy={n.y}
              r={rr}
              fill={`color-mix(in oklab, ${c} 22%, var(--panel))`}
              stroke={c}
              strokeWidth={active ? 2 : 1.2}
              style={{ filter: active ? `drop-shadow(0 0 8px ${c})` : "none", transition: "all .2s" }}
            />
            <text x={n.x} y={n.y + rr + 11} textAnchor="middle" fontSize="9" fontFamily="var(--font-mono)" fill={active ? "var(--ink)" : "var(--ink-3)"}>
              {n.id}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/* ---------- Multi-series line chart (broker position over time) ---------- */
export type LineSeries = { label: string; color: string; points: { t: number; v: number }[] };

export function MultiLineChart({ series, dates, w = 560, h = 180 }: { series: LineSeries[]; dates: string[]; w?: number; h?: number }) {
  const padL = 6, padR = 6, padT = 10, padB = 22;
  const all = series.flatMap((s) => s.points.map((p) => p.v));
  if (!all.length || dates.length === 0) return <div style={{ height: h }} />;
  const vmax = Math.max(...all, 0),
    vmin = Math.min(...all, 0),
    rng = vmax - vmin || 1;
  const tmax = dates.length - 1 || 1;
  const X = (t: number) => padL + (t / tmax) * (w - padL - padR);
  const Y = (v: number) => padT + (1 - (v - vmin) / rng) * (h - padT - padB);
  const zeroY = Y(0);
  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} style={{ display: "block" }}>
      {/* zero baseline */}
      <line x1={padL} x2={w - padR} y1={zeroY} y2={zeroY} stroke="var(--line)" strokeWidth="1" strokeDasharray="3 3" />
      {series.map((s, si) => {
        if (!s.points.length) return null;
        if (s.points.length === 1) {
          const p = s.points[0];
          return <circle key={si} cx={X(p.t)} cy={Y(p.v)} r="3.5" fill={s.color} />;
        }
        const d = s.points.map((p, i) => `${i ? "L" : "M"} ${X(p.t)} ${Y(p.v)}`).join(" ");
        return (
          <g key={si}>
            <path d={d} fill="none" stroke={s.color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
            {s.points.map((p, i) => <circle key={i} cx={X(p.t)} cy={Y(p.v)} r="2.2" fill={s.color} />)}
          </g>
        );
      })}
      {/* date axis (first / mid / last) */}
      {[0, Math.floor(tmax / 2), tmax].filter((v, i, a) => a.indexOf(v) === i).map((t) => (
        <text key={t} x={X(t)} y={h - 6} textAnchor={t === 0 ? "start" : t === tmax ? "end" : "middle"}
          fontSize="9" fontFamily="var(--font-mono)" fill="var(--ink-3)">{(dates[t] || "").slice(5)}</text>
      ))}
    </svg>
  );
}

/* moving-average helper */
export function movavg(arr: number[], n: number): (number | null)[] {
  return arr.map((_, i) => {
    if (i < n - 1) return null;
    let s = 0;
    for (let k = i - n + 1; k <= i; k++) s += arr[k];
    return s / n;
  });
}
