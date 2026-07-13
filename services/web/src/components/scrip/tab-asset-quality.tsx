"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
} from "recharts";
import { api } from "@/lib/api";
import { Pill } from "@/components/dashboard/chips";
import {
  Panel, MetricCell, EmptyState, LoadingState, pct, quarterLabel,
} from "./primitives";

const QUALITY_TONE: Record<string, "ok" | "warn" | "err" | "muted"> = {
  STRONG: "ok",
  MODERATE: "muted",
  WEAK: "err",
};

export function TabAssetQuality({ scrip }: { scrip: string }) {
  const hist = useQuery({
    queryKey: ["asset-quality", scrip, 20],
    queryFn: () => api.scrip.assetQuality(scrip, 20),
  });

  const rows = (hist.data ?? []).slice().reverse();
  const latest = rows[rows.length - 1];

  const data = rows.map((r) => ({
    q: quarterLabel(r.fiscal_year_bs, r.quarter),
    npl: r.npl_ratio !== null ? r.npl_ratio * 100 : null,
    coverage: r.llp_to_npl_ratio !== null ? r.llp_to_npl_ratio * 100 : null,
    credit_loss: r.credit_loss_rate_ttm !== null ? r.credit_loss_rate_ttm * 100 : null,
  }));

  return (
    <div className="grid grid-cols-12 gap-4">
      <Panel
        title="Latest asset quality"
        className="col-span-12"
        right={latest?.asset_quality_tier ? (
          <Pill label={latest.asset_quality_tier} tone={QUALITY_TONE[latest.asset_quality_tier] ?? "muted"} />
        ) : null}
      >
        {hist.isLoading ? (
          <LoadingState rows={2} />
        ) : !latest ? (
          <EmptyState message="No asset-quality data." />
        ) : (
          <div className="grid grid-cols-4 gap-4">
            <MetricCell label="NPL ratio" value={pct(latest.npl_ratio, 2)} tone={latest.npl_ratio !== null && latest.npl_ratio > 0.05 ? "warn" : "default"} />
            <MetricCell label="LLP / NPL (coverage)" value={pct(latest.llp_to_npl_ratio, 1)} tone={latest.llp_to_npl_ratio !== null && latest.llp_to_npl_ratio > 1 ? "ok" : "default"} />
            <MetricCell label="NPL QoQ Δ" value={latest.npl_qoq_change_abs !== null ? `${latest.npl_qoq_change_abs >= 0 ? "+" : ""}${(latest.npl_qoq_change_abs * 100).toFixed(2)}pp` : "—"} tone={latest.npl_qoq_change_abs !== null && latest.npl_qoq_change_abs > 0 ? "warn" : "ok"} />
            <MetricCell label="NPL YoY Δ" value={latest.npl_yoy_change_abs !== null ? `${latest.npl_yoy_change_abs >= 0 ? "+" : ""}${(latest.npl_yoy_change_abs * 100).toFixed(2)}pp` : "—"} tone={latest.npl_yoy_change_abs !== null && latest.npl_yoy_change_abs > 0 ? "warn" : "ok"} />
            <MetricCell label="LLP coverage YoY Δ" value={latest.llp_coverage_yoy_change !== null ? `${latest.llp_coverage_yoy_change >= 0 ? "+" : ""}${(latest.llp_coverage_yoy_change * 100).toFixed(2)}pp` : "—"} />
            <MetricCell label="TTM credit-loss rate" value={pct(latest.credit_loss_rate_ttm, 2)} tone={latest.credit_loss_rate_ttm !== null && latest.credit_loss_rate_ttm > 0.01 ? "warn" : "default"} />
          </div>
        )}
      </Panel>

      <Panel title="NPL trajectory" className="col-span-6">
        <AqChart data={data} field="npl" label="NPL %" isLoading={hist.isLoading} />
      </Panel>

      <Panel title="LLP coverage" hint="Loan-loss provisions / NPL" className="col-span-6">
        <AqChart data={data} field="coverage" label="Coverage %" isLoading={hist.isLoading} />
      </Panel>

      <Panel title="Credit-loss rate (TTM)" className="col-span-12">
        <AqChart data={data} field="credit_loss" label="Credit loss %" isLoading={hist.isLoading} />
      </Panel>
    </div>
  );
}

function AqChart({
  data, field, label, isLoading,
}: {
  data: { q: string; npl: number | null; coverage: number | null; credit_loss: number | null }[];
  field: "npl" | "coverage" | "credit_loss";
  label: string;
  isLoading: boolean;
}) {
  if (isLoading) return <LoadingState rows={4} />;
  if (!data.length) return <EmptyState message="No series." />;
  return (
    <div className="h-[200px]">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="var(--border-subtle)" vertical={false} />
          <XAxis dataKey="q" tick={{ fontSize: 9, fill: "var(--fg-muted)" }} tickLine={false} axisLine={false} minTickGap={24} />
          <YAxis tick={{ fontSize: 10, fill: "var(--fg-muted)" }} tickLine={false} axisLine={false} width={36} />
          <Tooltip
            contentStyle={{ background: "var(--bg-panel)", border: "1px solid var(--border)", borderRadius: 6, fontSize: 11 }}
            formatter={(v) => [typeof v === "number" ? `${v.toFixed(2)}%` : "—", label]}
          />
          <Line type="monotone" dataKey={field} stroke="var(--fg)" strokeWidth={1.5} dot={false} connectNulls />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
