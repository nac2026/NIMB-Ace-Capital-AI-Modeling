"use client";

// Shared building blocks for the scrip detail page. Kept small and
// presentation-only so each tab can compose them without re-styling.

import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

export function Panel({
  title,
  hint,
  right,
  children,
  className,
}: {
  title?: string;
  hint?: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("panel overflow-hidden", className)}>
      {(title || right) && (
        <div
          className="flex items-start justify-between gap-3 px-4 py-3"
          style={{ borderBottom: "1px solid var(--border-subtle)" }}
        >
          <div className="min-w-0">
            {title && <h3 className="text-[12.5px] font-semibold uppercase tracking-wider text-fg">{title}</h3>}
            {hint && <p className="mt-0.5 text-[11px] text-fg-muted">{hint}</p>}
          </div>
          {right}
        </div>
      )}
      <div className="p-4">{children}</div>
    </div>
  );
}

export function MetricCell({
  label,
  value,
  unit,
  tone,
  hint,
}: {
  label: string;
  value: string;
  unit?: string;
  tone?: "ok" | "warn" | "err" | "default";
  hint?: string;
}) {
  const toneClass =
    tone === "ok" ? "text-ok" :
    tone === "warn" ? "text-warn" :
    tone === "err" ? "text-err" :
    "text-fg";
  return (
    <div className="flex flex-col gap-1" title={hint}>
      <div className="text-[10.5px] font-semibold uppercase tracking-wider text-fg-dim">
        {label}
      </div>
      <div className={cn("num text-[18px] font-semibold leading-none tabular-nums", toneClass)}>
        {value}
        {unit && <span className="ml-1 text-[11px] font-normal text-fg-muted">{unit}</span>}
      </div>
    </div>
  );
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex items-center justify-center py-10 text-[13px] text-fg-muted">
      {message}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-10 text-[13px] text-fg-muted">
      <div className="text-err">⚠ {message}</div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="rounded-md border border-border-subtle px-3 py-1 text-[12px] text-fg-muted hover:border-border hover:text-fg"
        >
          Retry
        </button>
      )}
    </div>
  );
}

export function LoadingState({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-5 rounded bg-bg-hover animate-pulse" style={{ width: `${70 - i * 8}%` }} />
      ))}
    </div>
  );
}

// Formatters — NPR-aware
export function npr(v: number | null | undefined): string {
  if (v === null || v === undefined || !isFinite(v)) return "—";
  if (v >= 1e12) return `NPR ${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9)  return `NPR ${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6)  return `NPR ${(v / 1e6).toFixed(1)}M`;
  return `NPR ${Math.round(v).toLocaleString("en-US")}`;
}

export function pct(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

export function pctFromPct(v: number | null | undefined, digits = 2): string {
  // When backend already gives a percent (e.g. 5.4 = 5.4%)
  if (v === null || v === undefined) return "—";
  return `${v.toFixed(digits)}%`;
}

export function signedPct(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined) return "—";
  const x = v * 100;
  return `${x >= 0 ? "+" : ""}${x.toFixed(digits)}%`;
}

export function quarterLabel(fy: number, q: number): string {
  return `FY${fy} Q${q}`;
}
