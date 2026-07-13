"use client";

// Shared UI primitives for the help page. Kept tiny because help is purely
// presentational — no data, no state beyond the tab switcher.

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd
      className="rounded-md border px-1.5 py-0.5 text-[10.5px] font-semibold tabular-nums"
      style={{ borderColor: "var(--border-subtle)", background: "var(--bg-subtle)", color: "var(--fg-muted)" }}
    >
      {children}
    </kbd>
  );
}

export function Code({ children }: { children: ReactNode }) {
  return (
    <code
      className="rounded px-1 py-0.5 text-[12px] font-mono"
      style={{ background: "var(--bg-subtle)", color: "var(--fg)", border: "1px solid var(--border-subtle)" }}
    >
      {children}
    </code>
  );
}

export function Formula({ children }: { children: ReactNode }) {
  return (
    <div
      className="mt-2 rounded-md px-3 py-2 text-[12px] font-mono leading-relaxed"
      style={{ background: "var(--bg-subtle)", border: "1px solid var(--border-subtle)", color: "var(--fg)" }}
    >
      {children}
    </div>
  );
}

export function SubHeading({ children }: { children: ReactNode }) {
  return (
    <h3 className="mt-5 mb-2 text-[11px] font-semibold uppercase tracking-widest text-fg-dim">
      {children}
    </h3>
  );
}

export function Card({
  title,
  chip,
  children,
  className,
}: {
  title: ReactNode;
  chip?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn("rounded-lg px-4 py-3", className)}
      style={{ background: "var(--bg-panel)", border: "1px solid var(--border-subtle)" }}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2 min-w-0">
          <span className="text-[13.5px] font-semibold text-fg">{title}</span>
          {chip && <span className="shrink-0">{chip}</span>}
        </div>
      </div>
      <div className="mt-1.5 text-[12.5px] leading-relaxed text-fg-muted">
        {children}
      </div>
    </div>
  );
}

export function Labeled({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="mt-2">
      <div className="text-[10.5px] font-semibold uppercase tracking-wider text-fg-dim">{label}</div>
      <div className="mt-0.5 text-[12.5px] leading-relaxed text-fg-muted">{children}</div>
    </div>
  );
}

export function SourceTag({ children }: { children: ReactNode }) {
  return (
    <div className="mt-3 inline-flex items-center gap-2 rounded px-2 py-1 text-[10.5px]" style={{ background: "var(--bg-subtle)", border: "1px solid var(--border-subtle)", color: "var(--fg-dim)" }}>
      <span className="font-semibold uppercase tracking-wider">Source</span>
      <span className="font-mono text-fg-muted">{children}</span>
    </div>
  );
}
