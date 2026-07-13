"use client";

// Icon-only toggle. Cycles light → dark → system. Hover reveals a tooltip
// showing the current state.

import { Sun, Moon, Monitor } from "lucide-react";
import { useTheme } from "./theme-provider";

const LABELS: Record<string, string> = {
  light: "Light",
  dark: "Dark",
  system: "System",
};

export function ThemeToggle() {
  const { pref, cycle } = useTheme();
  const Icon = pref === "light" ? Sun : pref === "dark" ? Moon : Monitor;
  const label = `Theme: ${LABELS[pref]} — click to cycle`;
  return (
    <button
      onClick={cycle}
      aria-label={label}
      className="group relative flex h-7 w-7 items-center justify-center rounded-md text-fg-muted transition-colors hover:bg-bg-hover hover:text-fg"
    >
      <Icon className="h-[14px] w-[14px]" strokeWidth={1.75} />
      <span
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 -translate-x-1/2 translate-y-1 whitespace-nowrap rounded-md px-2 py-1 text-[11px] font-medium opacity-0 transition-[opacity,transform] duration-150 ease-out delay-150 group-hover:translate-y-0 group-hover:opacity-100"
        style={{ background: "var(--fg)", color: "var(--bg)", boxShadow: "var(--shadow-md)" }}
      >
        {LABELS[pref]}
      </span>
    </button>
  );
}
