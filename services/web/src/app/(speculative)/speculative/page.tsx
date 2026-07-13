"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Plus, Download, FileSpreadsheet, Calendar, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";
import { FlagDistributionBar } from "@/components/speculative/flag-distribution-bar";

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      day: "2-digit", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}

function StatusPill({ status }: { status: string }) {
  const map: Record<string, { bg: string; fg: string; label: string }> = {
    succeeded: { bg: "var(--ok)",   fg: "#ffffff", label: "Complete" },
    running:   { bg: "var(--brand)", fg: "#ffffff", label: "Running" },
    pending:   { bg: "var(--fg-dim)", fg: "#ffffff", label: "Pending" },
    partial:   { bg: "var(--warn)", fg: "#1c2331", label: "Partial" },
    failed:    { bg: "var(--err)",  fg: "#ffffff", label: "Failed" },
  };
  const s = map[status] || map.pending;
  return (
    <span
      className="inline-flex items-center rounded-md px-2 py-0.5 text-[10px] font-semibold uppercase tracking-widest"
      style={{ background: s.bg, color: s.fg }}
    >
      {s.label}
    </span>
  );
}

export default function SpeculativeDashboardPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["speculative", "sessions"],
    queryFn: () => api.speculative.listSessions(),
    refetchOnWindowFocus: false,
  });

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[1100px] px-8 py-10">
        <div className="mb-8 flex items-start justify-between gap-6">
          <div>
            <h1 className="text-[28px] font-semibold tracking-tight text-fg">
              Speculative Analysis
            </h1>
            <p className="mt-1.5 text-[14px] text-fg-muted">
              Upload a shortlist your research team prepared. Get per-ticker red / amber / green flags
              plus an LLM-written executive brief. Sessions persist — return any day to review.
            </p>
          </div>
          <Link
            href="/speculative/new"
            className="inline-flex shrink-0 items-center gap-1.5 rounded-md px-4 py-2.5 text-[13px] font-semibold transition-all hover:opacity-90"
            style={{ background: "var(--brand)", color: "#ffffff", boxShadow: "var(--shadow-sm)" }}
          >
            <Plus className="h-4 w-4" strokeWidth={2.25} />
            New analysis
          </Link>
        </div>

        {isLoading && (
          <div className="panel p-12 text-center text-fg-muted text-[13px]">Loading past analyses…</div>
        )}

        {error && (
          <div className="panel p-8 text-center" style={{ borderColor: "var(--err)" }}>
            <AlertCircle className="mx-auto h-6 w-6" style={{ color: "var(--err)" }} strokeWidth={1.75} />
            <p className="mt-2 text-[13px]" style={{ color: "var(--err)" }}>
              Failed to load sessions. Is the backend running?
            </p>
          </div>
        )}

        {!isLoading && !error && (data?.length ?? 0) === 0 && (
          <div className="panel flex flex-col items-center justify-center gap-3 px-8 py-20 text-center">
            <FileSpreadsheet className="h-12 w-12" style={{ color: "var(--brand)" }} strokeWidth={1.25} />
            <h2 className="text-[18px] font-semibold tracking-tight text-fg">No analyses yet</h2>
            <p className="max-w-md text-[13px] text-fg-muted">
              Upload a CSV or Excel file with a column named <code className="rounded bg-bg-subtle px-1.5 py-0.5 font-mono text-[11.5px]">scrip</code> /
              <code className="rounded bg-bg-subtle px-1.5 py-0.5 font-mono text-[11.5px]">ticker</code> listing the banks the research team
              wants reviewed.
            </p>
            <div className="mt-3 flex gap-3">
              <Link
                href="/speculative/new"
                className="inline-flex items-center gap-1.5 rounded-md px-4 py-2 text-[12.5px] font-semibold transition-opacity hover:opacity-90"
                style={{ background: "var(--brand)", color: "#ffffff" }}
              >
                <Plus className="h-3.5 w-3.5" strokeWidth={2.25} />
                Upload first shortlist
              </Link>
              <a
                href={api.speculative.sampleTemplateUrl()}
                download
                className="inline-flex items-center gap-1.5 rounded-md px-4 py-2 text-[12.5px] font-medium text-fg-muted transition-colors hover:bg-bg-hover hover:text-fg"
              >
                <Download className="h-3.5 w-3.5" strokeWidth={2} />
                Download CSV template
              </a>
            </div>
          </div>
        )}

        {!isLoading && !error && (data?.length ?? 0) > 0 && (
          <div className="panel overflow-hidden">
            <table className="tbl">
              <thead>
                <tr>
                  <th>Title</th>
                  <th style={{ width: 110 }}>Tickers</th>
                  <th style={{ width: 200 }}>Flag distribution</th>
                  <th style={{ width: 110 }}>Status</th>
                  <th style={{ width: 170 }}>Created</th>
                </tr>
              </thead>
              <tbody>
                {data!.map((s) => (
                  <tr
                    key={s.session_id}
                    className="cursor-pointer"
                    onClick={() => { window.location.href = `/speculative/analysis/${s.session_id}`; }}
                  >
                    <td>
                      <div className="font-medium text-fg" style={{ color: "var(--brand)" }}>{s.title}</div>
                      {s.notes && <div className="mt-0.5 text-[11.5px] text-fg-muted truncate max-w-[420px]">{s.notes}</div>}
                    </td>
                    <td className="mono num">{s.n_tickers}</td>
                    <td>
                      <FlagDistributionBar
                        green={s.n_green}
                        amber={s.n_amber}
                        red={s.n_red}
                        unknown={s.n_unknown}
                      />
                      <div className="mt-1 flex gap-2 text-[10.5px] text-fg-muted">
                        <span>{s.n_green}G</span>
                        <span>{s.n_amber}A</span>
                        <span>{s.n_red}R</span>
                        {s.n_unknown > 0 && <span>{s.n_unknown}?</span>}
                      </div>
                    </td>
                    <td><StatusPill status={s.status} /></td>
                    <td>
                      <div className="flex items-center gap-1.5 text-[12px] text-fg-muted">
                        <Calendar className="h-3 w-3" strokeWidth={1.75} />
                        <span className="num">{fmtDate(s.created_at)}</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
