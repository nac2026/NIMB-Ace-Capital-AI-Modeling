"use client";

import { LayoutGrid, Sparkles, ExternalLink } from "lucide-react";
import Link from "next/link";
import { ProductCard } from "./product-card";
import {
  PROTOTYPE_VERSION,
  PROTOTYPE_SECTOR,
  PROTOTYPE_SCRIP_COUNT,
  PROTOTYPE_DATA_THROUGH,
} from "@/components/prototype-banner";

export function LandingChooser() {
  return (
    <div className="flex min-h-screen w-full flex-col" style={{ background: "var(--bg)" }}>
      {/* Top brand strip */}
      <header
        className="flex h-[56px] shrink-0 items-center justify-between px-8"
        style={{ borderBottom: "1px solid var(--border-subtle)" }}
      >
        <div className="flex items-baseline gap-2">
          <span className="text-[15px] font-bold tracking-tight" style={{ color: "var(--brand)" }}>NIMB Ace</span>
          <span className="text-[13px] font-medium tracking-tight text-fg-muted">· Research Platform</span>
        </div>
        <Link
          href="/help"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-[12px] text-fg-muted transition-colors hover:text-fg"
        >
          Help & docs
          <ExternalLink className="h-3 w-3" strokeWidth={1.75} />
        </Link>
      </header>

      {/* Hero + cards */}
      <main className="flex flex-1 items-center justify-center px-8 py-12">
        <div className="w-full max-w-[1080px]">
          <div className="mb-10 text-center">
            <div
              className="mb-3 inline-flex items-center gap-2 rounded-full px-3 py-1 text-[10.5px] font-semibold uppercase tracking-widest"
              style={{ background: "var(--brand-soft)", color: "var(--brand)" }}
            >
              Prototype {PROTOTYPE_VERSION} · {PROTOTYPE_SECTOR} · Data through {PROTOTYPE_DATA_THROUGH}
            </div>
            <h1 className="text-[36px] font-semibold tracking-tight text-fg">Where would you like to go today?</h1>
            <p className="mt-3 text-[15px] text-fg-muted">
              Choose a workspace to begin. Both modes share the same {PROTOTYPE_SCRIP_COUNT}-bank dataset
              and analytics layer.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
            <ProductCard
              href="/dashboard"
              label="For Analysts"
              icon={<LayoutGrid className="h-6 w-6" strokeWidth={1.75} />}
              title="Research"
              description="Browse, filter and drill into the universe. Open any scrip for a deep-dive across 8 analytical tabs. Run preset screens. Compare side-by-side."
              features={[
                "Universe dashboard with composite scores and quadrants",
                "Per-scrip detail: performance, fundamentals, valuation, asset quality",
                "Compare any 2-5 banks in one transposed grid",
                "5 strategy presets and a context-aware research chat",
              ]}
            />
            <ProductCard
              href="/speculative"
              label="For Decision-Makers"
              icon={<Sparkles className="h-6 w-6" strokeWidth={1.75} />}
              title="Speculative Analysis"
              description="Upload a shortlist your research team prepared. The platform analyses every name against our Gold-layer data and returns a flagged report with an LLM-written narrative."
              features={[
                "CSV / Excel upload — research-team shortlists",
                "Per-ticker red / amber / green verdict with rule-level evidence",
                "LLM-generated executive narrative report",
                "Persistent sessions — return days later and pick up where you left off",
              ]}
              primary
            />
          </div>

          <div className="mt-12 text-center text-[11.5px] text-fg-dim">
            Internal use only · NIMB Ace Capital · Built for NEPSE Commercial Banks coverage
          </div>
        </div>
      </main>
    </div>
  );
}
