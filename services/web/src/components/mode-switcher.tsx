"use client";

// Pinned top of both sidebars. Two-pill toggle showing current product mode.
// Click jumps to the other mode's home page.

import Link from "next/link";
import { LayoutGrid, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

export function ModeSwitcher({
  current,
  collapsed = false,
}: {
  current: "research" | "speculative";
  collapsed?: boolean;
}) {
  if (collapsed) {
    return (
      <div className="flex flex-col gap-1 px-1.5">
        <ModeIcon
          href="/dashboard"
          Icon={LayoutGrid}
          active={current === "research"}
          label="Research"
        />
        <ModeIcon
          href="/speculative"
          Icon={Sparkles}
          active={current === "speculative"}
          label="Speculative"
        />
      </div>
    );
  }
  return (
    <div
      className="grid grid-cols-2 gap-0.5 rounded-md p-0.5"
      style={{ background: "var(--bg-hover)" }}
    >
      <ModePill href="/dashboard"   active={current === "research"}    label="Research"     Icon={LayoutGrid} />
      <ModePill href="/speculative" active={current === "speculative"} label="Speculative"  Icon={Sparkles} />
    </div>
  );
}

function ModePill({
  href, active, label, Icon,
}: {
  href: string;
  active: boolean;
  label: string;
  Icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "flex items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-[12px] font-medium transition-all",
        active ? "shadow-sm" : "text-fg-muted hover:text-fg",
      )}
      style={
        active
          ? { background: "var(--bg-panel)", color: "var(--brand)" }
          : undefined
      }
    >
      <Icon className="h-3.5 w-3.5" strokeWidth={1.75} />
      {label}
    </Link>
  );
}

function ModeIcon({
  href, Icon, active, label,
}: {
  href: string;
  Icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  active: boolean;
  label: string;
}) {
  return (
    <Link
      href={href}
      className="group relative flex h-8 items-center justify-center rounded-md transition-colors hover:bg-bg-hover"
      style={active ? { background: "var(--brand-soft)", color: "var(--brand)" } : undefined}
    >
      <Icon className="h-4 w-4" strokeWidth={1.75} />
      <span
        role="tooltip"
        className="pointer-events-none absolute left-full top-1/2 z-50 ml-2 -translate-y-1/2 whitespace-nowrap rounded-md px-2 py-1 text-[11px] font-medium opacity-0 transition-opacity duration-150 delay-150 group-hover:opacity-100"
        style={{ background: "var(--fg)", color: "var(--bg)", boxShadow: "var(--shadow-md)" }}
      >
        {label}
      </span>
    </Link>
  );
}
