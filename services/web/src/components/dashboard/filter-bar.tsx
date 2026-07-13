"use client";

// Chip-style multi-select filter bar for the universe table. State lives in
// the parent (which also keeps it in URL query params so links are
// shareable). Groups: quality tier, quadrant, market-cap tier, NPL band.

import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { UniverseRow } from "@/lib/api";

export type FilterKey = "quality" | "quadrant" | "size" | "npl";

export type FilterState = Record<FilterKey, Set<string>>;

export function emptyFilters(): FilterState {
  return { quality: new Set(), quadrant: new Set(), size: new Set(), npl: new Set() };
}

export function filtersActiveCount(f: FilterState): number {
  return (f.quality.size + f.quadrant.size + f.size.size + f.npl.size);
}

const GROUPS: Array<{ key: FilterKey; label: string; options: string[] }> = [
  { key: "quality", label: "Quality",   options: ["TOP_DECILE", "STRONG", "AVERAGE", "BELOW_AVERAGE", "WEAK"] },
  { key: "quadrant", label: "Quadrant", options: ["QUALITY_LEADER", "CONTRARIAN_BET", "MOMENTUM_TRAP", "AVOID"] },
  { key: "size",    label: "Size",      options: ["LARGE", "MID", "SMALL", "MICRO"] },
  { key: "npl",     label: "NPL band",  options: ["< 2%", "2-5%", "> 5%"] },
];

function prettify(v: string): string {
  return v.replace(/_/g, " ").toLowerCase().replace(/(^|\s)\w/g, (m) => m.toUpperCase());
}

export function FilterBar({
  filters,
  onChange,
}: {
  filters: FilterState;
  onChange: (next: FilterState) => void;
}) {
  function toggle(key: FilterKey, opt: string) {
    const next: FilterState = {
      quality: new Set(filters.quality),
      quadrant: new Set(filters.quadrant),
      size: new Set(filters.size),
      npl: new Set(filters.npl),
    };
    if (next[key].has(opt)) next[key].delete(opt);
    else next[key].add(opt);
    onChange(next);
  }

  function clearAll() {
    onChange(emptyFilters());
  }

  const active = filtersActiveCount(filters);

  return (
    <div
      className="panel px-4 py-3 flex flex-wrap items-center gap-x-5 gap-y-2.5"
    >
      {GROUPS.map((g) => (
        <div key={g.key} className="flex items-center gap-2">
          <span className="text-[10.5px] font-semibold uppercase tracking-wider text-fg-dim">
            {g.label}
          </span>
          <div className="flex flex-wrap gap-1">
            {g.options.map((opt) => {
              const selected = filters[g.key].has(opt);
              return (
                <button
                  key={opt}
                  onClick={() => toggle(g.key, opt)}
                  className={cn(
                    "rounded-md px-2 py-0.5 text-[11px] font-medium transition-colors",
                    selected
                      ? "border border-transparent"
                      : "border border-border-subtle text-fg-muted hover:border-border hover:text-fg",
                  )}
                  style={selected ? { background: "var(--fg)", color: "var(--bg)" } : undefined}
                >
                  {prettify(opt)}
                </button>
              );
            })}
          </div>
        </div>
      ))}

      {active > 0 && (
        <button
          onClick={clearAll}
          className="ml-auto inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-medium text-fg-muted transition-colors hover:text-fg"
        >
          <X className="h-3 w-3" strokeWidth={2} />
          Clear ({active})
        </button>
      )}
    </div>
  );
}

// Apply the filters to a row list. Pulled into a helper so the table +
// any future screen preset can reuse it.
export function applyFilters(rows: UniverseRow[], f: FilterState): UniverseRow[] {
  return rows.filter((r) => {
    if (f.quality.size && !(r.quality_tier && f.quality.has(r.quality_tier))) return false;
    if (f.quadrant.size && !(r.quadrant && f.quadrant.has(r.quadrant))) return false;
    if (f.size.size && !(r.market_cap_tier && f.size.has(r.market_cap_tier))) return false;
    if (f.npl.size) {
      const npl = r.npl_ratio;
      const pct = npl === null ? null : npl * 100;
      const band =
        pct === null ? null :
        pct < 2 ? "< 2%" :
        pct <= 5 ? "2-5%" :
        "> 5%";
      if (!band || !f.npl.has(band)) return false;
    }
    return true;
  });
}
