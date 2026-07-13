"use client";
// Trade Surveillance — investigation-first board for the firm's OWN fills.
// Flagged fills are grouped into cases (fund × scrip × day): each case carries
// a risk score, the LLM-written plain-language explanation, counterparty
// concentration (observed vs expected), the D+0..D+5 post-trade markout curve
// and the fill cluster. The clean book (LOW fills) collapses to one line.
// A flag for review, not a verdict.

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, AlertTriangle, CheckCircle2, ExternalLink, MessageSquare, ChevronRight, Activity, X, BookmarkPlus } from "lucide-react";
import { flushSync } from "react-dom";
import { api, type SurveillanceCase, type SurveillanceTrade } from "@/lib/api";
import { LoadTradebookButton } from "@/components/load-tradebook-button";
import { type Message, MessageBubble } from "@/components/chat/message-bubble";
import { ChatInput } from "@/components/chat/chat-input";

type Sev = "high" | "elevated" | "moderate";
const SEVC: Record<string, string> = { high: "var(--neg)", elevated: "#e8884e", moderate: "var(--warn)", low: "var(--ink-3)" };
const TIER_TO_SEV: Record<string, Sev> = { HIGH: "high", ELEVATED: "elevated", MODERATE: "moderate" };

function sevOf(c: SurveillanceCase): Sev { return TIER_TO_SEV[c.tier ?? ""] ?? "moderate"; }
function fmtN(n: number | null | undefined, d = 0) {
  return n == null ? "—" : Number(n).toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d });
}
function lakh(v: number | null | undefined) {
  if (v == null) return "—";
  const a = Math.abs(v);
  if (a >= 1e7) return `Rs ${(v / 1e7).toFixed(2)} Cr`;
  return `Rs ${(v / 1e5).toFixed(1)}L`;
}
function pctf(v: number | null | undefined, d = 2) {
  return v == null ? "—" : `${v > 0 ? "+" : ""}${(v * 100).toFixed(d)}%`;
}

/* ── severity pill ─────────────────────────────────────────────── */
function SevPill({ sev }: { sev: Sev }) {
  const c = SEVC[sev];
  return (
    <span className="mono" style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 9.5, fontWeight: 600, letterSpacing: ".12em", color: c, background: `color-mix(in oklab, ${c} 15%, transparent)`, border: `1px solid color-mix(in oklab, ${c} 38%, transparent)`, padding: "2px 9px", borderRadius: 999 }}>
      <span style={{ width: 6, height: 6, borderRadius: 99, background: c, boxShadow: `0 0 6px ${c}` }} />
      {sev.toUpperCase()}
    </span>
  );
}

function SideBadge({ side }: { side: string }) {
  const c = side === "BUY" ? "var(--pos)" : side === "SELL" ? "var(--neg)" : "var(--accent-2)";
  return <span className="mono" style={{ fontSize: 11, fontWeight: 700, letterSpacing: ".06em", color: c }}>{side}</span>;
}

/* ── market-context classification chip ────────────────────────── */
const CLASS_META: Record<string, { short: string; color: string }> = {
  "Likely Normal Market Behavior": { short: "LIKELY NORMAL", color: "var(--ok)" },
  "Elevated Concentration": { short: "ELEVATED CONC.", color: "#e8884e" },
  "Potentially Exceptional Concentration": { short: "EXCEPTIONAL", color: "var(--neg)" },
};

function ClassChip({ cls }: { cls: NonNullable<SurveillanceCase["classification"]> }) {
  const m = CLASS_META[cls.label] ?? { short: cls.label, color: "var(--ink-3)" };
  return (
    <span className="mono" title={`${cls.label} — confidence ${(cls.confidence * 100).toFixed(0)}%`}
      style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 9.5, fontWeight: 600, letterSpacing: ".1em", color: m.color, border: `1px dashed color-mix(in oklab, ${m.color} 50%, transparent)`, padding: "2px 9px", borderRadius: 999 }}>
      {m.short} · {(cls.confidence * 100).toFixed(0)}%
    </span>
  );
}

/* ── risk score gauge — glowing 270° instrument arc ────────────── */
function ScoreGauge({ score, sev, size = 92, thick = 8 }: { score: number; sev: Sev; size?: number; thick?: number }) {
  const c = SEVC[sev];
  const r = (size - thick) / 2 - 2;
  const cx = size / 2, cy = size / 2;
  const start = Math.PI * 0.75, end = Math.PI * 2.25; // 270° sweep
  const frac = Math.min(1, Math.max(0, score / 100));
  const ang = start + (end - start) * frac;
  const pt = (a: number) => [cx + Math.cos(a) * r, cy + Math.sin(a) * r];
  const arc = (a0: number, a1: number) => {
    const [x0, y0] = pt(a0), [x1, y1] = pt(a1);
    const large = a1 - a0 > Math.PI ? 1 : 0;
    return `M ${x0} ${y0} A ${r} ${r} 0 ${large} 1 ${x1} ${y1}`;
  };
  return (
    <div style={{ position: "relative", width: size, height: size }}>
      <svg width={size} height={size}>
        <path d={arc(start, end)} fill="none" stroke="var(--panel-3)" strokeWidth={thick} strokeLinecap="round" />
        <path d={arc(start, ang)} fill="none" stroke={c} strokeWidth={thick} strokeLinecap="round"
          style={{ filter: `drop-shadow(0 0 5px color-mix(in oklab, ${c} 55%, transparent))`, transition: "all .6s var(--ease)" }} />
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        <span className="mono" style={{ fontSize: size * 0.27, fontWeight: 700, lineHeight: 1, color: c }}>{Math.round(score)}</span>
        <span className="mono" style={{ fontSize: 8.5, color: "var(--ink-3)", marginTop: 2, letterSpacing: ".1em" }}>/ 100</span>
      </div>
    </div>
  );
}

/* ── book-health ring — big clean-rate instrument with glow ────── */
function HealthRing({ pct, flagged, total, size = 132, thick = 11 }: { pct: number | null; flagged: number; total: number; size?: number; thick?: number }) {
  const c = "var(--ok)";
  const r = (size - thick) / 2 - 2;
  const cx = size / 2, cy = size / 2;
  const start = Math.PI * 0.75, end = Math.PI * 2.25;
  const frac = Math.min(1, Math.max(0, (pct ?? 0) / 100));
  const ang = start + (end - start) * frac;
  const pt = (a: number) => [cx + Math.cos(a) * r, cy + Math.sin(a) * r];
  const arc = (a0: number, a1: number) => {
    const [x0, y0] = pt(a0), [x1, y1] = pt(a1);
    const large = a1 - a0 > Math.PI ? 1 : 0;
    return `M ${x0} ${y0} A ${r} ${r} 0 ${large} 1 ${x1} ${y1}`;
  };
  return (
    <div style={{ position: "relative", width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size}>
        <path d={arc(start, end)} fill="none" stroke="var(--panel-3)" strokeWidth={thick} strokeLinecap="round" />
        <path d={arc(start, ang)} fill="none" stroke={c} strokeWidth={thick} strokeLinecap="round"
          style={{ filter: `drop-shadow(0 0 6px color-mix(in oklab, ${c} 60%, transparent))`, transition: "all .7s var(--ease)" }} />
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        <span className="mono" style={{ fontSize: 27, fontWeight: 700, lineHeight: 1, color: c }}>{pct != null ? pct : "—"}<span style={{ fontSize: 14 }}>%</span></span>
        <span className="eyebrow" style={{ fontSize: 8.5, marginTop: 4 }}>clean book</span>
        <span className="mono" style={{ fontSize: 10, color: "var(--ink-3)", marginTop: 4 }}>{flagged} of {fmtN(total)}</span>
      </div>
    </div>
  );
}

/* ── scan composition bar — clean vs each flagged tier ──────────── */
const TIER_SEG: { key: string; label: string; color: string }[] = [
  { key: "HIGH", label: "high", color: SEVC.high },
  { key: "ELEVATED", label: "elevated", color: "#e8884e" },
  { key: "MODERATE", label: "moderate", color: SEVC.moderate },
  { key: "LOW", label: "clean", color: "var(--ok)" },
];
function CompositionBar({ byTier, total }: { byTier: Record<string, number>; total: number }) {
  const segs = TIER_SEG.map((t) => ({ ...t, n: byTier[t.key] ?? 0 })).filter((t) => t.n > 0);
  return (
    <div style={{ minWidth: 0, flex: 1 }}>
      <div className="eyebrow" style={{ marginBottom: 10 }}>Scan composition · {fmtN(total)} fills</div>
      <div style={{ display: "flex", height: 14, borderRadius: 99, overflow: "hidden", background: "var(--panel-3)", border: "1px solid var(--line-soft)" }}>
        {segs.map((s) => (
          <div key={s.key} title={`${s.label}: ${s.n}`} style={{ width: `${(s.n / total) * 100}%`, minWidth: s.key === "LOW" ? 0 : 3, background: s.color, boxShadow: s.key === "LOW" ? "none" : `0 0 8px color-mix(in oklab, ${s.color} 60%, transparent)` }} />
        ))}
      </div>
      <div style={{ display: "flex", gap: 16, marginTop: 12, flexWrap: "wrap" }}>
        {TIER_SEG.map((t) => {
          const n = byTier[t.key] ?? 0;
          const on = n > 0;
          return (
            <div key={t.key} style={{ display: "flex", alignItems: "center", gap: 7, opacity: on ? 1 : 0.4 }}>
              <span style={{ width: 7, height: 7, borderRadius: 99, background: t.color, boxShadow: on ? `0 0 6px ${t.color}` : "none" }} />
              <span className="mono" style={{ fontSize: 14, fontWeight: 700, color: on ? "var(--ink)" : "var(--ink-3)" }}>{n}</span>
              <span className="mono" style={{ fontSize: 10, letterSpacing: ".1em", textTransform: "uppercase", color: "var(--ink-3)" }}>{t.label}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ── metric tile — labelled terminal readout ───────────────────── */
function MetricTile({ label, value, sub, tone }: { label: string; value: React.ReactNode; sub?: string; tone?: string }) {
  return (
    <div style={{ padding: "11px 14px", borderRadius: 11, background: "var(--panel-2)", border: "1px solid var(--line-soft)" }}>
      <div className="eyebrow" style={{ fontSize: 9 }}>{label}</div>
      <div className="mono" style={{ fontSize: 19, fontWeight: 700, marginTop: 5, lineHeight: 1, color: tone ?? "var(--ink)" }}>{value}</div>
      {sub && <div style={{ fontSize: 10.5, color: "var(--ink-3)", marginTop: 5, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{sub}</div>}
    </div>
  );
}

/* ── concentration meter: observed vs expected ─────────────────── */
function ConcentrationMeter({ data }: { data: NonNullable<SurveillanceCase["concentration"]> }) {
  const col = data.value >= 75 ? "var(--neg)" : data.value >= 45 ? "#e8884e" : "var(--warn)";
  const exp = Math.min(100, Math.max(0, data.expected));
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 9, gap: 8 }}>
        <span style={{ fontSize: 11.5, color: "var(--ink-2)" }}>{data.label}</span>
        <span className="mono" style={{ fontSize: 17, fontWeight: 700, color: col }}>{data.value}%</span>
      </div>
      <div style={{ position: "relative", height: 10, borderRadius: 99, background: "var(--panel-3)", overflow: "hidden" }}>
        <div style={{ width: `${Math.min(100, data.value)}%`, height: "100%", background: `linear-gradient(90deg, color-mix(in oklab, ${col} 55%, transparent), ${col})`, borderRadius: 99 }} />
      </div>
      <div style={{ position: "relative", height: 0 }}>
        <div style={{ position: "absolute", left: `${exp}%`, top: -16, transform: "translateX(-50%)" }}>
          <div style={{ width: 2, height: 16, background: "var(--ink-2)", margin: "0 auto", opacity: 0.8 }} />
        </div>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 9 }}>
        <span className="mono" style={{ fontSize: 10, color: "var(--ink-3)" }}>0</span>
        <span className="mono" style={{ fontSize: 10, color: "var(--ink-2)" }}>↑ expected ~{data.expected}%</span>
        <span className="mono" style={{ fontSize: 10, color: "var(--ink-3)" }}>z = {data.surprise_z.toFixed(1)}</span>
      </div>
    </div>
  );
}

/* ── markout curve: post-trade price drift ─────────────────────── */
function MarkoutCurve({ data }: { data: number[] | null }) {
  const w = 260, h = 96;
  if (!data || data.length < 2) {
    return (
      <div style={{ height: h, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 7, color: "var(--ink-3)", textAlign: "center" }}>
        <span style={{ display: "flex", alignItems: "center", justifyContent: "center", width: 30, height: 30, borderRadius: 99, background: "var(--panel-3)", border: "1px solid var(--line-soft)" }}>
          <Activity size={15} strokeWidth={1.5} />
        </span>
        <span style={{ fontSize: 11.5, color: "var(--ink-2)" }}>Markout pending</span>
        <span style={{ fontSize: 10, maxWidth: 180, lineHeight: 1.5 }}>Resolves once 5 sessions of post-trade prices have settled.</span>
      </div>
    );
  }
  const min = Math.min(...data, 0), max = Math.max(...data, 0), rng = max - min || 1;
  const X = (i: number) => (i / (data.length - 1)) * (w - 34) + 4;
  const Y = (v: number) => 8 + (1 - (v - min) / rng) * (h - 28);
  const last = data[data.length - 1];
  const adverse = last < 0;
  const c = adverse ? "var(--neg)" : "var(--pos)";
  let d = `M ${X(0)} ${Y(data[0])}`;
  data.forEach((v, i) => { if (i) d += ` L ${X(i)} ${Y(v)}`; });
  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} style={{ display: "block" }}>
      <defs>
        <linearGradient id="mkg" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor={c} stopOpacity=".22" /><stop offset="1" stopColor={c} stopOpacity="0" />
        </linearGradient>
      </defs>
      <line x1="4" x2={w - 30} y1={Y(0)} y2={Y(0)} stroke="var(--line)" strokeWidth="1" strokeDasharray="3 3" />
      <path d={`${d} L ${X(data.length - 1)} ${Y(0)} L ${X(0)} ${Y(0)} Z`} fill="url(#mkg)" />
      <path d={d} fill="none" stroke={c} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
      {data.map((v, i) => <circle key={i} cx={X(i)} cy={Y(v)} r={i === data.length - 1 ? 3.5 : 2} fill={c} />)}
      <text x={X(data.length - 1)} y={Y(last) + (adverse ? 14 : -8)} fontSize="11" fontWeight="700" fontFamily="var(--font-mono)" fill={c} textAnchor="end">
        {last > 0 ? "+" : ""}{last}%
      </text>
      {data.map((_, i) => (
        <text key={i} x={X(i)} y={h - 2} fontSize="8.5" fontFamily="var(--font-mono)" fill="var(--ink-3)" textAnchor="middle">D+{i}</text>
      ))}
    </svg>
  );
}

/* ── integrated-verdict factor strip — why the trade was flagged ── */
// One row per lens that fed the integrated verdict, strongest contributor first.
// Lit lenses (concern ≥ 0.5) are highlighted; this is the "factorized but one
// verdict" view — the breakdown behind the single score, not separate widgets.
function FactorStrip({ factors }: { factors: NonNullable<SurveillanceCase["factors"]> }) {
  const shown = factors.filter((f) => f.value > 0.02);
  if (shown.length === 0) return null;
  return (
    <div style={{ padding: 15, borderRadius: 11, background: "var(--panel-2)", border: "1px solid var(--line-soft)", marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 12 }}>Why flagged — factor breakdown</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
        {shown.map((f) => {
          const lit = f.value >= 0.5;
          const col = lit ? "var(--neg)" : f.value >= 0.25 ? "var(--warn, #d8a13a)" : "var(--ink-3)";
          return (
            <div key={f.lens} style={{ display: "grid", gridTemplateColumns: "150px 1fr 42px", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 11.5, color: lit ? "var(--ink-1)" : "var(--ink-2)", fontWeight: lit ? 600 : 400 }}>{f.label}</span>
              <div style={{ position: "relative", height: 7, borderRadius: 99, background: "var(--line)", overflow: "hidden" }}>
                <div style={{ position: "absolute", inset: 0, width: `${Math.round(f.value * 100)}%`, background: col, boxShadow: lit ? `0 0 7px ${col}` : "none", borderRadius: 99 }} />
              </div>
              <span className="mono tabular-nums" style={{ fontSize: 11, textAlign: "right", color: col }}>{Math.round(f.value * 100)}</span>
              {f.note && <span style={{ gridColumn: "2 / 4", fontSize: 10.5, color: "var(--ink-3)", lineHeight: 1.4, marginTop: -3 }}>{f.note}</span>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ── fill cluster timeline ─────────────────────────────────────── */
function FillCluster({ fills, total }: { fills: SurveillanceCase["fills"]; total: number }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {fills.slice(0, 6).map((f, i) => {
        const c = f.side === "BUY" ? "var(--pos)" : "var(--neg)";
        return (
          <div key={i} style={{ display: "grid", gridTemplateColumns: "60px 42px 1fr auto", gap: 8, alignItems: "center", padding: "5px 0", borderBottom: i < Math.min(fills.length, 6) - 1 ? "1px solid var(--line-soft)" : "none" }}>
            <span className="mono" style={{ fontSize: 10.5, color: "var(--ink-3)" }}>{f.t}</span>
            <span className="mono" style={{ fontSize: 10, fontWeight: 700, color: c }}>{f.side}</span>
            <span className="mono tabular-nums" style={{ fontSize: 11, color: "var(--ink-2)" }}>{fmtN(f.qty)} @ {fmtN(f.px, 1)}</span>
            <span style={{ width: 6, height: 6, borderRadius: 99, background: c, boxShadow: `0 0 5px ${c}` }} />
          </div>
        );
      })}
      {total > 6 && <span className="mono" style={{ fontSize: 10, color: "var(--ink-3)", paddingTop: 4 }}>+ {total - 6} more fills</span>}
    </div>
  );
}

/* ── broker market-context tile ────────────────────────────────── */
function MarketContextTile({ c }: { c: SurveillanceCase }) {
  const mc = c.market_context!;
  const cls = c.classification;
  const d = mc.trade_date;
  const sh = (v: number | null) => (v == null ? "—" : `${(v * 100).toFixed(1)}%`);
  const posColor = (l: string) => (l === "accumulating" ? "var(--pos)" : l === "distributing" ? "var(--neg)" : "var(--ink-2)");
  const rows: [string, React.ReactNode][] = [
    ["Trade-day share", <span key="d" className="mono" style={{ fontWeight: 600 }}>{sh(d.total_share)} <span style={{ color: "var(--ink-3)", fontWeight: 400 }}>· rank #{d.rank ?? "—"} of {d.n_brokers}{d.dominant ? " · dominant" : ""}</span></span>],
    ["Day buys / sells", <span key="bs" className="mono">{sh(d.buy_share)} / {sh(d.sell_share)}</span>],
    ["Prior 30 sessions", <span key="h30" className="mono">{sh(mc.hist_30d.total_share)} <span style={{ color: "var(--ink-3)" }}>({mc.hist_30d.n_days}d data)</span></span>],
    ["Prior 90 sessions", <span key="h90" className="mono">{sh(mc.hist_90d.total_share)} <span style={{ color: "var(--ink-3)" }}>({mc.hist_90d.n_days}d data)</span></span>],
    ["Positioning 7d / 30d", (
      <span key="p" className="mono">
        <span style={{ color: posColor(mc.positioning_7d.label) }}>{mc.positioning_7d.label}</span>
        {" / "}
        <span style={{ color: posColor(mc.positioning_30d.label) }}>{mc.positioning_30d.label}</span>
      </span>
    )],
  ];
  return (
    <div style={{ padding: 15, borderRadius: 11, background: "var(--panel-2)", border: "1px solid var(--line-soft)" }}>
      <div className="eyebrow" style={{ marginBottom: 10 }}>Broker market context</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {rows.map(([k, v]) => (
          <div key={k} style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8, fontSize: 11.5 }}>
            <span style={{ color: "var(--ink-3)" }}>{k}</span>
            <span style={{ fontSize: 11.5, textAlign: "right" }}>{v}</span>
          </div>
        ))}
      </div>
      {cls && (
        <div style={{ marginTop: 11, paddingTop: 10, borderTop: "1px solid var(--line-soft)" }}>
          <ClassChip cls={cls} />
          <p style={{ margin: "8px 0 0", fontSize: 11, lineHeight: 1.55, color: "var(--ink-2)" }}>{cls.rationale}</p>
        </div>
      )}
    </div>
  );
}

/* ── recorded findings (read-only — written from the case chat) ── */
function FindingsList({ c }: { c: SurveillanceCase }) {
  const responses = c.responses ?? [];
  if (responses.length === 0) return null;
  return (
    <div style={{ marginTop: 12, padding: 15, borderRadius: 11, background: "var(--panel-2)", border: "1px solid var(--line-soft)" }}>
      <div className="eyebrow" style={{ marginBottom: 10 }}>Recorded findings ({responses.length})</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {responses.map((r) => (
          <div key={r.id} style={{ display: "flex", gap: 10 }}>
            <div style={{ width: 26, height: 26, borderRadius: 99, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center", background: "var(--panel-3)", border: "1px solid var(--line)" }}>
              <span className="mono" style={{ fontSize: 10, fontWeight: 700, color: "var(--accent)" }}>{(r.author || "?").slice(0, 1).toUpperCase()}</span>
            </div>
            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                <span style={{ fontSize: 11.5, fontWeight: 600 }}>{r.author}</span>
                <span className="mono" style={{ fontSize: 10, color: "var(--ink-4)" }}>{r.created_at ? new Date(r.created_at).toLocaleString() : ""}</span>
              </div>
              <p style={{ margin: "3px 0 0", fontSize: 12.5, lineHeight: 1.55, color: "var(--ink-2)", whiteSpace: "pre-wrap" }}>{r.body}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── floating per-case analyst chat ────────────────────────────── */
function CaseChatPanel({ c, onClose }: { c: SurveillanceCase; onClose: () => void }) {
  const qc = useQueryClient();
  const [messages, setMessages] = useState<Message[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [sending, setSending] = useState(false);
  const [statusText, setStatusText] = useState("");
  const [savingFinding, setSavingFinding] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const sev = sevOf(c);

  // Restore the persistent thread for THIS case on open.
  useEffect(() => {
    let alive = true;
    setLoaded(false);
    setMessages([]);
    api.surveillance.caseChat(c.case_key)
      .then((turns) => { if (alive) setMessages(turns.map((t) => ({ role: t.role, content: t.content }))); })
      .catch(() => {})
      .finally(() => { if (alive) setLoaded(true); });
    return () => { alive = false; abortRef.current?.abort(); };
  }, [c.case_key]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, sending]);

  function send(query: string) {
    if (sending) return;
    setSending(true);
    setStatusText("Thinking…");
    setMessages((prev) => [...prev, { role: "user", content: query }]);
    abortRef.current = api.surveillance.caseChatStream(
      c.case_key,
      query,
      (token) => {
        flushSync(() => {
          setMessages((prev) => {
            const msgs = [...prev];
            const last = msgs[msgs.length - 1];
            if (last?.role === "assistant") msgs[msgs.length - 1] = { ...last, content: last.content + token };
            else msgs.push({ role: "assistant", content: token });
            return msgs;
          });
        });
      },
      () => { setSending(false); setStatusText(""); abortRef.current = null; },
      (err) => {
        setMessages((prev) => [...prev, { role: "assistant", content: `_Error: ${err.message}_` }]);
        setSending(false); setStatusText(""); abortRef.current = null;
      },
      (status) => setStatusText(status),
    );
  }

  async function saveFinding() {
    if (savingFinding || messages.length === 0) return;
    setSavingFinding(true);
    try {
      const r = await api.surveillance.saveCaseFinding(c.case_key, localStorage.getItem("nrc.surv_author") || "CEO");
      if (r.ok) qc.invalidateQueries({ queryKey: ["surv-cases"] });
    } catch { /* noop */ }
    setSavingFinding(false);
  }

  return (
    <div className="fixed bottom-5 right-5 z-50 flex flex-col overflow-hidden rounded-2xl border"
      style={{ width: "min(420px, calc(100vw - 40px))", height: "min(620px, calc(100vh - 96px))", borderColor: "var(--line)", background: "var(--bg)", boxShadow: "0 12px 40px rgba(0,0,0,.34)" }}>
      {/* header */}
      <div className="flex h-[54px] items-center justify-between border-b px-3" style={{ borderColor: "var(--line)", background: `color-mix(in oklab, ${SEVC[sev]} 7%, var(--panel))` }}>
        <div className="flex min-w-0 items-center gap-2">
          <MessageSquare className="h-[14px] w-[14px] shrink-0" style={{ color: SEVC[sev] }} strokeWidth={1.75} />
          <div className="min-w-0">
            <div className="truncate text-[13px] font-medium">
              <span className="mono" style={{ fontWeight: 700 }}>{c.scrip}</span> · {c.case_id}
            </div>
            <div className="truncate text-[10px] uppercase tracking-wide" style={{ color: "var(--ink-3)" }}>
              Case analyst · context pre-loaded · thread saved
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={saveFinding} disabled={savingFinding || messages.length === 0}
            title="Distill this chat into a recorded finding on the case"
            className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11.5px] font-semibold disabled:opacity-40"
            style={{ background: "var(--panel-2)", color: "var(--ink-2)", border: "1px solid var(--line)" }}>
            <BookmarkPlus size={13} strokeWidth={2} /> {savingFinding ? "Saving…" : "Save finding"}
          </button>
          <button onClick={onClose} className="flex h-7 w-7 items-center justify-center rounded-md text-fg-muted transition-colors hover:bg-bg-hover hover:text-fg" aria-label="Close case chat">
            <X className="h-[14px] w-[14px]" strokeWidth={1.75} />
          </button>
        </div>
      </div>

      {/* thread */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        {!loaded ? (
          <div style={{ padding: 24, fontSize: 12, color: "var(--ink-3)" }}>Loading thread…</div>
        ) : messages.length === 0 && !sending ? (
          <div className="flex h-full flex-col justify-end px-3 pb-4">
            <div className="mb-2 text-[10.5px] uppercase tracking-wide" style={{ color: "var(--ink-4)" }}>
              The analyst already knows this case — try
            </div>
            <div className="space-y-1.5">
              {[
                "Walk me through why this was flagged",
                `Is ${c.counterparty ?? "the counterparty"} a problem here, or just liquidity?`,
                "What should the desk check before we clear this?",
                "What would make this case HIGH severity?",
              ].map((p) => (
                <button key={p} onClick={() => send(p)}
                  className="w-full rounded-lg px-3 py-2 text-left text-[12.5px] transition-colors hover:bg-bg-hover"
                  style={{ border: "1px solid var(--line-soft)", color: "var(--ink-2)" }}>
                  {p}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="px-3 py-4 space-y-3">
            {messages.map((m, i) => <MessageBubble key={i} message={m} />)}
            {sending && messages[messages.length - 1]?.role !== "assistant" && (
              <div className="flex items-center gap-2 px-1 text-[12px]" style={{ color: "var(--ink-3)" }}>
                <span className="thinking-dot" style={{ animationDelay: "0ms" }} />
                <span className="thinking-dot" style={{ animationDelay: "160ms" }} />
                <span className="thinking-dot" style={{ animationDelay: "320ms" }} />
                <span>{statusText || "Thinking…"}</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* input */}
      <div className="px-3 py-3" style={{ borderTop: "1px solid var(--line)" }}>
        <ChatInput onSubmit={send} disabled={sending} />
        <p className="mt-1.5 px-1 text-[10px]" style={{ color: "var(--ink-4)" }}>
          Scoped to {c.case_id} — every turn is saved; “Save finding” records the conclusion on the case.
        </p>
      </div>
    </div>
  );
}

/* ── investigation case card ───────────────────────────────────── */
function CaseCard({ c, defaultOpen, onChat }: { c: SurveillanceCase; defaultOpen: boolean; onChat: (c: SurveillanceCase) => void }) {
  const router = useRouter();
  const [open, setOpen] = useState(defaultOpen);
  const sev = sevOf(c);
  const col = SEVC[sev];
  const facts: [string, string][] = [
    ["Date", c.trade_date],
    ["Window", c.window ?? "—"],
    ["Fills", String(c.n_fills_total)],
    ["Qty", fmtN(c.qty)],
    ["Avg price", fmtN(c.price, 1)],
    ["Benchmark", fmtN(c.vwap, 1)],
    ["Slippage", pctf(c.slippage_pct)],
    ["Notional", lakh(c.notional)],
  ];
  return (
    <div className="panel" style={{ overflow: "hidden", boxShadow: "var(--shadow)" }}>
      <div style={{ display: "flex", alignItems: "stretch" }}>
        <div style={{ width: 4, flexShrink: 0, background: `linear-gradient(180deg, ${col}, color-mix(in oklab, ${col} 35%, transparent))`, boxShadow: `0 0 16px -2px color-mix(in oklab, ${col} 65%, transparent)` }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <button onClick={() => setOpen((o) => !o)} style={{ font: "inherit", cursor: "pointer", width: "100%", textAlign: "left", background: "none", border: "none", color: "inherit", padding: "16px 20px", display: "flex", alignItems: "center", gap: 16 }}>
            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 11, flexWrap: "wrap" }}>
                <span className="mono" style={{ fontSize: 10.5, color: "var(--ink-4)" }}>{c.case_id}</span>
                <span className="mono" style={{ fontSize: 18, fontWeight: 700 }}>{c.scrip}</span>
                <SideBadge side={c.side} />
                <SevPill sev={sev} />
                {c.classification && <ClassChip cls={c.classification} />}
              </div>
              <div style={{ fontSize: 15.5, fontWeight: 600, marginTop: 7 }}>{c.pattern}</div>
              <div style={{ fontSize: 11.5, color: "var(--ink-3)", marginTop: 3 }}>
                {(c.side === "SELL" ? "Sold" : c.side === "CROSS" ? "Crossed" : "Bought")} for{" "}
                <span style={{ color: "var(--ink-2)" }}>{c.client_name ?? c.client_code}</span> on {c.trade_date}
                {c.price != null ? ` at ~Rs ${fmtN(c.price, 1)}` : ""}
              </div>
              <div style={{ display: "flex", gap: 14, marginTop: 6, flexWrap: "wrap" }}>
                <span style={{ fontSize: 11.5, color: "var(--ink-3)" }}>
                  <span style={{ color: "var(--ink-4)" }}>Fund</span>{" "}
                  <span style={{ color: "var(--ink-2)" }}>{c.client_name ?? c.client_code}</span>
                </span>
                <span style={{ fontSize: 11.5, color: "var(--ink-3)" }}>
                  <span style={{ color: "var(--ink-4)" }}>Counterparty</span>{" "}
                  <span style={{ color: "var(--ink-2)" }}>{c.counterparty ?? "—"}</span>
                </span>
              </div>
            </div>
            <div style={{ flexShrink: 0, textAlign: "center" }}>
              <ScoreGauge score={c.score} sev={sev} />
              <div className="mono" style={{ fontSize: 8.5, letterSpacing: ".12em", color: "var(--ink-3)", marginTop: 4 }}>VERDICT</div>
              {c.microstructure_score != null && (
                <div className="mono" style={{ fontSize: 8.5, color: "var(--ink-4)", marginTop: 2 }}>micro {Math.round(c.microstructure_score)}</div>
              )}
            </div>
            <ChevronRight size={18} style={{ color: "var(--ink-3)", transform: open ? "rotate(90deg)" : "none", transition: "transform .2s", flexShrink: 0 }} />
          </button>

          {open && (
            <div style={{ padding: "0 20px 20px" }}>
              {/* trade facts strip */}
              <div style={{ display: "flex", flexWrap: "wrap", padding: "12px 6px", borderRadius: 11, background: "var(--panel-2)", border: "1px solid var(--line-soft)", marginBottom: 14 }}>
                {facts.map(([k, v], i) => (
                  <div key={k} style={{ padding: "0 14px", borderRight: i < facts.length - 1 ? "1px solid var(--line)" : "none" }}>
                    <div className="eyebrow" style={{ fontSize: 9 }}>{k}</div>
                    <div className="mono" style={{ fontSize: 13, fontWeight: 600, marginTop: 3 }}>{v}</div>
                  </div>
                ))}
              </div>

              {/* integrated-verdict factor breakdown — the lenses behind the score */}
              {c.factors && c.factors.length > 0 && <FactorStrip factors={c.factors} />}

              {/* quantitative signals that tripped the flag */}
              {c.flag_reasons.length > 0 && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 12 }}>
                  {c.flag_reasons.map((r) => (
                    <span key={r} style={{ display: "inline-flex", alignItems: "center", gap: 7, fontSize: 11.5, color: "var(--ink-2)", padding: "5px 11px", borderRadius: 8, background: "var(--panel-2)", border: "1px solid var(--line-soft)" }}>
                      <span style={{ width: 5, height: 5, borderRadius: 99, background: col, boxShadow: `0 0 5px ${col}`, flexShrink: 0 }} />
                      {r}
                    </span>
                  ))}
                </div>
              )}

              {/* LLM reasoning */}
              <div style={{ display: "flex", gap: 11, padding: "13px 15px", borderRadius: 11, background: `color-mix(in oklab, ${col} 8%, transparent)`, border: `1px solid color-mix(in oklab, ${col} 26%, transparent)`, marginBottom: 14 }}>
                <AlertTriangle size={16} style={{ color: col, flexShrink: 0, marginTop: 2 }} />
                {c.explanation ? (
                  <p style={{ margin: 0, fontSize: 13, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>{c.explanation}</p>
                ) : (
                  <p style={{ margin: 0, fontSize: 13, lineHeight: 1.6, color: "var(--ink-3)", fontStyle: "italic" }}>
                    Writing the case note… the analyst model is reviewing this cluster.
                  </p>
                )}
              </div>

              {/* evidence grid */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))", gap: 12 }}>
                <div style={{ padding: 15, borderRadius: 11, background: "var(--panel-2)", border: "1px solid var(--line-soft)" }}>
                  <div className="eyebrow" style={{ marginBottom: 14 }}>Counterparty concentration</div>
                  {c.concentration ? <ConcentrationMeter data={c.concentration} /> : (
                    <div style={{ height: 80, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--ink-3)", fontSize: 11 }}>
                      No counterparty statistic for this case
                    </div>
                  )}
                </div>
                <div style={{ padding: 15, borderRadius: 11, background: "var(--panel-2)", border: "1px solid var(--line-soft)" }}>
                  <div className="eyebrow" style={{ marginBottom: 8 }}>Post-trade markout</div>
                  <MarkoutCurve data={c.markout_curve} />
                </div>
                <div style={{ padding: 15, borderRadius: 11, background: "var(--panel-2)", border: "1px solid var(--line-soft)" }}>
                  <div className="eyebrow" style={{ marginBottom: 10 }}>Fill cluster</div>
                  <FillCluster fills={c.fills} total={c.n_fills_total} />
                </div>
                {c.market_context && <MarketContextTile c={c} />}
              </div>

              {/* recorded findings (saved from the case chat) */}
              <FindingsList c={c} />

              {/* tags + actions */}
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginTop: 12, flexWrap: "wrap" }}>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  {c.tags.map((t) => (
                    <span key={t} className="mono" style={{ fontSize: 10, padding: "3px 9px", borderRadius: 999, color: "var(--ink-2)", border: "1px solid var(--line)", background: "var(--panel-2)" }}>{t}</span>
                  ))}
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button
                    onClick={() => router.push(`/scrip/${c.scrip}#floorsheet`)}
                    className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-semibold"
                    style={{ background: "var(--panel-2)", color: "var(--ink-2)", border: "1px solid var(--line)" }}>
                    <ExternalLink size={13} strokeWidth={2} /> Open {c.scrip}
                  </button>
                  <button
                    onClick={() => onChat(c)}
                    className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-semibold"
                    style={{ background: "var(--accent)", color: "var(--bg)", border: "1px solid var(--accent)" }}>
                    <MessageSquare size={13} strokeWidth={2} /> Discuss case
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── clean book (LOW fills) ────────────────────────────────────── */
function CleanBook({ rows }: { rows: SurveillanceTrade[] }) {
  const [open, setOpen] = useState(false);
  const shown = rows.slice(0, 14);
  return (
    <div className="panel" style={{ overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "14px 18px", borderBottom: open ? "1px solid var(--line)" : "none" }}>
        <CheckCircle2 size={16} style={{ color: "var(--ok)", flexShrink: 0 }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <span style={{ fontSize: 13, color: "var(--ink-2)" }}>
            {fmtN(rows.length)} fills cleared automatically — within market tolerance, no counterparty concentration, no adverse markout.
          </span>
        </div>
        <span className="mono" style={{ fontSize: 10.5, color: "var(--ink-3)" }}>clean book</span>
        <button onClick={() => setOpen((o) => !o)} className="rounded-lg px-3 py-1.5 text-[12px] font-semibold"
          style={{ background: "var(--panel-2)", color: "var(--ink-2)", border: "1px solid var(--line)" }}>
          {open ? "Collapse" : "Expand"}
        </button>
      </div>
      {open && (
        <div>
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ textAlign: "left" }}>Date</th>
                <th style={{ textAlign: "left" }}>Fund</th>
                <th style={{ textAlign: "left" }}>Scrip</th>
                <th style={{ textAlign: "center" }}>Side</th>
                <th style={{ textAlign: "right" }}>Qty</th>
                <th style={{ textAlign: "right" }}>Price</th>
                <th style={{ textAlign: "left" }}>Counterparty</th>
                <th style={{ textAlign: "right" }}>Score</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr key={`${r.contract_number}-${r.client_code}-${r.side}`}>
                  <td className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>{r.trade_date}</td>
                  <td className="text-fg-muted" style={{ maxWidth: 150, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.client_name ?? r.client_code}</td>
                  <td><span className="mono" style={{ fontWeight: 700, color: "var(--accent)" }}>{r.scrip}</span></td>
                  <td style={{ textAlign: "center" }}><SideBadge side={r.side === "B" ? "BUY" : "SELL"} /></td>
                  <td className="mono tabular-nums" style={{ textAlign: "right" }}>{fmtN(r.our_qty)}</td>
                  <td className="mono tabular-nums" style={{ textAlign: "right" }}>{fmtN(r.our_price, 1)}</td>
                  <td className="text-fg-muted" style={{ maxWidth: 180, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.counterparty_broker_name ?? (r.counterparty_broker != null ? `#${r.counterparty_broker}` : "—")}</td>
                  <td className="mono tabular-nums" style={{ textAlign: "right", color: "var(--ink-3)" }}>{r.surveillance_score?.toFixed(0) ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length > shown.length && (
            <div style={{ padding: "12px 18px", textAlign: "center" }}>
              <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>+ {fmtN(rows.length - shown.length)} more cleared fills</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ── page ──────────────────────────────────────────────────────── */
const CASES_PER_PAGE = 5;

export default function SurveillancePage() {
  const qc = useQueryClient();
  const [filt, setFilt] = useState<string>("all");
  const [page, setPage] = useState(1);
  const [chatCase, setChatCase] = useState<SurveillanceCase | null>(null);
  // Session window — empty string = unbounded side. Server-side filter, so the
  // triage stats, cases AND clean book all narrow together.
  const [from, setFrom] = useState<string>("");
  const [to, setTo] = useState<string>("");
  const fd = from || undefined;
  const td = to || undefined;
  // Cases we've already asked the LLM about this session — never re-request.
  const requestedKeys = useRef<Set<string>>(new Set());

  const summaryQ = useQuery({ queryKey: ["surv-summary", fd, td], queryFn: () => api.surveillance.summary(fd, td), refetchInterval: 120_000 });
  const casesQ = useQuery({ queryKey: ["surv-cases", fd, td], queryFn: () => api.surveillance.cases(25, fd, td), refetchInterval: 120_000 });
  const tradesQ = useQuery({ queryKey: ["surv-trades", fd, td], queryFn: () => api.surveillance.trades({ min_score: 0, limit: 1000, from_date: fd, to_date: td }), refetchInterval: 300_000 });

  const S = summaryQ.data;
  const cases = casesQ.data ?? [];
  const cleanRows = useMemo(
    () => (tradesQ.data ?? []).filter((r) => (r.surveillance_score ?? 0) < 25),
    [tradesQ.data],
  );

  const sevCounts = useMemo(() => {
    const m: Record<Sev, number> = { high: 0, elevated: 0, moderate: 0 };
    for (const c of cases) m[sevOf(c)] += 1;
    return m;
  }, [cases]);

  const view = filt === "all" ? cases : cases.filter((c) => sevOf(c) === filt);
  const pageCount = Math.max(1, Math.ceil(view.length / CASES_PER_PAGE));
  const safePage = Math.min(page, pageCount);
  const pageCases = view.slice((safePage - 1) * CASES_PER_PAGE, safePage * CASES_PER_PAGE);
  useEffect(() => { setPage(1); }, [filt, from, to]);

  // Lazy LLM case notes: ONLY for the cases visible on the current page, and
  // only once per case per session — paging through 300 MODERATE cases costs
  // exactly the pages you actually look at.
  useEffect(() => {
    const missing = pageCases
      .filter((c) => !c.explanation && !requestedKeys.current.has(c.case_key))
      .map((c) => c.case_key);
    if (missing.length === 0) return;
    missing.forEach((k) => requestedKeys.current.add(k));
    api.surveillance
      .explain(missing)
      .then((r) => { if (r.generated > 0) qc.invalidateQueries({ queryKey: ["surv-cases"] }); })
      .catch(() => {});
  }, [pageCases, qc]);
  const total = S?.total ?? 0;
  const flaggedFills = S?.flagged ?? 0;
  // first/last_date reflect the SELECTED window; book_* are the whole book.
  const isFiltered = !!(from || to);
  const sessions = S?.book_sessions ?? [];
  const sessionLabel = S?.first_date && S?.last_date
    ? (S.first_date === S.last_date ? `Session ${S.last_date}` : `Sessions ${S.first_date} → ${S.last_date}`)
    : (isFiltered ? "No sessions in this window" : "");
  const windowSessions = sessions.filter((d) => (!from || d >= from) && (!to || d <= to)).length;

  const dateInputStyle = {
    background: "var(--panel-2)", border: "1px solid var(--line)", color: "var(--fg)",
    borderRadius: 8, padding: "5px 9px", fontSize: 12, fontFamily: "var(--font-mono)",
  };
  const presets: { label: string; active: boolean; apply: () => void }[] = [
    { label: "All", active: !isFiltered, apply: () => { setFrom(""); setTo(""); } },
    {
      label: "Latest session",
      active: !!sessions.length && from === sessions[sessions.length - 1] && to === sessions[sessions.length - 1],
      apply: () => {
        const last = sessions[sessions.length - 1];
        if (last) { setFrom(last); setTo(last); }
      },
    },
    {
      label: "Last 5 sessions",
      active: sessions.length > 5 && from === sessions[Math.max(0, sessions.length - 5)] && to === sessions[sessions.length - 1],
      apply: () => {
        if (!sessions.length) return;
        setFrom(sessions[Math.max(0, sessions.length - 5)]);
        setTo(sessions[sessions.length - 1]);
      },
    },
  ];

  return (
    <div className="h-full overflow-y-auto" style={{ background: "var(--bg)" }}>
      {/* header */}
      <div className="flex items-center justify-between px-6 py-4" style={{ borderBottom: "1px solid var(--line)", background: "var(--panel)" }}>
        <div>
          <div className="eyebrow">Internal trade book · our own fills</div>
          <h1 className="serif" style={{ fontSize: 22, fontWeight: 600, letterSpacing: "-.01em", marginTop: 2 }}>Trade Surveillance</h1>
          <p style={{ fontSize: 12.5, color: "var(--ink-3)", marginTop: 4 }}>
            Automated review of our own fills — flagging trades that warrant a closer look before they become a problem.
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
          <button onClick={() => { casesQ.refetch(); summaryQ.refetch(); tradesQ.refetch(); }} className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12.5px] font-semibold"
            style={{ background: "var(--panel-2)", color: "var(--ink-2)", border: "1px solid var(--line)" }}>
            <RefreshCw className="h-3.5 w-3.5" strokeWidth={2} /> Refresh scan
          </button>
          <LoadTradebookButton />
        </div>
      </div>

      <div className="px-6 py-6" style={{ display: "flex", flexDirection: "column", gap: "var(--gap)" }}>
        {/* session window — server-side date filter over triage stats, cases & clean book */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <span className="eyebrow">Session window</span>
          <input type="date" value={from} min={S?.book_first_date ?? undefined} max={to || S?.book_last_date || undefined}
            onChange={(e) => setFrom(e.target.value)} style={dateInputStyle} aria-label="From date" />
          <span style={{ color: "var(--ink-3)" }}>→</span>
          <input type="date" value={to} min={from || S?.book_first_date || undefined} max={S?.book_last_date ?? undefined}
            onChange={(e) => setTo(e.target.value)} style={dateInputStyle} aria-label="To date" />
          <div style={{ display: "flex", gap: 7 }}>
            {presets.map((p) => (
              <button key={p.label} onClick={p.apply} className="mono"
                style={{ font: "inherit", cursor: "pointer", fontFamily: "var(--font-mono)", fontSize: 11, padding: "5px 11px", borderRadius: 999,
                  color: p.active ? "var(--accent)" : "var(--ink-3)",
                  border: `1px solid ${p.active ? "var(--accent)" : "var(--line)"}`,
                  background: p.active ? "color-mix(in oklab, var(--accent) 14%, transparent)" : "transparent" }}>
                {p.label}
              </button>
            ))}
          </div>
          {isFiltered && (
            <span className="mono" style={{ fontSize: 11, color: "var(--accent)" }}>
              viewing {windowSessions} of {S?.book_n_sessions ?? "—"} sessions
              {" · "}
              <button onClick={() => { setFrom(""); setTo(""); }} style={{ font: "inherit", cursor: "pointer", color: "var(--accent)", textDecoration: "underline" }}>
                clear
              </button>
            </span>
          )}
          {!isFiltered && S?.book_first_date && S?.book_last_date && (
            <span className="mono" style={{ fontSize: 11, color: "var(--ink-4)" }}>
              book covers {S.book_first_date} → {S.book_last_date} · {S.book_n_sessions} sessions
            </span>
          )}
        </div>

        {/* triage command strip */}
        <div className="panel" style={{ padding: 0, boxShadow: "var(--shadow)", overflow: "hidden", position: "relative" }}>
          {/* top accent hairline */}
          <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 2, background: "linear-gradient(90deg, transparent, color-mix(in oklab, var(--accent) 55%, transparent), color-mix(in oklab, var(--accent-2) 45%, transparent), transparent)" }} />
          <div style={{ display: "grid", gridTemplateColumns: "auto 1fr auto", gap: 0, alignItems: "stretch" }}>
            {/* book-health gauge */}
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 10, padding: "22px 28px", borderRight: "1px solid var(--line)" }}>
              <HealthRing pct={S?.clean_rate ?? null} flagged={flaggedFills} total={total} />
              <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                <span className="statusdot" style={{ background: "var(--ok)", boxShadow: "0 0 6px var(--ok)" }} />
                <span className="mono" style={{ fontSize: 10.5, color: "var(--ink-3)" }}>
                  {cases.length} case{cases.length === 1 ? "" : "s"} need review
                </span>
              </div>
            </div>
            {/* composition + sessions */}
            <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", gap: 16, padding: "22px 28px" }}>
              <CompositionBar byTier={S?.by_tier ?? {}} total={total} />
              <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11.5, color: "var(--ink-3)" }}>
                <Activity size={13} strokeWidth={1.75} style={{ color: "var(--ink-3)", flexShrink: 0 }} />
                <span>{sessionLabel || "—"}</span>
                {windowSessions > 0 && S?.book_n_sessions != null && (
                  <span className="mono" style={{ color: "var(--ink-4)" }}>· {windowSessions}/{S.book_n_sessions} sessions</span>
                )}
              </div>
            </div>
            {/* metric tiles */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gridAutoRows: "min-content", gap: 10, padding: "20px 22px", borderLeft: "1px solid var(--line)", alignContent: "center", minWidth: 320 }}>
              <MetricTile label="Flagged notional" value={lakh(S?.flagged_notional)} sub={`across ${cases.length} case${cases.length === 1 ? "" : "s"}`} tone="var(--accent)" />
              <MetricTile label="Funds monitored" value={S?.n_funds ?? "—"} sub={S?.by_client?.[0]?.client_name ?? undefined} />
              <MetricTile label="Sessions scanned" value={windowSessions || S?.book_n_sessions || "—"} sub={S?.last_date ? `latest ${S.last_date}` : undefined} />
              <MetricTile label="Last auto-scan" value={S?.computed_at ? new Date(S.computed_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—"} sub={S?.computed_at ? new Date(S.computed_at).toLocaleDateString() : "scan complete"} />
            </div>
          </div>
        </div>

        {/* cases header + severity filter */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
          <div>
            <div className="eyebrow">Cases requiring review</div>
            <h2 style={{ margin: "4px 0 0", fontSize: 19, fontWeight: 600 }}>Investigate before acting</h2>
          </div>
          <div style={{ display: "flex", gap: 7 }}>
            {([["all", "All", cases.length], ["high", "High", sevCounts.high], ["elevated", "Elevated", sevCounts.elevated], ["moderate", "Moderate", sevCounts.moderate]] as [string, string, number][]).map(([k, l, n]) => {
              const c = k === "all" ? "var(--accent)" : SEVC[k];
              const active = filt === k;
              const dim = k !== "all" && n === 0;
              return (
                <button key={k} onClick={() => setFilt(k)} className="mono" disabled={dim} style={{ font: "inherit", cursor: dim ? "default" : "pointer", fontFamily: "var(--font-mono)", fontSize: 11, padding: "6px 12px", borderRadius: 999, display: "inline-flex", alignItems: "center", gap: 7, opacity: dim ? 0.4 : 1, color: active ? c : "var(--ink-3)", border: `1px solid ${active ? c : "var(--line)"}`, background: active ? `color-mix(in oklab, ${c} 14%, transparent)` : "transparent" }}>
                  {k !== "all" && <span style={{ width: 6, height: 6, borderRadius: 99, background: c, boxShadow: active ? `0 0 5px ${c}` : "none" }} />}
                  {l}
                  <span style={{ fontWeight: 700, color: active ? c : "var(--ink-2)" }}>{n}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* case cards (paginated — LLM notes generate only for the visible page) */}
        {casesQ.isLoading ? (
          <div className="panel" style={{ padding: 40, textAlign: "center", color: "var(--ink-3)" }}>Scanning the trade book…</div>
        ) : view.length === 0 ? (
          <div className="panel" style={{ padding: 40, textAlign: "center", color: "var(--ink-3)" }}>
            {cases.length === 0 ? "No cases need review — the book is clean." : "No cases at this severity."}
          </div>
        ) : (
          pageCases.map((c, i) => <CaseCard key={c.case_key} c={c} defaultOpen={safePage === 1 && i === 0} onChat={setChatCase} />)
        )}

        {pageCount > 1 && (
          <div className="flex items-center justify-center gap-3">
            <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={safePage <= 1}
              className="rounded-lg px-3 py-1.5 text-[12px] font-semibold disabled:opacity-40"
              style={{ background: "var(--panel-2)", color: "var(--ink-2)", border: "1px solid var(--line)" }}>
              ← Prev
            </button>
            <span className="eyebrow">Page {safePage} of {pageCount} · {view.length} cases</span>
            <button onClick={() => setPage((p) => Math.min(pageCount, p + 1))} disabled={safePage >= pageCount}
              className="rounded-lg px-3 py-1.5 text-[12px] font-semibold disabled:opacity-40"
              style={{ background: "var(--panel-2)", color: "var(--ink-2)", border: "1px solid var(--line)" }}>
              Next →
            </button>
          </div>
        )}

        {/* clean book */}
        {cleanRows.length > 0 && <CleanBook rows={cleanRows} />}

        <p className="text-[11px]" style={{ color: "var(--ink-3)" }}>
          Slippage is measured against the prevailing market (±15-min interval VWAP, day VWAP fallback) in units of each scrip&apos;s own
          volatility. Markout is the post-trade price drift — negative means the price moved against the side we took. Counterparty
          concentration compares how often a broker faced our flow vs its actual market share (z ≥ 3 ≈ very unlikely by chance).
          Case notes are model-written summaries of the quantitative flags. A flag for review, not a verdict.
        </p>
      </div>

      {/* floating per-case analyst chat */}
      {chatCase && <CaseChatPanel key={chatCase.case_key} c={chatCase} onClose={() => setChatCase(null)} />}
    </div>
  );
}
