"use client";

import { Trash2, Calendar, Hash } from "lucide-react";
import type { SpeculativeSessionDetail } from "@/lib/api";

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      day: "2-digit", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}

export function AnalysisSummaryHeader({
  detail,
  onDelete,
}: {
  detail: SpeculativeSessionDetail;
  onDelete?: () => void;
}) {
  const s = detail.session;
  return (
    <div className="mb-6 panel p-6">
      <div className="flex items-start justify-between gap-6">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h1 className="truncate text-[24px] font-semibold tracking-tight text-fg">
              {s.title}
            </h1>
          </div>
          {s.notes && <p className="mt-1 text-[13px] text-fg-muted">{s.notes}</p>}
          <div className="mt-3 flex flex-wrap items-center gap-4 text-[12px] text-fg-muted">
            <span className="inline-flex items-center gap-1.5">
              <Calendar className="h-3.5 w-3.5" strokeWidth={1.75} />
              <span className="num">{fmtDate(s.created_at)}</span>
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Hash className="h-3.5 w-3.5" strokeWidth={1.75} />
              <span className="num">{s.n_tickers} tickers</span>
            </span>
          </div>
        </div>

        {onDelete && (
          <button
            onClick={onDelete}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-md px-3 py-2 text-[12px] text-fg-muted transition-colors hover:bg-bg-hover"
            style={{ color: "var(--err)" }}
            title="Delete this analysis"
          >
            <Trash2 className="h-3.5 w-3.5" strokeWidth={1.75} />
            Delete
          </button>
        )}
      </div>

      {/* Cohort counter strip — Value/Fundamental/Out (research-team taxonomy) */}
      <div className="mt-5">
        <div className="mb-1.5 text-[10px] uppercase tracking-widest text-fg-dim">Cohort placement</div>
        <div className="grid grid-cols-3 gap-3">
          <Counter label="Value Universe"  count={s.n_value}       bg="var(--brand)"    fg="#ffffff" />
          <Counter label="Fundamental"     count={s.n_fundamental} bg="transparent"     fg="var(--brand)" outline="var(--brand)" />
          <Counter label="Out of Universe" count={s.n_out}         bg="transparent"     fg="var(--err)"   outline="var(--err)" />
        </div>
      </div>

      {/* Flag counter strip — risk signals */}
      <div className="mt-3">
        <div className="mb-1.5 text-[10px] uppercase tracking-widest text-fg-dim">Risk signal flags</div>
        <div className="grid grid-cols-4 gap-3">
          <Counter label="Green"   count={s.n_green}   bg="var(--ok)"   fg="#ffffff" />
          <Counter label="Amber"   count={s.n_amber}   bg="var(--warn)" fg="#1c2331" />
          <Counter label="Red"     count={s.n_red}     bg="var(--err)"  fg="#ffffff" />
          <Counter label="Unknown" count={s.n_unknown} bg="var(--bg-hover)" fg="var(--fg-muted)" />
        </div>
      </div>
    </div>
  );
}

function Counter({
  label, count, bg, fg, outline,
}: {
  label: string;
  count: number;
  bg: string;
  fg: string;
  outline?: string;
}) {
  return (
    <div
      className="flex items-baseline justify-between rounded-md px-4 py-2.5"
      style={{
        background: bg,
        color: fg,
        border: outline ? `1px solid ${outline}` : undefined,
      }}
    >
      <span className="text-[11px] uppercase tracking-widest font-semibold">{label}</span>
      <span className="num text-[22px] font-bold">{count}</span>
    </div>
  );
}
