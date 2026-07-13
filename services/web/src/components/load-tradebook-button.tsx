"use client";

// Surveillance-board trigger for the trade-book reload. The desk drops new
// Trade_Book_Details*.xlsx into the drop folder (NRC_INTERNAL_TRADES_DIR),
// clicks this, and the Dagster `tradebook_job` re-ingests the folder, rebuilds
// the internal surveillance Gold models and re-syncs serving — no SMTM call.
// Mirrors RefreshPipelineButton: POST /api/pipeline/refresh {jobs:[...]},
// then poll /api/pipeline/status every 3s while active.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, FileUp, Loader2 } from "lucide-react";
import { useEffect, useRef } from "react";
import { api, type PipelineState } from "@/lib/api";

export function LoadTradebookButton() {
  const qc = useQueryClient();
  // run_id of the launch THIS button made — the status endpoint is global, so
  // without this a daily_eod refresh from another page would repaint us.
  const ourRun = useRef<string | null>(null);

  const files = useQuery({
    queryKey: ["tradebook-files"],
    queryFn: () => api.pipeline.tradebookFiles(),
    refetchInterval: 60_000,
  });

  const status = useQuery<PipelineState>({
    queryKey: ["pipeline-status"],
    queryFn: () => api.pipeline.status(),
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "running" || s === "queued" ? 3000 : false;
    },
    refetchOnWindowFocus: false,
  });

  const trigger = useMutation({
    mutationFn: () => api.pipeline.refresh(["tradebook_job"]),
    onSuccess: (data) => {
      ourRun.current = data.run_id ?? null;
      qc.setQueryData(["pipeline-status"], data);
    },
  });

  const state = status.data;
  const mine = ourRun.current != null && state?.run_id === ourRun.current;
  const running = mine && (state?.status === "running" || state?.status === "queued");
  const succeeded = mine && state?.status === "succeeded";
  const failed = (mine && (state?.status === "failed" || state?.status === "canceled"))
    || trigger.isError;

  // Fresh surveillance tables landed — repaint the whole board, then run the
  // alert dispatcher so any NEW internal cases email immediately (the
  // background loop only sends during the NEPSE session window).
  useEffect(() => {
    if (!succeeded) return;
    qc.invalidateQueries({ queryKey: ["surv-summary"] });
    qc.invalidateQueries({ queryKey: ["surv-cases"] });
    qc.invalidateQueries({ queryKey: ["surv-trades"] });
    api.alerts
      .run("incremental")
      .then(() => {
        qc.invalidateQueries({ queryKey: ["alerts-all"] });
        qc.invalidateQueries({ queryKey: ["alerts-recent"] });
      })
      .catch(() => {});
  }, [succeeded, qc]);

  const caption = running
    ? "Ingesting & scoring…"
    : succeeded
      ? "Trade book reloaded — board refreshed"
      : failed
        ? (state?.message || (trigger.error as Error | null)?.message || "Launch failed — is Dagster running?")
        : files.data
          ? `${files.data.count} file${files.data.count === 1 ? "" : "s"} in drop folder`
          : "";

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
      <button
        onClick={() => trigger.mutate()}
        disabled={running || trigger.isPending}
        className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12.5px] font-semibold disabled:cursor-not-allowed disabled:opacity-60"
        style={{ background: "var(--accent)", color: "#1a1407", border: "1px solid var(--accent)" }}
        title={files.data ? `Drop folder: ${files.data.dir}` : undefined}
      >
        {running || trigger.isPending
          ? <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={2} />
          : succeeded
            ? <CheckCircle2 className="h-3.5 w-3.5" strokeWidth={2} />
            : failed
              ? <AlertTriangle className="h-3.5 w-3.5" strokeWidth={2} />
              : <FileUp className="h-3.5 w-3.5" strokeWidth={2} />}
        {running ? "Loading trade book…" : "Load new trade-book data"}
      </button>
      {caption && (
        <span className="mono" style={{ fontSize: 10.5, color: failed ? "var(--err)" : "var(--ink-3)", maxWidth: 260, textAlign: "right" }}>
          {caption}
          {running && state?.dagster_url && (
            <>
              {" · "}
              <a href={state.dagster_url} target="_blank" rel="noopener noreferrer" style={{ color: "var(--accent)" }}>
                logs
              </a>
            </>
          )}
        </span>
      )}
    </div>
  );
}
