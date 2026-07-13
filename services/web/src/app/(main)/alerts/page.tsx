"use client";
// Surveillance Alerts — the "view all" board for the alert engine. All detector
// types (speculation, pump, insider, ring, volume, distribution), sorted by
// score (high→low), flagged by severity, filterable by type, status, date range.

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { api, type AlertRow } from "@/lib/api";

type StatusFilter = "active" | "all";

// Per detector type: label + accent colour.
const TYPE_META: Record<string, { label: string; color: string }> = {
  spec:    { label: "Speculation",  color: "var(--accent)" },
  pump:    { label: "Pump-and-dump", color: "#e5575c" },
  insider: { label: "Pre-event",    color: "var(--accent-2)" },
  ring:    { label: "Wash / ring",  color: "#e8884e" },
  volume:  { label: "Abnormal vol", color: "#38c6cf" },
  dist:    { label: "Distribution", color: "#e6a93b" },
  surv:    { label: "Internal trade", color: "#a78bfa" },
};
const TYPE_ORDER = ["surv", "spec", "pump", "insider", "ring", "volume", "dist"];

function typeLabel(t: string) { return TYPE_META[t]?.label ?? t; }
function typeColor(t: string) { return TYPE_META[t]?.color ?? "var(--ink-3)"; }

// Severity flag derived from the composite score (mirrors the alert email).
function sevByScore(score: number | null): { label: string; color: string } {
  const s = score ?? 0;
  if (s >= 70) return { label: "CRITICAL", color: "#e5575c" };
  if (s >= 55) return { label: "ELEVATED", color: "#e8884e" };
  if (s >= 45) return { label: "WATCH", color: "#e6a93b" };
  return { label: "LOW", color: "var(--ink-3)" };
}

function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const mins = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (isNaN(mins)) return "—";
  if (mins < 60) return `${mins}m ago`;
  if (mins < 1440) return `${Math.floor(mins / 60)}h ago`;
  return `${Math.floor(mins / 1440)}d ago`;
}
function dayOf(iso: string | null): string { return iso ? new Date(iso).toISOString().slice(0, 10) : ""; }

export default function AlertsPage() {
  const router = useRouter();
  const [status, setStatus] = useState<StatusFilter>("active");
  const [typeF, setTypeF] = useState<string>("all");
  const [from, setFrom] = useState<string>("");
  const [to, setTo] = useState<string>("");
  const q = useQuery({ queryKey: ["alerts-all"], queryFn: () => api.alerts.recent(200), refetchInterval: 120_000 });
  const rows = q.data ?? [];

  // rows after status + date filters (type counts computed from this set)
  const scoped = useMemo(() => {
    let v = status === "active" ? rows.filter((r) => !r.cleared_at) : rows;
    if (from) v = v.filter((r) => dayOf(r.first_seen_at) >= from);
    if (to) v = v.filter((r) => dayOf(r.first_seen_at) <= to);
    return v;
  }, [rows, status, from, to]);

  const typeCounts = useMemo(() => {
    const m: Record<string, number> = {};
    for (const r of scoped) m[r.alert_type] = (m[r.alert_type] ?? 0) + 1;
    return m;
  }, [scoped]);

  const view = useMemo(() => {
    let v = typeF === "all" ? scoped : scoped.filter((r) => r.alert_type === typeF);
    return [...v].sort((a, b) => (b.score ?? -1) - (a.score ?? -1)); // score high→low
  }, [scoped, typeF]);

  const inputStyle: React.CSSProperties = {
    background: "var(--panel-2)", border: "1px solid var(--line)", color: "var(--fg)",
    borderRadius: 8, padding: "5px 9px", fontSize: 12, fontFamily: "var(--font-mono)",
  };

  return (
    <div className="h-full overflow-y-auto" style={{ background: "var(--bg)" }}>
      <div className="flex items-center justify-between px-6 py-4" style={{ borderBottom: "1px solid var(--line)", background: "var(--panel)" }}>
        <div>
          <div className="eyebrow">Floor-sheet surveillance · all sectors</div>
          <h1 className="serif" style={{ fontSize: 22, fontWeight: 600, letterSpacing: "-.01em", marginTop: 2 }}>Surveillance Alerts</h1>
        </div>
        <button onClick={() => q.refetch()} className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12.5px] font-semibold"
          style={{ background: "var(--panel-2)", color: "var(--ink-2)", border: "1px solid var(--line)" }}>
          <RefreshCw className="h-3.5 w-3.5" strokeWidth={2} /> Refresh
        </button>
      </div>

      <div className="px-6 py-6" style={{ display: "flex", flexDirection: "column", gap: "var(--gap)" }}>
        {/* type chips */}
        <div className="flex flex-wrap gap-2">
          <TypeChip id="all" label={`All (${scoped.length})`} active={typeF === "all"} color="var(--accent)" onClick={() => setTypeF("all")} />
          {TYPE_ORDER.map((t) => (
            <TypeChip key={t} id={t} label={`${TYPE_META[t].label} (${typeCounts[t] ?? 0})`} active={typeF === t} color={TYPE_META[t].color} onClick={() => setTypeF(t)} />
          ))}
        </div>

        {/* status + date range */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <div className="flex gap-2">
            {([["active", "Active"], ["all", "All (incl. cleared)"]] as [StatusFilter, string][]).map(([id, label]) => (
              <button key={id} onClick={() => setStatus(id)} className="rounded-lg px-3 py-1.5 text-[12px] font-semibold"
                style={{ background: status === id ? "var(--accent)" : "var(--panel-2)", color: status === id ? "var(--bg)" : "var(--ink-2)", border: "1px solid var(--line)" }}>
                {label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <span className="eyebrow">First seen</span>
            <input type="date" value={from} max={to || undefined} onChange={(e) => setFrom(e.target.value)} style={inputStyle} aria-label="From date" />
            <span style={{ color: "var(--ink-3)" }}>→</span>
            <input type="date" value={to} min={from || undefined} onChange={(e) => setTo(e.target.value)} style={inputStyle} aria-label="To date" />
            {(from || to) && <button onClick={() => { setFrom(""); setTo(""); }} className="text-[11.5px]" style={{ color: "var(--accent)" }}>clear</button>}
          </div>
          <div className="flex-1" />
          <span className="eyebrow">{view.length} shown · sorted by score</span>
        </div>

        {/* table */}
        <div className="panel overflow-hidden">
          {q.isLoading ? (
            <div className="px-4 py-10 text-center text-[13px] text-fg-muted">Loading alerts…</div>
          ) : view.length === 0 ? (
            <div className="px-4 py-10 text-center text-[13px] text-fg-muted">No alerts match these filters.</div>
          ) : (
            <table className="tbl">
              <thead>
                <tr>
                  <th style={{ textAlign: "left", width: 36 }}>#</th>
                  <th style={{ textAlign: "left" }}>Scrip</th>
                  <th style={{ textAlign: "left" }}>Company</th>
                  <th style={{ textAlign: "left" }}>Type</th>
                  <th style={{ textAlign: "left" }}>Risk</th>
                  <th style={{ textAlign: "left" }}>Signal</th>
                  <th style={{ textAlign: "right" }}>Score ↓</th>
                  <th style={{ textAlign: "right" }}>First seen</th>
                  <th style={{ textAlign: "center" }}>State</th>
                </tr>
              </thead>
              <tbody>
                {view.map((a, i) => {
                  const sev = sevByScore(a.score);
                  const tc = typeColor(a.alert_type);
                  return (
                    <tr key={a.signal_key + (a.first_seen_at ?? "")} style={{ cursor: "pointer", opacity: a.cleared_at ? 0.55 : 1 }}
                        onClick={() => router.push(`/scrip/${a.scrip}#floorsheet`)}>
                      <td className="mono" style={{ color: "var(--ink-3)", fontSize: 11 }}>{(i + 1).toString().padStart(2, "0")}</td>
                      <td><span className="mono" style={{ fontWeight: 700, color: "var(--accent)" }}>{a.scrip}</span></td>
                      <td className="text-fg-muted" style={{ maxWidth: 170, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{a.company_name ?? "—"}</td>
                      <td><span className="mono" style={{ fontSize: 10.5, fontWeight: 600, color: tc }}>{typeLabel(a.alert_type)}</span></td>
                      <td>
                        <span className="mono" style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".06em", padding: "2px 8px", borderRadius: 999, color: sev.color, border: `1px solid ${sev.color}`, background: `color-mix(in oklab, ${sev.color} 12%, transparent)` }}>{sev.label}</span>
                      </td>
                      <td className="text-fg-muted" style={{ maxWidth: 320, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{a.detail ?? a.title}</td>
                      <td className="mono tabular-nums" style={{ textAlign: "right", fontWeight: 700, color: sev.color }}>{a.score != null ? a.score.toFixed(0) : "—"}</td>
                      <td className="mono" style={{ textAlign: "right", color: "var(--ink-3)", fontSize: 11 }}>{timeAgo(a.first_seen_at)}</td>
                      <td style={{ textAlign: "center" }}>
                        <span className="mono" style={{ fontSize: 9.5, padding: "2px 7px", borderRadius: 999, textTransform: "uppercase", letterSpacing: ".05em",
                          color: a.cleared_at ? "var(--ink-3)" : "var(--ok)", border: `1px solid ${a.cleared_at ? "var(--line)" : "var(--ok)"}` }}>
                          {a.cleared_at ? "cleared" : "active"}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

function TypeChip({ id, label, active, color, onClick }: { id: string; label: string; active: boolean; color: string; onClick: () => void }) {
  return (
    <button key={id} onClick={onClick} className="rounded-lg px-3 py-1.5 text-[12px] font-semibold inline-flex items-center gap-1.5"
      style={{ background: active ? color : "var(--panel-2)", color: active ? "var(--bg)" : "var(--ink-2)", border: "1px solid var(--line)" }}>
      <span style={{ width: 7, height: 7, borderRadius: 99, background: active ? "var(--bg)" : color, opacity: active ? 0.7 : 1 }} />
      {label}
    </button>
  );
}
