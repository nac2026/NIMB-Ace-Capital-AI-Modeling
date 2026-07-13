"use client";

import { cn } from "@/lib/utils";

export const SCRIP_TABS = [
  "overview",
  "performance",
  "fundamentals",
  "financials",
  "valuation",
  "asset-quality",
  "capital",
  "income",
  "technicals",
  "quality",
  "floorsheet",
  "ownership",
  "news",
] as const;

export type ScripTab = typeof SCRIP_TABS[number];

// NPL / CAR / Tier capital are BFI concepts — hide these tabs for non-BFI sectors.
const BANK_ONLY_TABS: ScripTab[] = ["asset-quality", "capital"];
const BFI_SECTORS = new Set(["Commercial Bank", "Development Bank", "Finance", "Microfinance"]);

export function visibleTabs(sector?: string | null): readonly ScripTab[] {
  if (sector && BFI_SECTORS.has(sector)) return SCRIP_TABS;
  return SCRIP_TABS.filter((t) => !BANK_ONLY_TABS.includes(t));
}

const LABELS: Record<ScripTab, string> = {
  "overview":       "Overview",
  "performance":    "Performance",
  "fundamentals":   "Fundamentals",
  "financials":     "Financials",
  "valuation":      "Valuation",
  "asset-quality":  "Asset quality",
  "capital":        "Capital",
  "income":         "Income",
  "technicals":     "Technicals",
  "quality":        "Quality",
  "floorsheet":     "Floor-sheet",
  "ownership":      "Ownership",
  "news":           "News & sentiment",
};

export function TabNav({ active, onChange, sector }: { active: ScripTab; onChange: (t: ScripTab) => void; sector?: string | null }) {
  const tabs = visibleTabs(sector);
  return (
    <nav
      className="flex items-center gap-0 px-6 overflow-x-auto"
      style={{ borderBottom: "1px solid var(--line)", background: "var(--panel)" }}
    >
      {tabs.map((t) => {
        const isActive = active === t;
        return (
          <button
            key={t}
            onClick={() => onChange(t)}
            className={cn(
              "relative whitespace-nowrap px-4 py-3 text-[13px] font-semibold transition-colors",
              isActive ? "text-fg" : "text-fg-muted hover:text-fg",
            )}
          >
            {LABELS[t]}
            {isActive && (
              <span
                className="absolute inset-x-3 bottom-0 h-[2px] rounded-t"
                style={{ background: "var(--accent)" }}
              />
            )}
          </button>
        );
      })}
    </nav>
  );
}
