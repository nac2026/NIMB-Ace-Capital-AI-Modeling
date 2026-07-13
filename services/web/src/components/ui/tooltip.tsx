"use client";

// Lightweight CSS-only tooltip. Wraps a trigger and renders a label in a
// floating pill on hover/focus. Positioned to the side of the trigger so
// it doesn't obstruct the icon. No portals — relies on the sidebar having
// overflow visible on the x-axis.

import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

type Side = "right" | "left" | "top" | "bottom";

export function Tooltip({
  label,
  side = "right",
  children,
  disabled,
}: {
  label: ReactNode;
  side?: Side;
  children: ReactNode;
  disabled?: boolean;
}) {
  if (disabled) return <>{children}</>;

  const pos =
    side === "right" ? "left-full top-1/2 -translate-y-1/2 ml-2" :
    side === "left"  ? "right-full top-1/2 -translate-y-1/2 mr-2" :
    side === "top"   ? "bottom-full left-1/2 -translate-x-1/2 mb-2" :
                       "top-full left-1/2 -translate-x-1/2 mt-2";

  return (
    <span className="relative inline-flex group">
      {children}
      <span
        role="tooltip"
        className={cn(
          "pointer-events-none absolute z-50 whitespace-nowrap rounded-md px-2 py-1 text-[11px] font-medium",
          "opacity-0 scale-95 translate-x-[-4px] group-hover:opacity-100 group-hover:scale-100 group-hover:translate-x-0",
          "group-focus-within:opacity-100 group-focus-within:scale-100 group-focus-within:translate-x-0",
          "transition-[opacity,transform] duration-150 ease-out delay-200",
          pos,
        )}
        style={{
          background: "var(--fg)",
          color: "var(--bg)",
          boxShadow: "var(--shadow-md)",
        }}
      >
        {label}
      </span>
    </span>
  );
}
