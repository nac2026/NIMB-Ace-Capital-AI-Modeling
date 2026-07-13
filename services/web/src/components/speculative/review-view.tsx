"use client";

import { CheckCircle2, AlertTriangle } from "lucide-react";
import type { SpeculativeSessionDetail } from "@/lib/api";
import { ScoreGauge, FlagPill, type Flag } from "@/components/viz";
import { NarrativeReport } from "./narrative-report";

const VERDICT_META: Record<string, { flag: Flag; label: string }> = {
  GREEN: { flag: "green", label: "Thesis well-supported" },
  AMBER: { flag: "amber", label: "Mixed — proceed with caution" },
  RED: { flag: "red", label: "Thesis not supported by data" },
};

export function ReviewView({ detail }: { detail: SpeculativeSessionDetail }) {
  const v = detail.verdict ?? "AMBER";
  const meta = VERDICT_META[v] ?? VERDICT_META.AMBER;
  const conf = detail.verdict_confidence;

  const claims = detail.claims ?? [];
  const supported = claims.filter((c) => c.verdict === "supported").length;
  const contradicted = claims.filter((c) => c.verdict === "contradicted").length;
  const unverifiable = claims.filter((c) => c.verdict === "unverifiable").length;

  // Conviction score for the gauge: confidence if present, else share of claims supported.
  const score = conf != null ? Math.round(conf * 100) : claims.length ? Math.round((supported / claims.length) * 100) : 50;

  const bull = detail.debate?.find((d) => d.role === "bull")?.content;
  const bear = detail.debate?.find((d) => d.role === "bear")?.content;
  const running = detail.session.status === "running" || detail.session.status === "pending";

  return (
    <div className="mb-8" style={{ display: "flex", flexDirection: "column", gap: "var(--gap)" }}>
      {/* Verdict banner — conviction gauge + flag + claim tally */}
      <div className="panel" style={{ overflow: "hidden", display: "flex", alignItems: "stretch" }}>
        <div style={{ width: 6, background: meta.flag === "green" ? "var(--pos)" : meta.flag === "red" ? "var(--neg)" : "var(--warn)", flexShrink: 0 }} />
        <div className="flex flex-wrap items-center gap-6" style={{ flex: 1, padding: 20 }}>
          <ScoreGauge score={score} flag={meta.flag} size={112} thick={8} label="Report conviction" />
          <div className="min-w-[220px] flex-1">
            <div className="eyebrow">Independent verdict · unbiased</div>
            <div className="mt-1.5 flex items-center gap-3">
              <span className="display" style={{ fontSize: 30, fontWeight: 700, color: meta.flag === "green" ? "var(--pos)" : meta.flag === "red" ? "var(--neg)" : "var(--warn)" }}>{v}</span>
              <FlagPill flag={meta.flag} />
            </div>
            <div className="mt-1 text-[13px] text-fg-muted">{meta.label}</div>
            <div className="mt-4 flex flex-wrap gap-2 text-[11.5px]">
              <Chip n={claims.length} label="claims checked" />
              <Chip n={supported} label="supported" color="var(--pos)" />
              <Chip n={contradicted} label="contradicted" color="var(--neg)" />
              <Chip n={unverifiable} label="unverifiable" color="var(--ink-3)" />
            </div>
          </div>
        </div>
      </div>

      {running && (
        <div className="rounded-lg p-3 text-[12.5px]" style={{ background: "color-mix(in oklab, var(--accent) 12%, transparent)", border: "1px solid color-mix(in oklab, var(--accent) 28%, transparent)", color: "var(--accent)" }}>
          Reviewing the report — claims, aspects and verdict will appear here automatically.
        </div>
      )}

      {/* Bull vs Bear — supporting evidence / risks */}
      {(bull || bear) && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <DebateCard title="Bull case · supporting evidence" tone="var(--pos)" icon="check" body={bull} />
          <DebateCard title="Bear case · risks & red flags" tone="var(--neg)" icon="alert" body={bear} />
        </div>
      )}

      {/* Contradicted claims (the headline risk) */}
      {contradicted > 0 && (
        <div className="panel p-4">
          <h3 className="mb-3 flex items-center gap-2 text-[12.5px] font-semibold uppercase tracking-wider" style={{ color: "var(--neg)" }}>
            <AlertTriangle className="h-4 w-4" /> Claims contradicted by our data
          </h3>
          <ul className="space-y-2.5 text-[12.5px]">
            {claims.filter((c) => c.verdict === "contradicted").map((c, i) => (
              <li key={i} className="flex flex-col gap-1 rounded-lg p-3" style={{ background: "var(--panel-2)", border: "1px solid var(--line-soft)", borderLeft: "3px solid var(--neg)" }}>
                <span className="text-fg">{c.claim_text}</span>
                {c.actual_value && <span className="text-fg-muted">actual: <code className="mono" style={{ color: "var(--neg)" }}>{c.actual_value}</code></span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Full counter-report (verdict reasoning + claim table + aspects, as markdown) */}
      <NarrativeReport
        narrativeMd={detail.narrative_md}
        model={detail.narrative_model}
        status={detail.session.status}
        loading={running}
      />
    </div>
  );
}

function Chip({ n, label, color }: { n: number; label: string; color?: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-md px-2 py-0.5"
          style={{ background: "var(--panel-2)", border: "1px solid var(--line-soft)", color: color ?? "var(--fg)" }}>
      <span className="mono font-semibold tabular-nums">{n}</span>
      <span className="text-fg-muted">{label}</span>
    </span>
  );
}

function DebateCard({ title, tone, icon, body }: { title: string; tone: string; icon: "check" | "alert"; body?: string }) {
  const Icon = icon === "check" ? CheckCircle2 : AlertTriangle;
  return (
    <div className="panel p-4" style={{ borderTop: `3px solid ${tone}` }}>
      <h3 className="mb-2 flex items-center gap-2 text-[12px] font-semibold uppercase tracking-wider" style={{ color: tone }}>
        <Icon className="h-4 w-4" /> {title}
      </h3>
      <p className="text-[12.5px] leading-relaxed text-fg-muted">{body || "—"}</p>
    </div>
  );
}
