"use client";

import { useQuery } from "@tanstack/react-query";
import { api, type ScripProfile } from "@/lib/api";
import { ScoreGauge, FlagPill, Spark, deriveFlag, npr } from "@/components/viz";
import { LoadingState } from "./primitives";

function rs(v: number | null | undefined): string {
  if (v == null || !isFinite(v)) return "—";
  if (Math.abs(v) >= 1e9) return `Rs ${(v / 1e9).toFixed(2)}B`;
  if (Math.abs(v) >= 1e7) return `Rs ${(v / 1e7).toFixed(2)} Cr`;
  if (Math.abs(v) >= 1e6) return `Rs ${(v / 1e6).toFixed(1)}M`;
  return `Rs ${npr(v)}`;
}
function shares(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v >= 1e7) return `${(v / 1e7).toFixed(2)} Cr`;
  if (v >= 1e5) return `${(v / 1e5).toFixed(1)} L`;
  return npr(v);
}

// A factual one-liner built only from data we actually hold (no invented prose).
function aboutText(p: ScripProfile): string {
  const parts: string[] = [];
  parts.push(`${p.company_name} is a ${p.sector}${p.sub_sector ? ` (${p.sub_sector})` : ""} company listed on NEPSE`);
  if (p.registered_date) parts.push(`, registered ${new Date(p.registered_date).getFullYear()}`);
  parts.push(".");
  if (p.paid_up_capital) parts.push(` It carries ${rs(p.paid_up_capital)} of paid-up capital`);
  if (p.listed_shares) parts.push(`${p.paid_up_capital ? " across" : " It has"} ${shares(p.listed_shares)} listed shares`);
  if (p.paid_up_capital || p.listed_shares) parts.push(".");
  if (p.market_cap_npr) parts.push(` Market capitalisation is ${rs(p.market_cap_npr)}${p.market_cap_tier ? ` (${p.market_cap_tier.toLowerCase()}-cap)` : ""}.`);
  return parts.join("");
}

export function TabOverview({ scrip }: { scrip: string }) {
  const profile = useQuery({ queryKey: ["scrip-profile", scrip], queryFn: () => api.scrip.profile(scrip) });
  const summary = useQuery({ queryKey: ["scrip-summary", scrip], queryFn: () => api.scrip.summary(scrip) });
  const prices = useQuery({ queryKey: ["prices", scrip, 90], queryFn: () => api.prices(scrip, 90), staleTime: 5 * 60_000 });

  if (profile.isLoading) return <LoadingState rows={4} />;
  const p = profile.data;
  if (!p) return <div className="py-10 text-center text-[13px] text-fg-muted">No profile data for this scrip.</div>;

  const score = Math.round(summary.data?.quality_score_0_100 ?? 50);
  const flag = deriveFlag(score, summary.data?.change_pct);
  const closes = (prices.data ?? []).map((x) => x.close);
  const fyLabel = p.fiscal_year_bs ? `FY${p.fiscal_year_bs}${p.quarter ? ` Q${p.quarter}` : ""}` : null;

  const tags = [summary.data?.quality_tier ?? null, summary.data?.quadrant ?? null, p.market_cap_tier ? `${p.market_cap_tier} cap` : null].filter(Boolean) as string[];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1.6fr 1fr", gap: "var(--gap)", alignItems: "start" }}>
      {/* left */}
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap)" }}>
        <Card>
          <SectionTitle>About {p.company_name}</SectionTitle>
          <p className="serif" style={{ margin: 0, fontSize: 15.5, lineHeight: 1.65, color: "var(--ink)" }}>{aboutText(p)}</p>
        </Card>
        <Card>
          <SectionTitle sub="Listing & capital structure">Company facts</SectionTitle>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0 24px" }}>
            <Field label="Sector" value={p.sector} />
            <Field label="Sub-sector" value={p.sub_sector ?? "—"} />
            <Field label="Listed on NEPSE" value={p.registered_date ? new Date(p.registered_date).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }) : "—"} />
            <Field label="Listed shares" value={shares(p.listed_shares)} />
            <Field label="Paid-up capital" value={rs(p.paid_up_capital)} />
            <Field label="Face value" value={p.paid_up_value != null ? `Rs ${p.paid_up_value}` : "—"} />
          </div>
        </Card>
        <Card>
          <SectionTitle sub={fyLabel ? `Latest reported · ${fyLabel}` : "Latest reported"}>Key fundamentals</SectionTitle>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
            <Ratio label="EPS" value={p.eps != null ? `Rs ${p.eps.toFixed(2)}` : "—"} />
            <Ratio label="Book value" value={p.bvps != null ? `Rs ${p.bvps.toFixed(1)}` : "—"} />
            <Ratio label="P / E" value={p.pe_ratio != null ? `${p.pe_ratio.toFixed(1)}×` : "—"} />
            <Ratio label="P / B" value={p.pb_ratio != null ? `${p.pb_ratio.toFixed(2)}×` : "—"} />
            <Ratio label="ROE" value={p.roe != null ? `${(p.roe * 100).toFixed(1)}%` : "—"} tone={p.roe != null && p.roe > 0.15 ? "var(--pos)" : undefined} />
            <Ratio label="Dividend yield" value={p.dividend_yield != null ? `${p.dividend_yield.toFixed(2)}%` : "—"} hint={p.bonus_pct ? `${p.bonus_pct}% bonus` : undefined} />
            <Ratio label="Market cap" value={rs(p.market_cap_npr)} />
            <Ratio label="Shares o/s" value={shares(p.shares_outstanding)} />
          </div>
        </Card>
      </div>

      {/* right */}
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap)" }}>
        <Card style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
          <ScoreGauge score={score} flag={flag} size={132} thick={9} label="Conviction" />
          <FlagPill flag={flag} />
          {tags.length > 0 && (
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: "center" }}>
              {tags.map((t, i) => (
                <span key={i} className="mono" style={{ fontSize: 9.5, padding: "3px 8px", borderRadius: 7, background: "var(--panel-3)", border: "1px solid var(--line)", color: "var(--ink-2)" }}>{t}</span>
              ))}
            </div>
          )}
        </Card>
        <Card soft>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px 18px" }}>
            <Stat label="Last price" value={summary.data?.latest_close != null ? `Rs ${summary.data.latest_close.toFixed(1)}` : "—"} />
            <Stat label="P/E" value={p.pe_ratio != null ? `${p.pe_ratio.toFixed(1)}×` : "—"} />
            <Stat label="EPS" value={p.eps != null ? `Rs ${p.eps.toFixed(2)}` : "—"} />
            <Stat label="Div yield" value={p.dividend_yield != null ? `${p.dividend_yield.toFixed(2)}%` : "—"} />
          </div>
          {closes.length > 1 && (
            <div style={{ marginTop: 16 }}>
              <div className="eyebrow" style={{ marginBottom: 6 }}>90-day price</div>
              <Spark data={closes} w={300} h={48} color="var(--accent)" fullWidth />
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

/* editorial building blocks (match the design) */
function SectionTitle({ children, sub }: { children: React.ReactNode; sub?: string }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <h3 className="serif" style={{ margin: 0, fontSize: 19, fontWeight: 600, letterSpacing: "-.01em" }}>{children}</h3>
      {sub && <p style={{ margin: "3px 0 0", fontSize: 12.5, color: "var(--ink-3)" }}>{sub}</p>}
    </div>
  );
}
function Card({ children, style, soft }: { children: React.ReactNode; style?: React.CSSProperties; soft?: boolean }) {
  return <div style={{ background: soft ? "var(--panel-2)" : "var(--panel)", border: "1px solid var(--line)", borderRadius: 16, padding: 20, ...style }}>{children}</div>;
}
function Field({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 3, padding: "11px 0", borderBottom: "1px solid var(--line-soft)" }}>
      <span style={{ fontSize: 11.5, color: "var(--ink-3)" }}>{label}</span>
      <span style={{ fontSize: 14, fontWeight: 500, color: "var(--ink)" }}>{value}</span>
    </div>
  );
}
function Ratio({ label, value, hint, tone }: { label: string; value: string; hint?: string; tone?: string }) {
  return (
    <div style={{ padding: 15, borderRadius: 13, background: "var(--panel-2)", border: "1px solid var(--line-soft)" }}>
      <div style={{ fontSize: 11.5, color: "var(--ink-3)" }}>{label}</div>
      <div className="display tnum" style={{ fontSize: 22, fontWeight: 600, marginTop: 5, color: tone ?? "var(--ink)" }}>{value}</div>
      {hint && <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 3 }}>{hint}</div>}
    </div>
  );
}
function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="eyebrow">{label}</div>
      <div className="display tnum" style={{ fontSize: 18, fontWeight: 600, marginTop: 3 }}>{value}</div>
    </div>
  );
}
