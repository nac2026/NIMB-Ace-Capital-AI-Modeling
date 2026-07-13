"use client";

import { Suspense, useCallback, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ScripPicker } from "@/components/compare/scrip-picker";
import { PriceOverlay } from "@/components/compare/price-overlay";
import { MetricGrid } from "@/components/compare/metric-grid";

function parseScrips(raw: string | null): string[] {
  if (!raw) return [];
  return Array.from(
    new Set(raw.split(",").map((s) => s.trim().toUpperCase()).filter(Boolean)),
  ).slice(0, 5);
}

function ComparePageInner() {
  const params = useSearchParams();
  const router = useRouter();
  const scrips = useMemo(() => parseScrips(params.get("scrips")), [params]);

  const setScrips = useCallback(
    (next: string[]) => {
      const qs = next.length ? `?scrips=${encodeURIComponent(next.join(","))}` : "";
      router.replace(`/compare${qs}`);
    },
    [router],
  );

  const tooFew = scrips.length < 2;

  return (
    <div className="h-full overflow-y-auto bg-bg">
      <div
        className="px-6 py-4"
        style={{ borderBottom: "1px solid var(--border-subtle)", background: "var(--bg-panel)" }}
      >
        <div className="flex items-baseline justify-between gap-4">
          <div>
            <h1 className="text-[15px] font-semibold tracking-tight text-fg">Compare</h1>
            <p className="mt-0.5 text-[12px] text-fg-muted">
              Pick 2–5 scrips — rows highlight the best value.
            </p>
          </div>
          <div className="text-[11px] text-fg-dim">{scrips.length} / 5 selected</div>
        </div>
        <div className="mt-3">
          <ScripPicker value={scrips} onChange={setScrips} />
        </div>
      </div>

      <div className="px-6 py-5 space-y-5">
        {tooFew ? (
          <div className="panel px-6 py-12 text-center text-[13px] text-fg-muted">
            Add at least 2 scrips above to start comparing.
          </div>
        ) : (
          <>
            <PriceOverlay scrips={scrips} />
            <MetricGrid scrips={scrips} />
          </>
        )}
      </div>
    </div>
  );
}

export default function ComparePage() {
  return (
    <Suspense fallback={<div className="flex h-full items-center justify-center text-[13px] text-fg-muted">Loading…</div>}>
      <ComparePageInner />
    </Suspense>
  );
}
