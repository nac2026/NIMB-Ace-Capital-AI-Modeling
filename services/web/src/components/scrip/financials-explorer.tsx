"use client";

// Multi-period financials explorer (Fiscal.ai-style): line items as rows,
// quarters as columns, with Absolute / QoQ% / YoY% value modes and a period
// selector. Built from the existing fundamentals-history endpoint — no extra
// backend. Sparse sectors render whatever line items they have.

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type FundamentalsHistoryRow } from "@/lib/api";
import { Panel, EmptyState, LoadingState, quarterLabel } from "./primitives";
import { cn } from "@/lib/utils";

type Mode = "abs" | "qoq" | "yoy";
type Fmt = "npr" | "pct" | "x" | "rs";

type Line = { key: keyof FundamentalsHistoryRow; label: string; fmt: Fmt };
type Section = { title: string; lines: Line[] };

const SECTIONS: Section[] = [
  { title: "Income", lines: [
    { key: "net_profit", label: "Net profit", fmt: "npr" },
    { key: "operating_profit", label: "Operating profit", fmt: "npr" },
    { key: "net_interest_income", label: "Net interest income", fmt: "npr" },
  ]},
  { title: "Balance sheet", lines: [
    { key: "total_deposits", label: "Total deposits", fmt: "npr" },
    { key: "total_loans", label: "Total loans", fmt: "npr" },
  ]},
  { title: "Per share", lines: [
    { key: "eps", label: "EPS", fmt: "rs" },
    { key: "bvps", label: "BVPS", fmt: "rs" },
  ]},
  { title: "Profitability & quality", lines: [
    { key: "roe", label: "ROE", fmt: "pct" },
    { key: "roa", label: "ROA", fmt: "pct" },
    { key: "npl_ratio", label: "NPL ratio", fmt: "pct" },
    { key: "car", label: "CAR", fmt: "pct" },
    { key: "cd_ratio", label: "CD ratio", fmt: "pct" },
  ]},
  { title: "Valuation", lines: [
    { key: "pe_ratio", label: "P/E", fmt: "x" },
    { key: "pb_ratio", label: "P/B", fmt: "x" },
  ]},
];

function fmtVal(v: number | null | undefined, fmt: Fmt): string {
  if (v == null) return "—";
  if (fmt === "npr") {
    const a = Math.abs(v);
    if (a >= 1e9) return (v / 1e9).toFixed(2) + "B";
    if (a >= 1e6) return (v / 1e6).toFixed(1) + "M";
    return Math.round(v).toLocaleString("en-US");
  }
  if (fmt === "pct") return (v <= 1 && v >= -1 ? v * 100 : v).toFixed(2) + "%";
  if (fmt === "x") return v.toFixed(1) + "×";
  return v.toFixed(2); // rs
}

function changePct(cur: number | null | undefined, base: number | null | undefined): number | null {
  if (cur == null || base == null || base === 0) return null;
  return (cur - base) / Math.abs(base) * 100;
}

export function FinancialsExplorer({ scrip }: { scrip: string }) {
  const [mode, setMode] = useState<Mode>("abs");
  const [nQ, setNQ] = useState(8);
  const q = useQuery({
    queryKey: ["fundamentals-history", scrip, 20],
    queryFn: () => api.scrip.fundamentalsHistory(scrip, 20),
  });

  // Endpoint returns chronological asc; show most-recent-first columns.
  const all = q.data ?? [];
  const rows = all.slice(-nQ).reverse();           // newest first
  const byIdx = (i: number) => rows[i];

  return (
    <Panel
      title="Financials"
      hint={mode === "abs" ? "NPR amounts in B/M · Rs per-share" : mode === "qoq" ? "quarter-over-quarter %" : "year-over-year %"}
      right={
        <div className="flex items-center gap-2">
          <Seg value={mode} onChange={setMode} options={[["abs", "Value"], ["qoq", "QoQ %"], ["yoy", "YoY %"]]} />
          <Seg value={String(nQ)} onChange={(v) => setNQ(Number(v))} options={[["8", "8Q"], ["12", "12Q"], ["20", "20Q"]]} />
        </div>
      }
    >
      {q.isLoading ? <LoadingState rows={6} /> : !rows.length ? (
        <EmptyState message="No fundamentals history for this scrip." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                <th className="sticky left-0 z-10 bg-bg-panel py-2 pr-3 text-left text-[10.5px] font-semibold uppercase tracking-wider text-fg-dim">
                  Line item
                </th>
                {rows.map((r) => (
                  <th key={`${r.fiscal_year_bs}-${r.quarter}`} className="px-3 py-2 text-right text-[11px] font-semibold text-fg-muted whitespace-nowrap">
                    {quarterLabel(r.fiscal_year_bs, r.quarter)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {SECTIONS.map((sec) => {
                // skip sections with no data across all visible quarters
                const hasData = sec.lines.some((ln) => rows.some((r) => r[ln.key] != null));
                if (!hasData) return null;
                return (
                  <FragmentSection key={sec.title} title={sec.title} cols={rows.length + 1}>
                    {sec.lines.map((ln) => {
                      if (!rows.some((r) => r[ln.key] != null)) return null;
                      return (
                        <tr key={String(ln.key)} className="hover:bg-bg-hover">
                          <td className="sticky left-0 z-10 bg-bg-panel py-1.5 pr-3 text-fg">{ln.label}</td>
                          {rows.map((r, i) => {
                            const cur = r[ln.key] as number | null;
                            let display: string;
                            let tone = "";
                            if (mode === "abs") {
                              display = fmtVal(cur, ln.fmt);
                            } else {
                              const baseRow = mode === "qoq" ? byIdx(i + 1) : byIdx(i + 4);
                              const ch = changePct(cur, baseRow ? (baseRow[ln.key] as number | null) : null);
                              display = ch == null ? "—" : `${ch >= 0 ? "+" : ""}${ch.toFixed(1)}%`;
                              tone = ch == null ? "" : ch >= 0 ? "text-ok" : "text-err";
                            }
                            return <td key={i} className={cn("px-3 py-1.5 text-right num", tone)}>{display}</td>;
                          })}
                        </tr>
                      );
                    })}
                  </FragmentSection>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function FragmentSection({ title, cols, children }: { title: string; cols: number; children: React.ReactNode }) {
  return (
    <>
      <tr>
        <td colSpan={cols} className="sticky left-0 bg-bg-panel pt-3 pb-1 text-[10.5px] font-semibold uppercase tracking-wider" style={{ color: "var(--brand)" }}>
          {title}
        </td>
      </tr>
      {children}
    </>
  );
}

function Seg<T extends string>({ value, onChange, options }: {
  value: T; onChange: (v: T) => void; options: [T, string][];
}) {
  return (
    <div className="inline-flex rounded-md p-0.5" style={{ background: "var(--bg-hover)" }}>
      {options.map(([v, label]) => (
        <button key={v} onClick={() => onChange(v)}
          className={cn("rounded px-2 py-0.5 text-[11px] font-medium transition-colors",
            value === v ? "text-fg" : "text-fg-muted hover:text-fg")}
          style={value === v ? { background: "var(--bg-panel)" } : undefined}>
          {label}
        </button>
      ))}
    </div>
  );
}
