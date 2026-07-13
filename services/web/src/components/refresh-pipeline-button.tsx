"use client";

// On-demand pipeline trigger. Sends POST /api/pipeline/refresh, then
// polls /api/pipeline/status every 3 seconds while the run is active.
// Surfaces idle / running / succeeded / failed states with timing.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, CheckCircle2, AlertTriangle, Loader2, ExternalLink } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, type PipelineState } from "@/lib/api";
import { cn } from "@/lib/utils";

function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      hour: "2-digit", minute: "2-digit", second: "2-digit",
      day: "2-digit", month: "short",
    });
  } catch { return iso; }
}

function fmtElapsed(start: string | null, end: string | null): string {
  if (!start) return "";
  const t0 = new Date(start).getTime();
  const t1 = end ? new Date(end).getTime() : Date.now();
  const sec = Math.max(0, Math.round((t1 - t0) / 1000));
  if (sec < 60) return `${sec}s`;
  return `${Math.floor(sec / 60)}m ${sec % 60}s`;
}

export function RefreshPipelineButton() {
  const qc = useQueryClient();
  const [now, setNow] = useState(Date.now());

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
    mutationFn: () => api.pipeline.refresh(),
    onSuccess: (data) => {
      qc.setQueryData(["pipeline-status"], data);
    },
  });

  // Tick once a second to refresh the "elapsed" display while running.
  useEffect(() => {
    if (status.data?.status !== "running") return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [status.data?.status]);

  // When a successful run finishes, refresh all dashboard queries so
  // numbers on the page reflect the new data.
  useEffect(() => {
    if (status.data?.status === "succeeded") {
      qc.invalidateQueries({ queryKey: ["universe"] });
      qc.invalidateQueries({ queryKey: ["scorecard"] });
      qc.invalidateQueries({ queryKey: ["quadrant"] });
      qc.invalidateQueries({ queryKey: ["indices"] });
    }
  }, [status.data?.status, qc]);

  const state = status.data;
  const running = state?.status === "running" || state?.status === "queued";
  const succeeded = state?.status === "succeeded";
  const failed = state?.status === "failed" || state?.status === "canceled";

  const elapsed = useMemo(() => {
    void now;
    return fmtElapsed(state?.started_at ?? null, state?.ended_at ?? null);
  }, [now, state?.started_at, state?.ended_at]);

  return (
    <div className="panel flex items-center justify-between gap-4 p-4">
      <div className="flex items-start gap-3 min-w-0">
        <div
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg"
          style={{ background: "var(--brand-soft)", color: "var(--brand)" }}
        >
          {running
            ? <Loader2 className="h-4.5 w-4.5 animate-spin" strokeWidth={1.75} />
            : succeeded
              ? <CheckCircle2 className="h-4.5 w-4.5" style={{ color: "var(--ok)" }} strokeWidth={1.75} />
              : failed
                ? <AlertTriangle className="h-4.5 w-4.5" style={{ color: "var(--err)" }} strokeWidth={1.75} />
                : <RefreshCw className="h-4.5 w-4.5" strokeWidth={1.75} />}
        </div>
        <div className="min-w-0">
          <div className="text-[13.5px] font-semibold text-fg">
            {running ? "Refreshing data…"
              : succeeded ? "Data refreshed"
              : failed ? "Last refresh failed"
              : "Refresh data on demand"}
          </div>
          <div className="mt-0.5 text-[12px] text-fg-muted">
            {running && state ? (
              <>
                <span className="mono num">Run {state.run_id}</span>
                {" · "}
                <span>Elapsed <span className="mono num">{elapsed}</span></span>
                {" · "}
                <span>Started <span className="num">{fmtTime(state.started_at)}</span></span>
              </>
            ) : succeeded && state ? (
              <>
                <span>Finished at <span className="num">{fmtTime(state.ended_at)}</span></span>
                {" · "}
                <span>Took <span className="mono num">{elapsed}</span></span>
                {" · "}
                <span className="mono num">{state.run_id}</span>
              </>
            ) : failed && state ? (
              <span style={{ color: "var(--err)" }}>{state.message || "Pipeline error"}</span>
            ) : (
              <>Runs the Dagster <span className="mono">daily_eod_job</span> — Bronze → Silver → Gold → Postgres. Usually ~2 min.</>
            )}
          </div>
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-2">
        <a
          href={state?.dagster_url || "http://localhost:3001"}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 rounded-md px-2.5 py-2 text-[12px] text-fg-muted transition-colors hover:bg-bg-hover hover:text-fg"
          title={state?.dagster_url ? "Open this run in Dagster UI" : "Open Dagster UI for full audit + logs"}
        >
          {state?.run_id ? "View run" : "Dagster"}
          <ExternalLink className="h-3 w-3" strokeWidth={1.75} />
        </a>
        <button
          onClick={() => trigger.mutate()}
          disabled={running || trigger.isPending}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-md px-3.5 py-2 text-[12.5px] font-semibold transition-all",
            "disabled:cursor-not-allowed disabled:opacity-60",
          )}
          style={{
            background: "var(--brand)",
            color: "#ffffff",
          }}
        >
          {running ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={2.25} />
              Running…
            </>
          ) : (
            <>
              <RefreshCw className="h-3.5 w-3.5" strokeWidth={2.25} />
              Refresh data
            </>
          )}
        </button>
      </div>
    </div>
  );
}
