"use client";

// Typeahead scrip picker — selects from the active universe and maintains
// a 2-5 chip list. State lives in the parent (URL query param).

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Plus, X, Search } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const MAX_SCRIPS = 5;

export function ScripPicker({
  value,
  onChange,
}: {
  value: string[];
  onChange: (next: string[]) => void;
}) {
  const universe = useQuery({ queryKey: ["universe"], queryFn: api.universe });
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const suggestions = useMemo(() => {
    const q = query.trim().toLowerCase();
    const rows = (universe.data ?? []).filter((r) => !value.includes(r.scrip));
    if (!q) return rows.slice(0, 8);
    return rows.filter(
      (r) => r.scrip.toLowerCase().includes(q) || r.company_name.toLowerCase().includes(q),
    ).slice(0, 8);
  }, [universe.data, query, value]);

  function addScrip(s: string) {
    if (value.length >= MAX_SCRIPS) return;
    onChange([...value, s]);
    setQuery("");
    setOpen(false);
  }

  function removeScrip(s: string) {
    onChange(value.filter((x) => x !== s));
  }

  return (
    <div className="flex flex-wrap items-center gap-2" ref={ref}>
      {value.map((s) => (
        <span
          key={s}
          className="inline-flex items-center gap-1.5 rounded-md bg-fg px-2 py-1 text-[12px] font-semibold"
          style={{ color: "var(--bg)" }}
        >
          {s}
          <button
            onClick={() => removeScrip(s)}
            className="opacity-60 hover:opacity-100"
            aria-label={`Remove ${s}`}
          >
            <X className="h-3 w-3" strokeWidth={2.5} />
          </button>
        </span>
      ))}

      {value.length < MAX_SCRIPS && (
        <div className="relative">
          <button
            onClick={() => setOpen((o) => !o)}
            className="inline-flex items-center gap-1.5 rounded-md border border-dashed border-border px-2.5 py-1 text-[12px] font-medium text-fg-muted transition-colors hover:border-fg hover:text-fg"
          >
            <Plus className="h-3.5 w-3.5" strokeWidth={2} />
            Add scrip
          </button>

          {open && (
            <div
              className="absolute left-0 top-[calc(100%+4px)] z-20 w-[280px] rounded-lg p-2 shadow-lg"
              style={{ background: "var(--bg-panel)", border: "1px solid var(--border)" }}
            >
              <div
                className="flex items-center gap-2 rounded-md px-2 py-1.5"
                style={{ background: "var(--bg-subtle)", border: "1px solid var(--border-subtle)" }}
              >
                <Search className="h-3.5 w-3.5 text-fg-dim" strokeWidth={2} />
                <input
                  autoFocus
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search scrip or bank…"
                  className="w-full bg-transparent text-[12.5px] text-fg placeholder:text-fg-dim outline-none"
                />
              </div>
              <div className="mt-1.5 max-h-[280px] overflow-y-auto">
                {suggestions.length === 0 ? (
                  <div className="py-6 text-center text-[12px] text-fg-dim">No matches</div>
                ) : (
                  suggestions.map((r) => (
                    <button
                      key={r.scrip}
                      onClick={() => addScrip(r.scrip)}
                      className={cn(
                        "flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left text-fg-muted",
                        "hover:bg-bg-hover hover:text-fg",
                      )}
                    >
                      <div className="w-[54px] shrink-0 text-[12.5px] font-semibold text-fg">{r.scrip}</div>
                      <div className="text-[11px] truncate">{r.company_name}</div>
                    </button>
                  ))
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
