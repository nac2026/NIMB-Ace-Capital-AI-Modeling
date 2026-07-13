"use client";

import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, AlertCircle, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { AnalysisSummaryHeader } from "@/components/speculative/analysis-summary-header";
import { TickerResultCard } from "@/components/speculative/ticker-result-card";
import { NarrativeReport } from "@/components/speculative/narrative-report";
import { SpeculativeChatDrawer } from "@/components/speculative/chat-drawer";
import { SectorOutlookPanel } from "@/components/speculative/sector-outlook-panel";
import { ReviewView } from "@/components/speculative/review-view";
import type { SpeculativeResult } from "@/lib/api";

export default function AnalysisDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const sessionId = params.id;

  const detailQ = useQuery({
    queryKey: ["speculative", "session", sessionId],
    queryFn: () => api.speculative.getSession(sessionId),
    refetchOnWindowFocus: false,
    refetchInterval: (q) => {
      const status = q.state.data?.session?.status;
      return status === "running" || status === "pending" ? 2000 : false;
    },
  });

  const deleteM = useMutation({
    mutationFn: () => api.speculative.deleteSession(sessionId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["speculative", "sessions"] });
      router.push("/speculative");
    },
  });

  function handleDelete() {
    if (confirm("Delete this analysis permanently? Chat history will also be removed.")) {
      deleteM.mutate();
    }
  }

  // The page is laid out as two columns: main content + persistent chat drawer.
  // The (speculative) layout already provides the sidebar + banner above.
  return (
    <div className="flex h-full overflow-hidden">
      {/* Main scroll area */}
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[1100px] px-8 py-8">
          <Link
            href="/speculative"
            className="inline-flex items-center gap-1 text-[12px] text-fg-muted transition-colors hover:text-fg"
          >
            <ChevronLeft className="h-3.5 w-3.5" strokeWidth={1.75} />
            All analyses
          </Link>

          {detailQ.isLoading && (
            <div className="mt-6 panel p-12 text-center text-fg-muted text-[13px]">
              <Loader2 className="mx-auto mb-3 h-6 w-6 animate-spin" strokeWidth={1.75} />
              Loading analysis…
            </div>
          )}

          {detailQ.error && (
            <div className="mt-6 panel p-8 text-center" style={{ borderColor: "var(--err)" }}>
              <AlertCircle className="mx-auto h-6 w-6" style={{ color: "var(--err)" }} strokeWidth={1.75} />
              <p className="mt-2 text-[13px]" style={{ color: "var(--err)" }}>
                Analysis not found or backend unreachable.
              </p>
              <Link
                href="/speculative"
                className="mt-3 inline-block text-[12px] text-fg-muted underline hover:text-fg"
              >
                Back to all analyses
              </Link>
            </div>
          )}

          {detailQ.data && (
            <div className="mt-4">
              <AnalysisSummaryHeader
                detail={detailQ.data}
                onDelete={handleDelete}
              />

              {/* Running banner */}
              {(detailQ.data.session.status === "running" || detailQ.data.session.status === "pending") && (
                <div
                  className="mb-6 flex items-center gap-2 rounded-md p-3 text-[12.5px]"
                  style={{ background: "var(--brand-soft)", color: "var(--brand)" }}
                >
                  <Loader2 className="h-4 w-4 animate-spin" strokeWidth={2} />
                  Analysis in progress — this view will update automatically.
                </div>
              )}

              {detailQ.data.mode === "review" ? (
                /* Review mode — written-report validation */
                <ReviewView detail={detailQ.data} />
              ) : (
                <>
                  {/* Screen mode — ticker shortlist results grouped by sector */}
                  {detailQ.data.results.length > 0 ? (
                    <SectorGroupedResults results={detailQ.data.results} />
                  ) : (
                    detailQ.data.session.status === "succeeded" && (
                      <div className="mb-8 panel p-6 text-center text-[13px] text-fg-muted">
                        No results were produced — all tickers were unknown to the active universe.
                      </div>
                    )
                  )}
                  <NarrativeReport
                    narrativeMd={detailQ.data.narrative_md}
                    model={detailQ.data.narrative_model}
                    status={detailQ.data.session.status}
                    loading={detailQ.data.session.status === "running" || detailQ.data.session.status === "pending"}
                  />
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Persistent chat drawer (right side, scoped to this analysis) */}
      {detailQ.data && <SpeculativeChatDrawer sessionId={sessionId} />}
    </div>
  );
}

// ─── Sector grouping ─────────────────────────────────────────────────
// Groups results by sector (case-insensitive, plural-tolerant). Results
// within a sector are already ordered server-side: Value Universe first,
// then Fundamental, then Out of Universe, then by flag_score descending.
function SectorGroupedResults({ results }: { results: SpeculativeResult[] }) {
  // Group by normalised sector key. "Commercial Bank" / "Commercial Banks"
  // merge into the same bucket; preserve the first-seen label for display.
  const groups = new Map<string, { label: string; items: SpeculativeResult[] }>();
  for (const r of results) {
    const raw = (r.sector || "Other").trim();
    const key = raw.toLowerCase().replace(/s$/, "");
    const g = groups.get(key);
    if (g) {
      g.items.push(r);
    } else {
      // Normalise display label: title-case, ensure trailing "s" for plural
      // ("Commercial Bank" -> "Commercial Banks").
      const label = raw.endsWith("s") ? raw : `${raw}s`;
      groups.set(key, { label, items: [r] });
    }
  }

  // Sort sections: largest first; "Unknown" / "Other" at the end.
  const sections = Array.from(groups.values()).sort((a, b) => {
    const aBack = /^other|unknown/i.test(a.label) ? 1 : 0;
    const bBack = /^other|unknown/i.test(b.label) ? 1 : 0;
    if (aBack !== bBack) return aBack - bBack;
    return b.items.length - a.items.length;
  });

  return (
    <div className="mb-8 space-y-8">
      {sections.map((section) => (
        <section key={section.label}>
          <SectorOutlookPanel sector={section.label} results={section.items} />
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {section.items.map((r) => (
              <TickerResultCard key={r.scrip} result={r} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
