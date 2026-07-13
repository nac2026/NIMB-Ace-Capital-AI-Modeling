"use client";
// Product landing — "Trade Surveillance" hero. Ported from the Claude Design
// project (Home.html, "Nothing leaves the book unreviewed"). The left
// telemetry strip, the scope header fill count and the scope footer tier
// breakdown are wired to the live /api/surveillance/summary; the design's
// values are the fallback while it loads. The trade-book ledger inside the
// scope is an illustrative scan animation (fixed sample), kept as designed.

import { useEffect } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

/* sample session ledger — clean fills interleaved with the 3 flagged cases.
   flag color: var(--neg) high · #e8884e elevated · var(--warn) moderate */
const RED = "var(--neg)", ORG = "#e8884e", AMB = "var(--warn)";
type Row = { t: string; s: string; side: "BUY" | "SELL" | "CROSS"; qty: string; px: string; brk: string; flag: { c: string; chip: string } | null };
const ROWS: Row[] = [
  { t: "14:21", s: "MBL", side: "BUY", qty: "800", px: "251.0", brk: "Nabil Sec", flag: null },
  { t: "14:33", s: "NABIL", side: "BUY", qty: "600", px: "512.0", brk: "Sani Sec", flag: null },
  { t: "14:40", s: "SANIMA", side: "SELL", qty: "500", px: "318.4", brk: "Online Sec", flag: null },
  { t: "14:46", s: "MEN", side: "SELL", qty: "600", px: "611.0", brk: "Online Sec", flag: { c: AMB, chip: "CONC 25" } },
  { t: "14:49", s: "NRIC", side: "BUY", qty: "400", px: "745.0", brk: "Kumari Sec", flag: null },
  { t: "14:54", s: "MBL", side: "BUY", qty: "12,000", px: "251.0", brk: "Kumari Sec", flag: { c: ORG, chip: "MARKOUT 52" } },
  { t: "14:57", s: "SHIVM", side: "BUY", qty: "300", px: "588.0", brk: "Imperial Sec", flag: null },
  { t: "14:59", s: "MEN", side: "CROSS", qty: "4,000", px: "611.0", brk: "Cross-fund", flag: { c: RED, chip: "WASH 78" } },
  { t: "15:00", s: "NICA", side: "BUY", qty: "700", px: "432.0", brk: "Online Sec", flag: null },
  { t: "15:01", s: "EBL", side: "SELL", qty: "450", px: "688.0", brk: "Sani Sec", flag: null },
  { t: "15:02", s: "PRVU", side: "BUY", qty: "900", px: "214.5", brk: "Nabil Sec", flag: null },
];

const Check = () => (
  <svg className="check" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6L9 17l-5-5" /></svg>
);

/* detection factors — the six inputs to the composite score */
const DETECT: { color: string; icon: React.ReactNode; title: string; body: string; scrip: string; ex: string }[] = [
  { color: "var(--warn)", title: "Broker concentration", scrip: "MEN", ex: "Online Sec 82% vs ~12% expected", body: "A few brokers accumulating or pairing on one stock far beyond neutral matching — pushing the price up, then distributing. The phase-one focus.", icon: <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3" /><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" /></svg> },
  { color: "var(--neg)", title: "Wash & related-party", scrip: "MEN", ex: "4,000 cross-fund @ 611.0", body: "Cross-fund matched prints that leave the group's net position flat while printing volume and shifting P&L between related funds.", icon: <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M4 7h16M4 7l4-4M20 17H4m16 0l-4 4" /></svg> },
  { color: "#e8884e", title: "Markout & timing", scrip: "MBL", ex: "−4.1% by t+5d", body: "Where price went at t+1m, t+5m, t+30m and t+1d after our fill — did we buy strength that faded, or sell into a recovery?", icon: <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M3 7l6 6 4-4 8 8M21 17v-6" /></svg> },
  { color: "var(--accent-2)", title: "Fundamentals", scrip: "NPL", ex: "4.8% · P/B 2.1× · ROE 9%", body: "Valuation, asset quality and profitability at trade time. A high-NPL bank bought rich is a bad trade no matter the price paid.", icon: <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M3 21h18M6 21V9m4 12V5m4 16v-8m4 8V11" /></svg> },
  { color: "var(--accent)", title: "Technicals", scrip: "MBL", ex: "filled 98th pctile of range", body: "Momentum, trend and where in its range the stock was traded — filled near the top, or into a breakdown against support?", icon: <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M3 17l6-6 4 4 8-8M21 7v5h-5" /></svg> },
  { color: "var(--info)", title: "Intent & averaging", scrip: "MBL", ex: "averaged up into −3% drift", body: "The decision behind the fill — averaging up into weakness, timing against the session, and whether the add improved cost or chased it.", icon: <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3a9 9 0 1 0 9 9M12 8v4l3 2M21 4l-3 3-2-2" /></svg> },
];

const Arrow = () => (<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14M13 6l6 6-6 6" /></svg>);

function fmtN(n: number) { return Number(n).toLocaleString("en-IN"); }

export function Home() {
  // Intro is additive — resting state IS the scanned state, so reduced-motion
  // or a late mount never gets stuck pre-animation.
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!window.matchMedia?.("(prefers-reduced-motion: no-preference)").matches) return;
    const el = document.documentElement;
    el.classList.add("intro");
    const id = window.setTimeout(() => el.classList.remove("intro"), 3600);
    return () => { window.clearTimeout(id); el.classList.remove("intro"); };
  }, []);

  const { data: S } = useQuery({ queryKey: ["surv-summary", "home"], queryFn: () => api.surveillance.summary(), staleTime: 60_000 });

  // KPIs — live where available, design values as fallback.
  const fills = S?.total ?? 559;
  const flagged = S?.flagged ?? 3;
  const cleared = S?.clean_rate != null ? `${S.clean_rate}%` : "99.5%";
  const notional = S?.flagged_notional != null ? (S.flagged_notional >= 1e7 ? `Rs ${(S.flagged_notional / 1e7).toFixed(2)}Cr` : `Rs ${(S.flagged_notional / 1e5).toFixed(1)}L`) : "Rs 65.5L";
  const tHigh = S?.by_tier?.HIGH ?? (S ? 0 : 1);
  const tElev = S?.by_tier?.ELEVATED ?? (S ? 0 : 1);
  const tMod = S?.by_tier?.MODERATE ?? (S ? 0 : 1);
  const lastScan = S?.computed_at
    ? `${new Date(S.computed_at).toLocaleDateString("en-CA")} · ${new Date(S.computed_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
    : "2026-06-05 · 15:02";

  return (
    <div className="home-page">
      <style dangerouslySetInnerHTML={{ __html: CSS }} />
      <div id="home-root">

        {/* TOP BAR */}
        <header className="topbar">
          <Link href="/" className="brand">
            <div className="brand-mark">N</div>
            <div>
              <div className="brand-name">NIMB Capital</div>
              <div className="eyebrow" style={{ fontSize: "8.5px", marginTop: 2 }}>Trade Surveillance</div>
            </div>
          </Link>
          <span className="live-pill"><span className="dot" />ENGINE LIVE</span>
          <div style={{ flex: 1 }} />
          <nav className="nav">
            <Link className="nav-link" href="/surveillance">Surveillance</Link>
            <Link className="nav-link" href="/dashboard">Research</Link>
            <Link className="nav-link" href="/speculative">Speculative</Link>
            <Link className="nav-link" href="/alerts">Alerts</Link>
          </nav>
        </header>

        {/* HERO */}
        <main className="wrap hero">
          <div className="hero-left">
            <div className="eyebrow-line reveal" style={{ animationDelay: ".05s" }}><span className="tick" />TRADE SURVEILLANCE · INTERNAL BOOK</div>
            <h1 className="reveal" style={{ animationDelay: ".12s" }}>Nothing leaves<br />the book <span className="accent">unreviewed.</span></h1>
            <p className="lead reveal" style={{ animationDelay: ".2s" }}>An engine that reads <b>every fill in the trade book</b> against live floorsheet data — screening broker concentration, wash trades and adverse markout — and surfaces only the handful that need a human.</p>

            <div className="telemetry reveal" style={{ animationDelay: ".28s" }}>
              <div className="ts"><span className="dot" style={{ color: "var(--pos)" }} />LAST SCAN<br />{lastScan}</div>
              <div className="sep" />
              <div className="kv"><b>{fmtN(fills)}</b><span>Fills read</span></div>
              <div className="kv"><b className="neg">{fmtN(flagged)}</b><span>Flagged</span></div>
              <div className="kv"><b className="pos">{cleared}</b><span>Cleared</span></div>
              <div className="kv"><b>{notional}</b><span>Flagged notional</span></div>
            </div>

            <div className="cta-row reveal" style={{ animationDelay: ".36s" }}>
              <Link className="btn btn-primary" href="/surveillance">Open Surveillance<Arrow /></Link>
              <Link className="btn btn-ghost" href="/alerts">
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M4 4h16v16H4zM4 7l8 5 8-5" /></svg>
                Latest alert
              </Link>
            </div>
          </div>

          {/* SURVEILLANCE SCOPE */}
          <div className="scope reveal" style={{ animationDelay: ".26s" }}>
            <div className="scope-head">
              <span className="live-pill" style={{ padding: "4px 10px", fontSize: 10 }}><span className="dot" />LIVE</span>
              <span className="eng">SURVEILLANCE&nbsp;ENGINE</span>
              <span className="status">SCAN COMPLETE · <b>{fmtN(fills)}</b>&nbsp;FILLS</span>
              <div className="scanbar" />
            </div>

            <div className="field">
              <span className="corner tl" /><span className="corner tr" /><span className="corner bl" /><span className="corner br" />

              <div className="ledger">
                <div className="lrow head">
                  <span className="c-time">Time</span>
                  <span className="c-stock">Stock</span>
                  <span className="c-side">Side</span>
                  <span className="c-qty">Qty</span>
                  <span className="c-px">Price</span>
                  <span className="c-brk">Counterparty broker</span>
                  <span className="c-flag" />
                </div>
                {ROWS.map((r, i) => (
                  <div
                    key={i}
                    className={"lrow scanrow" + (r.flag ? " flag" : "")}
                    style={{ "--d": `${(0.2 + i * 0.19).toFixed(2)}s`, ...(r.flag ? { "--fc": r.flag.c } : {}) } as React.CSSProperties}
                  >
                    <span className="c-time">{r.t}</span>
                    <span className="c-stock">{r.s}</span>
                    <span className={"c-side " + (r.side === "BUY" ? "buy" : r.side === "SELL" ? "sell" : "cross")}>{r.side}</span>
                    <span className="c-qty">{r.qty}</span>
                    <span className="c-px">{r.px}</span>
                    <span className="c-brk">{r.brk}</span>
                    <span className="c-flag">{r.flag ? <span className="chip">{r.flag.chip}</span> : <Check />}</span>
                  </div>
                ))}
              </div>

              <div className="beam" />
            </div>

            <div className="scope-foot">
              <span className="seg"><span className="dot" style={{ color: "var(--neg)" }} />{tHigh} HIGH</span>
              <span className="seg"><span className="dot" style={{ color: "#e8884e" }} />{tElev} ELEVATED</span>
              <span className="seg"><span className="dot" style={{ color: "var(--warn)" }} />{tMod} MODERATE</span>
              <span className="grow" />
              <span className="seg">CLEAN&nbsp;<b>{cleared}</b></span>
            </div>
          </div>
        </main>

        {/* WHAT THE ENGINE FACTORS IN */}
        <section className="wrap section">
          <div className="sec-head reveal">
            <span className="k">What the engine factors in</span>
            <span className="line" />
            <span className="sec-note">Every flag is a composite score across these factors — never a single binary rule.</span>
          </div>
          <div className="detect-grid">
            {DETECT.map((d, i) => (
              <div key={d.title} className="detect reveal" style={{ animationDelay: `${0.04 + i * 0.06}s` }}>
                <span className="accent-edge" style={{ background: d.color }} />
                <span className="ic" style={{ color: d.color, background: `color-mix(in oklab, ${d.color} 14%, var(--panel-3))` }}>{d.icon}</span>
                <h3>{d.title}</h3>
                <p>{d.body}</p>
                <span className="ex"><span className="dot" style={{ color: d.color }} /><span className="scrip">{d.scrip}</span>&nbsp;{d.ex}</span>
              </div>
            ))}
          </div>
        </section>

        {/* WORKSPACE */}
        <section className="wrap section">
          <div className="sec-head reveal">
            <span className="k">Also in the workspace</span>
            <span className="line" />
          </div>
          <div className="mod-grid">
            <Link className="mod reveal" style={{ animationDelay: ".06s" }} href="/dashboard">
              <span className="mod-ic"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M3 3h7v7H3zM14 3h7v7h-7zM14 14h7v7h-7zM3 14h7v7H3z" /></svg></span>
              <div>
                <h4>Research</h4>
                <p>Browse the universe and drill into any scrip across analytical tabs.</p>
              </div>
              <span className="go"><Arrow /></span>
            </Link>
            <Link className="mod reveal" style={{ animationDelay: ".12s" }} href="/speculative">
              <span className="mod-ic"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3l1.9 5.8H20l-4.9 3.6 1.9 5.8L12 14.6 7 18.2l1.9-5.8L4 8.8h6.1L12 3Z" /></svg></span>
              <div>
                <h4>Speculative Analysis</h4>
                <p>Upload a shortlist; get a per-ticker flag verdict with a written narrative.</p>
              </div>
              <span className="go"><Arrow /></span>
            </Link>
          </div>
        </section>

        <footer>
          <div className="wrap">
            <span>Internal use only · NIMB Capital · NEPSE commercial-bank coverage</span>
            <span>Prototype v1.0.0 · data through {S?.book_last_date ?? "2026-06-05"}</span>
          </div>
        </footer>
      </div>
    </div>
  );
}

/* ── page-scoped styles (ported verbatim from Home.html; mounts/unmounts
      with this component, so the generic class names don't leak) ─────── */
const CSS = `
.home-page a { color: inherit; text-decoration: none; }
.home-page #home-root { min-height: 100vh; }
.home-page .wrap { max-width: 1320px; margin: 0 auto; padding: 0 56px; }

.home-page .topbar {
  position: sticky; top: 0; z-index: 40;
  display: flex; align-items: center; gap: 18px;
  padding: 18px 56px;
  border-bottom: 1px solid var(--line);
  background: color-mix(in oklab, var(--bg) 70%, transparent);
  backdrop-filter: blur(14px);
}
.home-page .brand { display: flex; align-items: center; gap: 13px; }
.home-page .brand-mark {
  width: 38px; height: 38px; border-radius: 11px;
  background: linear-gradient(135deg, var(--accent), color-mix(in oklab, var(--accent) 50%, var(--accent-2)));
  display: flex; align-items: center; justify-content: center;
  color: #0b0d10; font-weight: 700; font-family: var(--font-display); font-size: 18px;
  box-shadow: 0 4px 20px -5px color-mix(in oklab, var(--accent) 70%, transparent);
}
.home-page .brand-name { font-family: var(--font-display); font-weight: 700; font-size: 15.5px; letter-spacing: -.01em; line-height: 1.05; }
.home-page .live-pill {
  display: inline-flex; align-items: center; gap: 8px;
  font-family: var(--font-mono); font-size: 11px; letter-spacing: .14em; color: var(--pos);
  padding: 6px 12px; border-radius: 999px;
  background: color-mix(in oklab, var(--pos) 12%, transparent);
  border: 1px solid color-mix(in oklab, var(--pos) 30%, transparent);
}
.home-page .dot { width: 7px; height: 7px; border-radius: 99px; background: currentColor; box-shadow: 0 0 8px currentColor; flex-shrink: 0; }
.home-page .live-pill .dot { animation: hp-blink 2.4s var(--ease) infinite; }
@keyframes hp-blink { 0%,100%{opacity:1} 50%{opacity:.35} }
.home-page .nav { display: flex; align-items: center; gap: 26px; }
.home-page .nav-link { font-size: 13px; color: var(--ink-3); transition: color .15s; }
.home-page .nav-link:hover { color: var(--ink); }

.home-page .hero {
  display: grid; grid-template-columns: 0.82fr 1.18fr; gap: 72px; align-items: center;
  padding-top: 80px; padding-bottom: 72px; min-height: calc(100vh - 73px);
}
.home-page .eyebrow-line {
  display: inline-flex; align-items: center; gap: 11px;
  font-family: var(--font-mono); font-size: 11px; letter-spacing: .22em; text-transform: uppercase; color: var(--ink-3);
}
.home-page .eyebrow-line .tick { width: 22px; height: 1px; background: var(--accent); }
.home-page .hero h1 {
  font-family: var(--font-display); font-weight: 700; letter-spacing: -.035em; line-height: 0.98;
  font-size: clamp(46px, 4.6vw, 70px); margin: 26px 0 0;
}
.home-page .hero h1 .accent {
  background: linear-gradient(100deg, var(--accent), color-mix(in oklab, var(--accent) 45%, var(--accent-2)));
  -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
}
.home-page .lead { font-size: 17px; line-height: 1.68; color: var(--ink-2); max-width: 460px; margin: 24px 0 0; text-wrap: pretty; }
.home-page .lead b { color: var(--ink); font-weight: 600; }

.home-page .telemetry {
  margin: 34px 0 0; max-width: 520px;
  border-top: 1px solid var(--line); border-bottom: 1px solid var(--line);
  padding: 14px 0; display: flex; align-items: center; gap: 22px; flex-wrap: wrap;
  font-family: var(--font-mono);
}
.home-page .telemetry .ts { font-size: 10.5px; letter-spacing: .12em; color: var(--ink-3); display: flex; align-items: center; gap: 8px; }
.home-page .telemetry .sep { width: 1px; height: 26px; background: var(--line); }
.home-page .telemetry .kv { display: flex; flex-direction: column; gap: 3px; }
.home-page .telemetry .kv b { font-size: 16px; font-weight: 600; letter-spacing: .01em; color: var(--ink); font-variant-numeric: tabular-nums; }
.home-page .telemetry .kv b.neg { color: var(--neg); }
.home-page .telemetry .kv b.pos { color: var(--pos); }
.home-page .telemetry .kv span { font-size: 9px; letter-spacing: .14em; text-transform: uppercase; color: var(--ink-4); }

.home-page .cta-row { display: flex; gap: 14px; margin: 34px 0 0; flex-wrap: wrap; }
.home-page .btn {
  display: inline-flex; align-items: center; gap: 10px; cursor: pointer;
  font-family: var(--font-ui); font-weight: 600; font-size: 14.5px;
  padding: 14px 22px; border-radius: 12px; transition: transform .18s var(--ease), box-shadow .18s var(--ease), background .15s, border-color .15s;
}
.home-page .btn svg { transition: transform .22s var(--ease); }
.home-page .btn-primary { background: var(--accent); color: #0b0d10; border: 1px solid var(--accent); box-shadow: 0 8px 28px -8px color-mix(in oklab, var(--accent) 70%, transparent); }
.home-page .btn-primary:hover { transform: translateY(-2px); box-shadow: 0 14px 38px -8px color-mix(in oklab, var(--accent) 78%, transparent); }
.home-page .btn-primary:hover svg { transform: translateX(5px); }
.home-page .btn-ghost { background: var(--panel-2); color: var(--ink); border: 1px solid var(--line); }
.home-page .btn-ghost:hover { transform: translateY(-2px); border-color: color-mix(in oklab, var(--accent) 45%, var(--line)); }

.home-page .scope {
  position: relative; border-radius: 18px; overflow: hidden;
  background:
    radial-gradient(120% 120% at 50% 0%, color-mix(in oklab, var(--accent-2) 7%, transparent), transparent 60%),
    linear-gradient(165deg, var(--panel-2), var(--panel));
  border: 1px solid var(--line);
  box-shadow: var(--shadow);
}
.home-page .scope-head {
  display: flex; align-items: center; gap: 12px; padding: 14px 18px;
  border-bottom: 1px solid var(--line); position: relative; z-index: 6;
  font-family: var(--font-mono);
}
.home-page .scope-head .eng { font-size: 11px; letter-spacing: .14em; color: var(--ink-2); }
.home-page .scope-head .status { margin-left: auto; font-size: 10.5px; letter-spacing: .1em; color: var(--ink-3); }
.home-page .scope-head .status b { color: var(--accent-2); font-weight: 600; }

.home-page .scanbar { position: absolute; left: 0; bottom: -1px; height: 2px; width: 100%; background: var(--accent-2); transform-origin: left; box-shadow: 0 0 10px var(--accent-2); }
html.intro .home-page .scanbar { transform: scaleX(0); animation: hp-scanFill 2.3s var(--ease) .2s forwards; }
@keyframes hp-scanFill { to { transform: scaleX(1); } }

.home-page .field { position: relative; height: 484px; overflow: hidden; }
.home-page .field::before {
  content: ""; position: absolute; inset: 0;
  background-image:
    linear-gradient(var(--grid-line) 1px, transparent 1px),
    linear-gradient(90deg, var(--grid-line) 1px, transparent 1px);
  background-size: 38px 38px;
}
.home-page .corner { position: absolute; width: 16px; height: 16px; border: 1.5px solid var(--ink-4); opacity: .5; }
.home-page .corner.tl { top: 14px; left: 14px; border-right: 0; border-bottom: 0; }
.home-page .corner.tr { top: 14px; right: 14px; border-left: 0; border-bottom: 0; }
.home-page .corner.bl { bottom: 14px; left: 14px; border-right: 0; border-top: 0; }
.home-page .corner.br { bottom: 14px; right: 14px; border-left: 0; border-top: 0; }

.home-page .ledger { position: absolute; inset: 30px 26px 26px; z-index: 3; display: flex; flex-direction: column; }
.home-page .lrow {
  display: grid; grid-template-columns: 50px 56px 42px 60px 66px 1fr 30px;
  gap: 8px; align-items: center; padding: 0 10px; height: 30px;
  font-family: var(--font-mono); font-size: 12px; font-variant-numeric: tabular-nums;
  border-radius: 7px; position: relative;
}
.home-page .lrow.head { font-size: 9px; letter-spacing: .14em; text-transform: uppercase; color: var(--ink-4); height: 26px; }
.home-page .lrow .c-time { color: var(--ink-3); }
.home-page .lrow .c-stock { color: var(--ink); font-weight: 700; }
.home-page .lrow .c-side { font-weight: 600; }
.home-page .lrow .c-side.buy { color: var(--pos); }
.home-page .lrow .c-side.sell { color: var(--neg); }
.home-page .lrow .c-side.cross { color: var(--accent-2); }
.home-page .lrow .c-qty { color: var(--ink-2); text-align: right; }
.home-page .lrow .c-px { color: var(--ink-2); text-align: right; }
.home-page .lrow .c-brk { color: var(--ink-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.home-page .lrow .c-flag { display: flex; justify-content: flex-end; align-items: center; }
.home-page .lrow .check { width: 15px; height: 15px; color: var(--pos); opacity: .85; }
.home-page .lrow.flag { color: var(--ink); grid-template-columns: 50px 56px 42px 60px 66px 1fr 56px; background: color-mix(in oklab, var(--fc) 9%, transparent); box-shadow: inset 0 0 0 1px color-mix(in oklab, var(--fc) 22%, transparent); }
.home-page .lrow.flag::before { content: ""; position: absolute; left: 0; top: 4px; bottom: 4px; width: 3px; border-radius: 99px; background: var(--fc); }
.home-page .lrow.flag .c-brk { color: var(--fc); font-weight: 600; }
.home-page .lrow.flag .chip {
  font-family: var(--font-mono); font-weight: 700; font-size: 9.5px; letter-spacing: .04em;
  padding: 2px 7px; border-radius: 6px; white-space: nowrap;
  color: var(--fc); background: color-mix(in oklab, var(--fc) 16%, transparent);
  border: 1px solid color-mix(in oklab, var(--fc) 45%, transparent);
  animation: hp-chipPulse 2.6s var(--ease) infinite;
}
@keyframes hp-chipPulse { 0%,100%{ box-shadow: 0 0 0 0 color-mix(in oklab,var(--fc) 0%,transparent);} 50%{ box-shadow: 0 0 0 3px color-mix(in oklab,var(--fc) 16%,transparent);} }

.home-page .beam {
  position: absolute; left: 14px; right: 14px; height: 64px; z-index: 4; pointer-events: none; border-radius: 8px;
  background: linear-gradient(180deg, transparent, color-mix(in oklab, var(--accent-2) 16%, transparent) 78%, color-mix(in oklab, var(--accent-2) 30%, transparent));
  border-bottom: 1.5px solid color-mix(in oklab, var(--accent-2) 70%, transparent);
  box-shadow: 0 1px 14px color-mix(in oklab, var(--accent-2) 30%, transparent);
  top: -64px; animation: hp-sweep 6.5s cubic-bezier(.5,0,.5,1) infinite;
}
@keyframes hp-sweep { 0% { top: -64px; } 100% { top: 100%; } }
html.intro .home-page .beam { animation: hp-sweepBoot 2.5s var(--ease) .15s 1 forwards; }
@keyframes hp-sweepBoot { 0% { top: -64px; opacity: 1; } 88% { opacity: 1; } 100% { top: 100%; opacity: 0; } }

html.intro .home-page .lrow.scanrow { opacity: .28; animation: hp-rowScan .5s var(--ease) forwards; animation-delay: var(--d, 0s); }
@keyframes hp-rowScan { 0% { opacity: .28; } 45% { opacity: 1; background: color-mix(in oklab, var(--accent-2) 14%, transparent); } 100% { opacity: 1; } }
html.intro .home-page .lrow .check, html.intro .home-page .lrow .chip { opacity: 0; animation: hp-badgeIn .4s var(--ease) forwards; animation-delay: calc(var(--d, 0s) + .18s); }
@keyframes hp-badgeIn { from { opacity: 0; transform: scale(.6); } to { opacity: 1; transform: none; } }

.home-page .scope-foot {
  display: flex; align-items: center; gap: 14px; padding: 13px 18px; border-top: 1px solid var(--line);
  font-family: var(--font-mono); font-size: 11px; color: var(--ink-3); position: relative; z-index: 6; flex-wrap: wrap;
}
.home-page .scope-foot .seg { display: inline-flex; align-items: center; gap: 7px; }
.home-page .scope-foot .seg b { color: var(--ink); font-weight: 600; font-variant-numeric: tabular-nums; }
.home-page .scope-foot .grow { flex: 1; }

.home-page .section { padding: 28px 0 30px; }
.home-page .sec-head { display: flex; align-items: baseline; gap: 16px; margin-bottom: 26px; }
.home-page .sec-head .k { font-family: var(--font-mono); font-size: 11px; letter-spacing: .2em; text-transform: uppercase; color: var(--ink-3); white-space: nowrap; }
.home-page .sec-head .line { flex: 1; height: 1px; background: var(--line); }
.home-page .sec-head .sec-note { font-size: 12.5px; color: var(--ink-3); white-space: nowrap; }
@media (max-width: 760px) { .home-page .sec-head .sec-note { display: none; } }
.home-page .detect-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; }
.home-page .detect {
  position: relative; padding: 26px 24px 24px; border-radius: 16px;
  background: var(--panel); border: 1px solid var(--line); overflow: hidden;
  transition: transform .2s var(--ease), border-color .2s, background .2s;
}
.home-page .detect:hover { transform: translateY(-3px); border-color: color-mix(in oklab, var(--accent) 38%, var(--line)); background: var(--panel-2); }
.home-page .detect .accent-edge { position: absolute; left: 0; top: 0; bottom: 0; width: 3px; }
.home-page .detect .ic { width: 44px; height: 44px; border-radius: 12px; display: flex; align-items: center; justify-content: center; margin-bottom: 18px; }
.home-page .detect h3 { font-family: var(--font-display); font-weight: 600; font-size: 18px; margin: 0; letter-spacing: -.01em; }
.home-page .detect p { font-size: 13.5px; line-height: 1.6; color: var(--ink-3); margin: 9px 0 18px; text-wrap: pretty; }
.home-page .detect .ex {
  font-family: var(--font-mono); font-size: 10.5px; letter-spacing: .04em; color: var(--ink-2);
  display: inline-flex; align-items: center; gap: 8px; padding: 6px 11px; border-radius: 8px;
  background: var(--panel-3); border: 1px solid var(--line-soft);
}
.home-page .detect .ex .scrip { color: var(--ink); font-weight: 700; }

.home-page .mod-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.home-page .mod {
  display: flex; align-items: center; gap: 16px; padding: 20px 22px; border-radius: 14px;
  background: color-mix(in oklab, var(--panel) 60%, transparent); border: 1px solid var(--line);
  transition: transform .2s var(--ease), border-color .2s, background .2s;
}
.home-page .mod:hover { transform: translateY(-2px); border-color: color-mix(in oklab, var(--accent) 36%, var(--line)); background: var(--panel); }
.home-page .mod-ic { width: 42px; height: 42px; border-radius: 11px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; color: var(--ink-2); background: var(--panel-3); }
.home-page .mod h4 { font-family: var(--font-display); font-weight: 600; font-size: 15px; margin: 0; }
.home-page .mod p { font-size: 12.5px; color: var(--ink-3); margin: 3px 0 0; line-height: 1.45; }
.home-page .mod .go { margin-left: auto; color: var(--ink-4); transition: transform .2s var(--ease), color .2s; flex-shrink: 0; }
.home-page .mod:hover .go { color: var(--accent); transform: translateX(4px); }

.home-page footer { border-top: 1px solid var(--line); padding: 22px 0; margin-top: 36px; }
.home-page footer .wrap { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
.home-page footer span { font-family: var(--font-mono); font-size: 11px; color: var(--ink-4); letter-spacing: .04em; }

.home-page .reveal { opacity: 1; }
html.intro .home-page .reveal { opacity: 0; transform: translateY(18px); animation: hp-fadeUp .7s var(--ease) forwards; }
@keyframes hp-fadeUp { from { opacity: 0; transform: translateY(18px); } to { opacity: 1; transform: none; } }

@media (prefers-reduced-motion: reduce) {
  .home-page .beam, .home-page .live-pill .dot, .home-page .lrow.flag .chip { animation: none !important; }
  .home-page .beam { display: none; }
}
@media (max-width: 1080px) {
  .home-page .hero { grid-template-columns: 1fr; gap: 44px; padding-top: 52px; padding-bottom: 52px; min-height: 0; }
  .home-page .scope { max-width: 640px; }
  .home-page .detect-grid { grid-template-columns: 1fr 1fr; }
  .home-page .wrap, .home-page .topbar { padding-left: 32px; padding-right: 32px; }
}
@media (max-width: 620px) { .home-page .detect-grid { grid-template-columns: 1fr; } }
@media (max-width: 560px) { .home-page .mod-grid { grid-template-columns: 1fr; } .home-page .nav { display: none; } }
`;
