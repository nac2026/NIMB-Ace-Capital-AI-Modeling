"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { ReactNode } from "react";

export function ProductCard({
  href,
  icon,
  label,
  title,
  description,
  features,
  primary = false,
}: {
  href: string;
  icon: ReactNode;
  label: string;
  title: string;
  description: string;
  features: string[];
  primary?: boolean;
}) {
  return (
    <Link
      href={href}
      className="group relative flex flex-col rounded-2xl border bg-bg-panel p-8 transition-all duration-200 hover:-translate-y-1 hover:shadow-lg"
      style={{
        borderColor: primary ? "var(--brand)" : "var(--border-subtle)",
        borderWidth: primary ? 1.5 : 1,
        boxShadow: "var(--shadow-sm)",
      }}
    >
      <div className="flex items-start justify-between">
        <div
          className="flex h-12 w-12 items-center justify-center rounded-xl"
          style={{
            background: primary ? "var(--brand)" : "var(--brand-soft)",
            color: primary ? "#ffffff" : "var(--brand)",
          }}
        >
          {icon}
        </div>
        <span
          className="text-[10.5px] uppercase tracking-widest font-semibold"
          style={{ color: primary ? "var(--brand)" : "var(--fg-dim)" }}
        >
          {label}
        </span>
      </div>

      <h2 className="mt-6 text-[24px] font-semibold tracking-tight text-fg">{title}</h2>
      <p className="mt-2 text-[13.5px] leading-relaxed text-fg-muted">{description}</p>

      <ul className="mt-6 space-y-2.5">
        {features.map((f) => (
          <li key={f} className="flex items-start gap-2 text-[13px] text-fg-muted">
            <span
              className="mt-1.5 inline-block h-1 w-1 shrink-0 rounded-full"
              style={{ background: "var(--brand)" }}
            />
            <span>{f}</span>
          </li>
        ))}
      </ul>

      <div className="mt-8 flex items-center justify-between border-t pt-5" style={{ borderColor: "var(--border-subtle)" }}>
        <span className="text-[12px] text-fg-muted">Open workspace</span>
        <span
          className="flex h-8 w-8 items-center justify-center rounded-lg transition-all duration-200 group-hover:translate-x-1"
          style={{
            background: primary ? "var(--brand)" : "var(--bg-subtle)",
            color: primary ? "#ffffff" : "var(--brand)",
          }}
        >
          <ArrowRight className="h-4 w-4" strokeWidth={2} />
        </span>
      </div>
    </Link>
  );
}
