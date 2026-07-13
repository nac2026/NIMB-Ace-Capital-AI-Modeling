"use client";

import { Info } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { AccumBars, npr, type AccumRow } from "@/components/viz";
import { LoadingState } from "./primitives";

function shares(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v >= 1e7) return `${(v / 1e7).toFixed(2)} Cr`;
  if (v >= 1e5) return `${(v / 1e5).toFixed(1)} L`;
  return npr(v);
}
function rs(v: number | null | undefined): string {
  if (v == null) return "—";
  if (Math.abs(v) >= 1e9) return `Rs ${(v / 1e9).toFixed(2)}B`;
  if (Math.abs(v) >= 1e7) return `Rs ${(v / 1e7).toFixed(2)} Cr`;
  return `Rs ${npr(v)}`;
}

export function TabOwnership({ scrip }: { scrip: string }) {
  const profile = useQuery({ queryKey: ["scrip-profile", scrip], queryFn: () => api.scrip.profile(scrip) });
  const fs = useQuery({ queryKey: ["floorsheet", scrip], queryFn: () => api.scrip.floorsheet(scrip) });

  const p = profile.data;
  const d = fs.data;

  const accumRows: AccumRow[] = [
    ...(d?.top_accumulators ?? []).slice(0, 6).map((r) => ({ broker: `#${r.broker}`, buy: Math.abs(r.cum_net_qty ?? 0), sell: 0 })),
    ...(d?.top_distributors ?? []).slice(0, 6).map((r) => ({ broker: `#${r.broker}`, buy: 0, sell: Math.abs(r.cum_net_qty ?? 0) })),
  ];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1.3fr", gap: "var(--gap)", alignItems: "start" }}>
      {/* Share structure (what we hold) + shareholding-pending note */}
      <Card>
        <SectionTitle sub="Capital & float — from the NEPSE listing master">Share structure</SectionTitle>
        {profile.isLoading ? (
          <LoadingState rows={3} />
        ) : !p ? (
          <Empty msg="No listing data." />
        ) : (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 22px" }}>
              <Field label="Listed shares" value={shares(p.listed_shares)} />
              <Field label="Shares outstanding" value={shares(p.shares_outstanding)} />
              <Field label="Paid-up capital" value={rs(p.paid_up_capital)} />
              <Field label="Face value" value={p.paid_up_value != null ? `Rs ${p.paid_up_value}` : "—"} />
              <Field label="Market cap" value={rs(p.market_cap_npr)} />
              <Field label="Size tier" value={p.market_cap_tier ?? "—"} />
            </div>
            <div style={{ display: "flex", gap: 10, alignItems: "flex-start", marginTop: 16, padding: 12, borderRadius: 10, background: "var(--panel-2)", border: "1px solid var(--line-soft)" }}>
              <Info className="h-4 w-4 shrink-0" style={{ color: "var(--accent)", marginTop: 1 }} />
              <p style={{ margin: 0, fontSize: 11.5, lineHeight: 1.5, color: "var(--ink-2)" }}>
                Promoter / public / foreign shareholding breakdown and top-holder categories are not in the current SMTM data feed — they have been requested from the provider. Until then, ownership is read from <b style={{ color: "var(--ink)" }}>broker activity</b> on the floor-sheet (right).
              </p>
            </div>
          </>
        )}
      </Card>

      {/* Broker accumulation & distribution (real, from floorsheet) */}
      <Card>
        <SectionTitle sub="Net broker activity in this scrip · loaded window">Broker accumulation &amp; distribution</SectionTitle>
        {fs.isLoading ? (
          <LoadingState rows={5} />
        ) : accumRows.length === 0 ? (
          <Empty msg="No floor-sheet broker flow for this scrip yet." />
        ) : (
          <>
            <AccumBars rows={accumRows} w={520} />
            {d?.speculation && (
              <div style={{ display: "flex", gap: 18, flexWrap: "wrap", marginTop: 16, paddingTop: 14, borderTop: "1px dashed var(--line)" }}>
                <Mini label="Speculation score" value={d.speculation.speculation_score != null ? `${d.speculation.speculation_score.toFixed(1)}/100` : "—"} tone={(d.speculation.speculation_score ?? 0) >= 70 ? "var(--neg)" : (d.speculation.speculation_score ?? 0) >= 45 ? "var(--warn)" : "var(--ink)"} />
                <Mini label="1-broker accum." value={d.speculation.c_accumulation != null ? `${(d.speculation.c_accumulation * 100).toFixed(0)}%` : "—"} />
                <Mini label="Self-trade" value={d.speculation.has_self_trade ? "Detected" : "None"} tone={d.speculation.has_self_trade ? "var(--neg)" : "var(--pos)"} />
              </div>
            )}
          </>
        )}
      </Card>
    </div>
  );
}

function SectionTitle({ children, sub }: { children: React.ReactNode; sub?: string }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <h3 className="serif" style={{ margin: 0, fontSize: 19, fontWeight: 600, letterSpacing: "-.01em" }}>{children}</h3>
      {sub && <p style={{ margin: "3px 0 0", fontSize: 12.5, color: "var(--ink-3)" }}>{sub}</p>}
    </div>
  );
}
function Card({ children }: { children: React.ReactNode }) {
  return <div style={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: 16, padding: 20 }}>{children}</div>;
}
function Field({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 3, padding: "11px 0", borderBottom: "1px solid var(--line-soft)" }}>
      <span style={{ fontSize: 11.5, color: "var(--ink-3)" }}>{label}</span>
      <span style={{ fontSize: 14, fontWeight: 500, color: "var(--ink)" }}>{value}</span>
    </div>
  );
}
function Mini({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <div className="eyebrow">{label}</div>
      <div className="mono tnum" style={{ fontSize: 15, fontWeight: 600, marginTop: 3, color: tone ?? "var(--ink)" }}>{value}</div>
    </div>
  );
}
function Empty({ msg }: { msg: string }) {
  return <div className="py-8 text-center text-[12.5px] text-fg-muted">{msg}</div>;
}
