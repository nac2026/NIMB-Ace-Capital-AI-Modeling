"use client";

// Thin top strip shown above every dashboard page. Communicates the
// prototype scope so analysts know exactly what data is in play:
// version · sector covered · date range.
//
// Click the banner to open /data-coverage with the full inventory.
// Constants below are the single source of truth — also imported by
// data-coverage/page.tsx so the banner and page never drift.

import Link from "next/link";
import { Info, ArrowRight } from "lucide-react";

export const PROTOTYPE_VERSION = "v1.0.0";
export const PROTOTYPE_SECTOR = "Commercial Banks";
export const PROTOTYPE_SCRIP_COUNT = 19;
export const PROTOTYPE_DATA_THROUGH = "2026-04-20";

export function PrototypeBanner() {
  return (
    <Link
      href="/data-coverage"
      title="View full data coverage details"
      className="group flex h-[26px] shrink-0 items-center justify-center gap-3 px-4 text-[11.5px] tracking-tight transition-colors"
      style={{
        background: "var(--brand)",
        color: "#ffffff",
        borderBottom: "1px solid rgba(0,0,0,0.15)",
      }}
    >
      <span className="inline-flex items-center gap-1.5 font-semibold uppercase tracking-widest">
        <Info className="h-3 w-3" strokeWidth={2.25} />
        Prototype {PROTOTYPE_VERSION}
      </span>
      <span aria-hidden className="opacity-50">·</span>
      <span>
        <span className="opacity-70">Sector:</span>{" "}
        <span className="font-medium">{PROTOTYPE_SECTOR} ({PROTOTYPE_SCRIP_COUNT} scrips)</span>
      </span>
      <span aria-hidden className="opacity-50">·</span>
      <span>
        <span className="opacity-70">Data through:</span>{" "}
        <span className="font-medium num">{PROTOTYPE_DATA_THROUGH}</span>
      </span>
      <span className="ml-2 inline-flex items-center gap-1 opacity-70 transition-opacity group-hover:opacity-100">
        <span className="text-[10.5px] uppercase tracking-widest">View details</span>
        <ArrowRight className="h-3 w-3 transition-transform group-hover:translate-x-0.5" strokeWidth={2.25} />
      </span>
    </Link>
  );
}
