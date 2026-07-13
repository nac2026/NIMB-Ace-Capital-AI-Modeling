"use client";

// Universe table redesign: 6 new sortable columns (scorecard, quadrant,
// 6m return with sparkline, P/E self-history tier, dividend yield,
// market-cap tier). Row click navigates to /scrip/[symbol]. Existing
// columns retained for continuity; filter chip bar sits above the table.

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  flexRender, getCoreRowModel, getSortedRowModel, useReactTable,
  SortingState, ColumnDef,
} from "@tanstack/react-table";
import {
  ArrowDown, ArrowUp, ChevronsUpDown, Search, MessageSquare,
  TrendingUp, TrendingDown, Copy,
} from "lucide-react";
import { api, UniverseRow } from "@/lib/api";
import { cn, formatPct } from "@/lib/utils";
import { Sparkline } from "./sparkline";
import {
  QualityTierChip, QuadrantChip, SelfValuationChip, MarketCapChip, ScoreBadge,
} from "./chips";
import {
  FilterBar, FilterState, emptyFilters, applyFilters,
} from "./filter-bar";

declare module "@tanstack/react-table" {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData, TValue> {
    align?: "left" | "right";
  }
}

function num(v: number | null, digits = 2) {
  if (v === null) return <span className="text-fg-dim">—</span>;
  return <span className="num">{v.toFixed(digits)}</span>;
}

function pct(v: number | null, digits = 2) {
  if (v === null) return <span className="text-fg-dim">—</span>;
  return <span className="num">{(v * 100).toFixed(digits)}%</span>;
}

function signed(v: number | null) {
  if (v === null) return <span className="text-fg-dim">—</span>;
  const up = v >= 0;
  const Icon = up ? TrendingUp : TrendingDown;
  return (
    <span className={cn("inline-flex items-center gap-1 num font-medium", up ? "text-ok" : "text-err")}>
      <Icon className="h-3.5 w-3.5" strokeWidth={2} />
      {formatPct(v)}
    </span>
  );
}

// Plain number with color, for fractional returns. Input is a fraction
// (0.0543 = 5.43%); displays with a sign so analysts can scan direction.
function signedFrac(v: number | null) {
  if (v === null) return <span className="text-fg-dim">—</span>;
  const up = v >= 0;
  const value = (v * 100).toFixed(1) + "%";
  return (
    <span className={cn("num font-medium", up ? "text-ok" : "text-err")}>
      {up ? "+" : ""}{value}
    </span>
  );
}

export function UniverseTable({ data, isLoading }: { data?: UniverseRow[]; isLoading?: boolean }) {
  const router = useRouter();
  const [sorting, setSorting] = useState<SortingState>([{ id: "scorecard_0_100", desc: true }]);
  const [filter, setFilter] = useState("");
  const [filters, setFilters] = useState<FilterState>(() => emptyFilters());

  const sparks = useQuery({
    queryKey: ["universe-sparks", 30],
    queryFn: () => api.universeSparklines(30),
    staleTime: 5 * 60_000,
  });

  const filtered = useMemo(() => {
    if (!data) return [];
    const q = filter.trim().toLowerCase();
    let rows = applyFilters(data, filters);
    if (q) {
      rows = rows.filter(
        (r) => r.scrip.toLowerCase().includes(q) || r.company_name.toLowerCase().includes(q),
      );
    }
    return rows;
  }, [data, filter, filters]);

  const columns = useMemo<ColumnDef<UniverseRow>[]>(() => [
    {
      accessorKey: "scrip",
      header: "Bank",
      cell: (c) => (
        <div className="leading-snug">
          <div className="text-[13px] font-semibold text-fg">{c.row.original.scrip}</div>
          <div className="mt-0.5 text-[11px] text-fg-muted truncate max-w-[180px]">
            {c.row.original.company_name}
          </div>
        </div>
      ),
    },
    {
      accessorKey: "latest_close",
      header: "Price",
      meta: { align: "right" },
      cell: (c) => <div className="text-right">{num(c.row.original.latest_close)}</div>,
    },
    {
      accessorKey: "change_pct",
      header: "1D",
      meta: { align: "right" },
      cell: (c) => <div className="text-right">{signed(c.row.original.change_pct)}</div>,
    },
    {
      accessorKey: "return_6m",
      header: "6M",
      meta: { align: "right" },
      cell: (c) => {
        const v = c.row.original.return_6m;
        const scrip = c.row.original.scrip;
        const points = sparks.data?.[scrip] ?? [];
        return (
          <div className="flex items-center justify-end gap-2">
            <Sparkline points={points} positive={(v ?? 0) >= 0} width={56} height={18} />
            <div className="w-[52px] text-right">{signedFrac(v)}</div>
          </div>
        );
      },
    },
    {
      accessorKey: "scorecard_0_100",
      header: "Scorecard",
      meta: { align: "right" },
      cell: (c) => (
        <div className="text-right">
          <ScoreBadge v={c.row.original.scorecard_0_100} />
        </div>
      ),
    },
    {
      accessorKey: "quality_tier",
      header: "Quality",
      cell: (c) => <QualityTierChip tier={c.row.original.quality_tier} />,
    },
    {
      accessorKey: "quadrant",
      header: "Quadrant",
      cell: (c) => <QuadrantChip quadrant={c.row.original.quadrant} />,
    },
    {
      accessorKey: "self_valuation_tier",
      header: "Vs own P/E",
      cell: (c) => <SelfValuationChip tier={c.row.original.self_valuation_tier} />,
    },
    {
      accessorKey: "total_dividend_yield",
      header: "Div yield",
      meta: { align: "right" },
      cell: (c) => {
        // dividend_yield.total_dividend_yield is stored as a percent (e.g. 3.59 = 3.59%).
        const v = c.row.original.total_dividend_yield;
        if (v === null) return <div className="text-right text-fg-dim">—</div>;
        const good = v >= 8;
        return (
          <div className={cn("text-right num", good && "font-semibold text-ok")}>
            {v.toFixed(2)}%
          </div>
        );
      },
    },
    {
      accessorKey: "market_cap_tier",
      header: "Size",
      cell: (c) => <MarketCapChip tier={c.row.original.market_cap_tier} />,
    },
    {
      accessorKey: "npl_ratio",
      header: "NPL",
      meta: { align: "right" },
      cell: (c) => {
        const v = c.row.original.npl_ratio;
        const pctVal = v === null ? null : v * 100;
        return (
          <div className={cn("text-right", pctVal !== null && pctVal > 5 && "font-semibold text-warn")}>
            {pct(v, 2)}
          </div>
        );
      },
    },
    {
      accessorKey: "car",
      header: "CAR",
      meta: { align: "right" },
      cell: (c) => {
        const v = c.row.original.car;
        const pctVal = v === null ? null : v * 100;
        return (
          <div className={cn("text-right", pctVal !== null && pctVal < 11 && "font-semibold text-err")}>
            {pct(v, 2)}
          </div>
        );
      },
    },
    {
      accessorKey: "pe_ratio",
      header: "P/E",
      meta: { align: "right" },
      cell: (c) => <div className="text-right">{num(c.row.original.pe_ratio)}</div>,
    },
    {
      id: "actions",
      header: "",
      enableSorting: false,
      cell: (c) => (
        <div className="flex items-center justify-end gap-1">
          <RowAction
            icon={MessageSquare}
            label="Ask chat"
            onClick={(e) => {
              e.stopPropagation();
              router.push(`/chat?q=${encodeURIComponent(`Summarize ${c.row.original.scrip}`)}`);
            }}
          />
          <RowAction
            icon={Copy}
            label="Add to compare"
            onClick={(e) => {
              e.stopPropagation();
              router.push(`/compare?scrips=${encodeURIComponent(c.row.original.scrip)}`);
            }}
          />
        </div>
      ),
    },
  ], [router, sparks.data]);

  const table = useReactTable({
    data: filtered,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  return (
    <div className="space-y-3">
      <FilterBar filters={filters} onChange={setFilters} />

      <div className="panel overflow-hidden">
        {/* Toolbar */}
        <div
          className="flex items-center justify-between px-5 py-3.5"
          style={{ borderBottom: "1px solid var(--border-subtle)" }}
        >
          <div className="flex items-center gap-3">
            <h2 className="text-[14px] font-semibold text-fg">Active Universe</h2>
            <span className="rounded-full bg-bg-subtle px-2 py-0.5 text-[11px] font-medium text-fg-muted">
              {filtered.length} / {data?.length ?? 0}
            </span>
          </div>
          <div
            className="flex items-center gap-2 rounded-xl px-3 py-1.5"
            style={{ background: "var(--bg-subtle)", border: "1px solid var(--border-subtle)" }}
          >
            <Search className="h-3.5 w-3.5 text-fg-dim" strokeWidth={2} />
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter bank or ticker…"
              className="w-[200px] bg-transparent text-[13px] text-fg placeholder:text-fg-dim outline-none"
            />
          </div>
        </div>

        {/* Table */}
        <div className="overflow-x-auto">
          <table className="tbl">
            <thead>
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id}>
                  {hg.headers.map((h) => {
                    const isRight = h.column.columnDef.meta?.align === "right";
                    const sortState = h.column.getIsSorted();
                    return (
                      <th
                        key={h.id}
                        className={cn(
                          h.column.getCanSort() && "cursor-pointer select-none hover:text-fg",
                          isRight && "text-right",
                        )}
                        onClick={h.column.getToggleSortingHandler()}
                      >
                        <div className={cn(
                          "inline-flex items-center gap-1",
                          isRight && "flex-row-reverse",
                        )}>
                          {h.column.getCanSort() && (
                            sortState === "asc"  ? <ArrowUp className="h-3 w-3 text-fg" /> :
                            sortState === "desc" ? <ArrowDown className="h-3 w-3 text-fg" /> :
                            <ChevronsUpDown className="h-3 w-3 opacity-30" />
                          )}
                          {flexRender(h.column.columnDef.header, h.getContext())}
                        </div>
                      </th>
                    );
                  })}
                </tr>
              ))}
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 8 }).map((_, i) => (
                  <tr key={i}>
                    {columns.map((_, j) => (
                      <td key={j}>
                        <div
                          className="h-4 rounded bg-bg-hover animate-pulse"
                          style={{ width: j === 0 ? 140 : 56 }}
                        />
                      </td>
                    ))}
                  </tr>
                ))
              ) : table.getRowModel().rows.length === 0 ? (
                <tr>
                  <td colSpan={columns.length} className="py-12 text-center text-[13px] text-fg-muted">
                    No banks match your filter.
                  </td>
                </tr>
              ) : (
                table.getRowModel().rows.map((row) => (
                  <tr
                    key={row.id}
                    onClick={() => router.push(`/scrip/${row.original.scrip}`)}
                    className="cursor-pointer hover:bg-bg-hover"
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id}>
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function RowAction({
  icon: Icon,
  label,
  onClick,
}: {
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  label: string;
  onClick: (e: React.MouseEvent) => void;
}) {
  return (
    <button
      onClick={onClick}
      title={label}
      aria-label={label}
      className="flex h-7 w-7 items-center justify-center rounded-md text-fg-dim transition-colors hover:bg-bg-hover hover:text-fg"
    >
      <Icon className="h-3.5 w-3.5" strokeWidth={2} />
    </button>
  );
}
