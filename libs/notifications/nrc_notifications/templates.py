"""HTML + text email templates for the NEPSE Surveillance Alert.

Faithful implementation of the Claude Design handoff "Surveillance Alert
Email.html": a dark, premium alert email (navy + gold, Newsreader serif
headings, IBM Plex Sans/Mono) with a header, a big summary strip, the top-5
stocks as detailed cards (severity rail, dominant-broker + volume-share hero,
concentration progress bar, pattern chips, score, review link), an "Also
flagged" table for the rest, a gold CTA and a methodology footer.

Table-based + inline styles only — the layout is email-client safe."""
from __future__ import annotations

from dataclasses import dataclass, field

# ---- palette (from the design) ----
_BG = "#06080c"
_CARD = "#0b0f16"
_CARD2 = "#11161f"
_STRIP = "#141b25"
_TRACK = "#1a2230"
_BORDER = "#222c3a"
_DIV = "#1a212c"
_INK = "#eef2f7"
_INK2 = "#aab4c2"
_MUTE = "#74808f"
_FAINT = "#56627a"
_GOLD = "#d8a64a"
_GOLD_L = "#f0cd86"
_GREEN = "#36b37e"
_CRIT = "#e5575c"
_ELEV = "#e8884e"
_WATCH = "#e6a93b"

_SERIF = "'Newsreader',Georgia,'Times New Roman',serif"
_SANS = "'IBM Plex Sans',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
_MONO = "'IBM Plex Mono','SF Mono',ui-monospace,'Courier New',monospace"

_FONT_LINK = (
    '<link href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,500;6..72,600'
    '&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet" />'
)

_DETAIL_N = 5  # detailed cards; the rest go in the "Also flagged" table


@dataclass
class AlertItem:
    scrip: str
    kind: str
    alert_type: str          # "spec" | "accum" | "conc"
    level: str               # "HIGH" | "WATCH"
    title: str
    detail: str
    signal_key: str
    company_name: str | None = None
    sector: str | None = None
    score: float | None = None
    broker: int | None = None
    volume_share: float | None = None      # 0..1 (dominant broker's share)
    patterns: list[str] = field(default_factory=list)
    severity: str = "watch"                # critical | elevated | watch
    tags: list[str] = field(default_factory=list)


def _sev_color(sev: str) -> str:
    return {"critical": _CRIT, "elevated": _ELEV}.get(sev, _WATCH)


def _pat_color(p: str) -> str:
    return _CRIT if p in ("Matched (wash) trades", "Self-trades") else _WATCH


def _scrip_url(web_base: str, scrip: str) -> str:
    return f"{web_base.rstrip('/')}/scrip/{scrip}#floorsheet"


def _alerts_url(web_base: str) -> str:
    return f"{web_base.rstrip('/')}/alerts"


def _pct(it: AlertItem) -> int:
    return round((it.volume_share or 0) * 100)


# ---------------------------------------------------------------- detailed card
def _card(it: AlertItem, rank: int, web_base: str) -> str:
    c = _sev_color(it.severity)
    pct = _pct(it)
    score = f"{it.score:.0f}" if it.score is not None else "—"
    broker = f"#{it.broker}" if it.broker is not None else "—"
    chips = "&nbsp;&nbsp;".join(
        f'<span style="display:inline-block;font-family:{_MONO};font-size:10px;letter-spacing:.04em;'
        f'color:{_pat_color(p)};border:1px solid {_pat_color(p)}55;background:{_pat_color(p)}14;'
        f'border-radius:20px;padding:3px 9px;white-space:nowrap;">{p}</span>'
        for p in (it.patterns or ["Concentration"])
    )
    return f"""
  <tr><td style="padding:0 26px 14px 26px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{_CARD2};border:1px solid {_BORDER};border-radius:14px;border-collapse:separate;">
      <tr>
        <td width="4" style="background:{c};border-radius:14px 0 0 14px;font-size:0;line-height:0;">&nbsp;</td>
        <td style="padding:18px 20px 18px 22px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
            <tr>
              <td valign="middle">
                <span style="font-family:{_MONO};font-size:11px;color:{_FAINT};letter-spacing:.05em;">{rank:02d}</span>
                &nbsp;&nbsp;<span style="font-family:{_MONO};font-size:18px;font-weight:600;color:{_INK};letter-spacing:.01em;">{it.scrip}</span>
              </td>
              <td valign="middle" align="right"><span style="display:inline-block;font-family:{_MONO};font-size:10.5px;font-weight:600;letter-spacing:.12em;color:{c};border:1px solid {c}66;background:{c}1c;border-radius:20px;padding:4px 11px;">{it.severity.upper()}</span></td>
            </tr>
            <tr><td colspan="2" style="padding-top:3px;"><span style="font-family:{_SANS};font-size:12.5px;color:{_MUTE};">{it.company_name or ''}</span></td></tr>
          </table>

          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:15px;">
            <tr>
              <td><span style="font-family:{_MONO};font-size:9.5px;letter-spacing:.16em;color:{_FAINT};text-transform:uppercase;">Dominant broker</span></td>
              <td align="right"><span style="font-family:{_MONO};font-size:9.5px;letter-spacing:.16em;color:{_FAINT};text-transform:uppercase;">Volume share</span></td>
            </tr>
            <tr>
              <td style="padding-top:2px;"><span style="font-family:{_SANS};font-size:14px;color:{_INK};font-weight:600;">Broker&nbsp;</span><span style="font-family:{_MONO};font-size:14px;color:{_GOLD_L};font-weight:600;">{broker}</span></td>
              <td align="right" style="padding-top:2px;"><span style="font-family:{_MONO};font-size:17px;font-weight:600;color:{c};">{pct}%</span></td>
            </tr>
            <tr><td colspan="2" style="padding-top:9px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:separate;border-spacing:0;">
                <tr>
                  <td height="9" width="{max(1, pct)}%" style="background:{c};border-radius:6px 0 0 6px;font-size:0;line-height:0;">&nbsp;</td>
                  <td height="9" width="{max(1, 100 - pct)}%" style="background:{_TRACK};border-radius:0 6px 6px 0;font-size:0;line-height:0;">&nbsp;</td>
                </tr>
              </table></td></tr>
          </table>

          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:16px;">
            <tr>
              <td valign="middle">{chips}</td>
              <td valign="middle" align="right" style="white-space:nowrap;">
                <span style="font-family:{_MONO};font-size:9.5px;letter-spacing:.12em;color:{_FAINT};">SCORE</span>&nbsp;
                <span style="font-family:{_MONO};font-size:15px;font-weight:600;color:{_INK};">{score}</span><span style="font-family:{_MONO};font-size:11px;color:{_FAINT};">/100</span>
              </td>
            </tr>
            <tr>
              <td colspan="2" style="padding-top:14px;border-top:1px solid {_DIV};">
                <div style="height:14px;font-size:0;line-height:0;">&nbsp;</div>
                <a href="{_scrip_url(web_base, it.scrip)}" style="font-family:{_MONO};font-size:12px;font-weight:600;color:{_GOLD};text-decoration:none;letter-spacing:.02em;">Review {it.scrip} &nbsp;&rarr;</a>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </td></tr>"""


def _also_row(it: AlertItem, rank: int, last: bool) -> str:
    c = _sev_color(it.severity)
    bb = "0" if last else f"1px solid {_DIV}"
    pct = _pct(it)
    score = f"{it.score:.0f}" if it.score is not None else "—"
    broker = f"#{it.broker}" if it.broker is not None else "—"
    return f"""
  <tr>
    <td style="padding:13px 8px 13px 0;border-bottom:{bb};" valign="middle" width="34"><span style="font-family:{_MONO};font-size:11px;color:{_FAINT};">{rank:02d}</span></td>
    <td style="padding:13px 8px;border-bottom:{bb};" valign="middle">
      <span style="font-family:{_MONO};font-size:13.5px;font-weight:600;color:{_INK};">{it.scrip}</span>
      &nbsp;<span style="font-family:{_SANS};font-size:11.5px;color:{_MUTE};">{it.company_name or ''}</span>
    </td>
    <td style="padding:13px 8px;border-bottom:{bb};white-space:nowrap;" valign="middle" align="right">
      <span style="font-family:{_MONO};font-size:11px;color:{_MUTE};">{broker}&nbsp;&middot;&nbsp;</span><span style="font-family:{_MONO};font-size:12.5px;font-weight:600;color:{c};">{pct}%</span>
    </td>
    <td style="padding:13px 0 13px 14px;border-bottom:{bb};white-space:nowrap;" valign="middle" align="right">
      <span style="font-family:{_MONO};font-size:12.5px;color:{_INK2};">{score}</span><span style="font-family:{_MONO};font-size:10px;color:{_FAINT};">/100</span>
    </td>
  </tr>"""


def _counts(items: list[AlertItem]) -> tuple[int, int, int]:
    crit = sum(1 for it in items if it.severity == "critical")
    elev = sum(1 for it in items if it.severity == "elevated")
    watch = len(items) - crit - elev
    return crit, elev, watch


def _render(items: list[AlertItem], *, title: str, lead_line: str, meta: str, subject: str, web_base: str) -> tuple[str, str, str]:
    n = len(items)
    crit, elev, watch = _counts(items)
    legend = []
    if crit:
        legend.append(f'<span style="font-family:{_MONO};font-size:10px;color:{_CRIT};">&#9679; {crit} critical</span>')
    if elev:
        legend.append(f'<span style="font-family:{_MONO};font-size:10px;color:{_ELEV};">&#9679; {elev} elevated</span>')
    if watch:
        legend.append(f'<span style="font-family:{_MONO};font-size:10px;color:{_WATCH};">&#9679; {watch} watch</span>')
    legend_html = "&nbsp;&nbsp;&nbsp;".join(legend)

    detailed = items[:_DETAIL_N]
    rest = items[_DETAIL_N:]
    cards = "".join(_card(it, i + 1, web_base) for i, it in enumerate(detailed))

    also = ""
    if rest:
        rows = "".join(_also_row(it, _DETAIL_N + 1 + i, i == len(rest) - 1) for i, it in enumerate(rest))
        also = f"""
        <tr><td style="padding:14px 26px 6px 26px;background:{_CARD};">
          <span style="font-family:{_MONO};font-size:10px;letter-spacing:.16em;color:{_MUTE};text-transform:uppercase;">Also flagged</span>
        </td></tr>
        <tr><td style="padding:4px 26px 8px 26px;background:{_CARD};">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{_CARD2};border:1px solid {_BORDER};border-radius:14px;">
            <tr><td style="padding:4px 18px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">{rows}</table>
            </td></tr>
          </table>
        </td></tr>"""

    section_count = f"{len(detailed)} of {n}"
    body = f"""<!DOCTYPE html><html lang="en"><head>
  <meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="color-scheme" content="dark" /><meta name="supported-color-schemes" content="dark" />
  <title>NEPSE Surveillance Alert</title>{_FONT_LINK}
  <style>body{{margin:0;padding:0;background:{_BG};}} table{{border-collapse:collapse;}} a{{text-decoration:none;}} @media (max-width:620px){{.container{{width:100%!important;}}}}</style>
  </head>
  <body style="margin:0;padding:0;background:{_BG};">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:{_BG};font-size:1px;line-height:1px;">{lead_line}</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{_BG};">
    <tr><td align="center" style="padding:28px 12px 40px 12px;">
      <table role="presentation" width="600" class="container" cellpadding="0" cellspacing="0" border="0" style="width:600px;max-width:600px;background:{_CARD};border:1px solid {_BORDER};border-radius:18px;overflow:hidden;">

        <!-- header -->
        <tr><td style="background:linear-gradient(135deg,#0e1626 0%,#0a0e16 60%,#0b0f18 100%);padding:30px 26px 26px 26px;border-bottom:1px solid {_BORDER};">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
            <td valign="middle">
              <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
                <td valign="middle" width="38" style="padding-right:11px;">
                  <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr><td width="38" height="38" align="center" valign="middle" style="background:{_GOLD};border-radius:9px;font-family:{_SERIF};font-size:20px;font-weight:600;color:#0b0d10;">N</td></tr></table>
                </td>
                <td valign="middle"><div style="font-family:{_MONO};font-size:10px;letter-spacing:.18em;color:{_GOLD};text-transform:uppercase;">NIMB Ace &nbsp;&middot;&nbsp; NEPSE Surveillance</div></td>
              </tr></table>
            </td>
            <td valign="middle" align="right"><span style="display:inline-block;font-family:{_MONO};font-size:10px;letter-spacing:.06em;color:{_GREEN};border:1px solid {_GREEN}44;background:{_GREEN}14;border-radius:20px;padding:4px 10px;">&#9679;&nbsp; LIVE</span></td>
          </tr></table>
          <div style="height:18px;font-size:0;line-height:0;">&nbsp;</div>
          <h1 style="margin:0;font-family:{_SERIF};font-size:34px;line-height:1.08;font-weight:600;color:{_INK};letter-spacing:-.01em;">{title}</h1>
          <p style="margin:9px 0 0 0;font-family:{_SANS};font-size:13.5px;line-height:1.5;color:{_INK2};">{lead_line}</p>
          <p style="margin:12px 0 0 0;font-family:{_MONO};font-size:10.5px;color:{_FAINT};letter-spacing:.04em;">{meta}</p>
        </td></tr>

        <!-- summary strip -->
        <tr><td style="padding:22px 26px;background:{_STRIP};border-bottom:1px solid {_BORDER};">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
            <td valign="middle" width="92"><span style="font-family:{_SERIF};font-size:52px;font-weight:600;color:{_GOLD};line-height:1;">{n}</span></td>
            <td valign="middle" style="padding-left:6px;">
              <div style="font-family:{_SANS};font-size:14px;font-weight:600;color:{_INK};letter-spacing:.01em;">Stocks at elevated manipulation risk</div>
              <div style="font-family:{_SANS};font-size:12px;color:{_MUTE};margin-top:3px;line-height:1.45;">Ranked by single-broker volume concentration. Review before acting.</div>
              <div style="margin-top:11px;">{legend_html}</div>
            </td>
          </tr></table>
        </td></tr>

        <!-- section label -->
        <tr><td style="padding:24px 26px 14px 26px;background:{_CARD};">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
            <td><span style="font-family:{_MONO};font-size:10px;letter-spacing:.16em;color:{_MUTE};text-transform:uppercase;">Top signals &middot; by concentration</span></td>
            <td align="right"><span style="font-family:{_MONO};font-size:10px;color:{_FAINT};">{section_count}</span></td>
          </tr></table>
        </td></tr>

        {cards}
        {also}

        <!-- CTA -->
        <tr><td align="center" style="padding:26px 26px 30px 26px;background:{_CARD};">
          <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr><td align="center" style="border-radius:12px;background:linear-gradient(135deg,{_GOLD_L},{_GOLD});">
            <a href="{_alerts_url(web_base)}" style="display:inline-block;font-family:{_SANS};font-size:14px;font-weight:600;color:#0b0d10;text-decoration:none;padding:15px 30px;letter-spacing:.01em;white-space:nowrap;">Open surveillance board &nbsp;&rarr;</a>
          </td></tr></table>
          <p style="margin:14px 0 0 0;font-family:{_SANS};font-size:11.5px;color:{_MUTE};">Full floor-sheet, broker tape &amp; pattern evidence for all {n} scrips.</p>
        </td></tr>

        <!-- footer -->
        <tr><td style="padding:20px 26px 24px 26px;background:{_BG};border-top:1px solid {_BORDER};">
          <p style="margin:0;font-family:{_SANS};font-size:11px;line-height:1.6;color:{_FAINT};"><span style="color:{_MUTE};font-weight:600;">Methodology.</span> Automated floor-sheet surveillance &mdash; single-broker concentration, accumulation/distribution imbalance, and matched (wash) / self-trade detection. Broker numbers are NEPSE member codes.</p>
          <p style="margin:10px 0 0 0;font-family:{_SANS};font-size:11px;line-height:1.6;color:{_FAINT};"><span style="color:{_WATCH};">Data-only &mdash; no investment recommendation implied.</span> Flags indicate unusual trading patterns warranting review, not wrongdoing.</p>
          <p style="margin:14px 0 0 0;font-family:{_MONO};font-size:10px;color:{_FAINT};letter-spacing:.03em;">NIMB Capital &middot; Research &amp; Surveillance Desk &nbsp;&nbsp;|&nbsp;&nbsp; <a href="{_alerts_url(web_base)}" style="color:{_MUTE};text-decoration:underline;">Manage alerts</a></p>
        </td></tr>
      </table>
      <div style="font-family:{_MONO};font-size:9.5px;color:#3a4252;margin-top:18px;letter-spacing:.05em;">NEPSE INTELLIGENCE PORTAL &nbsp;&middot;&nbsp; CONFIDENTIAL</div>
    </td></tr>
  </table></body></html>"""
    return subject, body, _text(items, title, web_base)


def render_digest(items: list[AlertItem], as_of: str, web_base: str = "http://localhost:3000", scanned: int | None = None) -> tuple[str, str, str]:
    items = sorted(items, key=lambda it: (-(it.volume_share or 0), -(it.score or 0)))
    n = len(items)
    if not items:
        return (f"✅ NEPSE surveillance clear — {as_of}",
                _empty_shell(as_of, web_base), _text(items, "Daily surveillance digest", web_base))
    lead = items[0]
    pct = _pct(lead)
    subject = f"🔴 {n} stocks flagged for review — NEPSE surveillance {as_of}"
    title = f"{n} stocks flagged for review"
    lead_line = (f"New floor-sheet surveillance signals — led by {lead.scrip} at "
                 f"{pct}% single-broker concentration.")
    scanned_txt = f" &middot; {scanned} scrips scanned" if scanned else ""
    meta = f"Session {as_of} &middot; floor-sheet surveillance{scanned_txt}"
    return _render(items, title=title, lead_line=lead_line, meta=meta, subject=subject, web_base=web_base)


def render_urgent(items: list[AlertItem], web_base: str = "http://localhost:3000", scanned: int | None = None) -> tuple[str, str, str]:
    items = sorted(items, key=lambda it: (-(it.volume_share or 0), -(it.score or 0)))
    n = len(items)
    lead = items[0]
    pct = _pct(lead)
    subject = f"🔴 {n} new stock{'s' if n != 1 else ''} flagged — NEPSE surveillance"
    title = f"{n} new stock{'s' if n != 1 else ''} flagged" if n != 1 else f"{lead.scrip} flagged for review"
    lead_line = f"New floor-sheet signals — led by {lead.scrip} at {pct}% single-broker concentration."
    scanned_txt = f" &middot; {scanned} scrips scanned" if scanned else ""
    meta = f"Live alert &middot; floor-sheet surveillance{scanned_txt}"
    return _render(items, title=title, lead_line=lead_line, meta=meta, subject=subject, web_base=web_base)


# ---------------------------------------------------------------- internal trade surveillance
# Same dark shell, different framing: these are OUR OWN fills flagged by the
# internal five-lens scoring (one card == one case on /surveillance). AlertItem
# carries the fund in tags[0], the tier in tags[1] and the trade date in
# tags[2]; broker/volume_share = the dominant counterparty and the share of OUR
# flow it faced (not market volume share).
def _surv_url(web_base: str) -> str:
    return f"{web_base.rstrip('/')}/surveillance"


def _card_internal(it: AlertItem, rank: int, web_base: str) -> str:
    c = _sev_color(it.severity)
    fund = it.tags[0] if it.tags else ""
    day = it.tags[2] if len(it.tags) > 2 else ""
    score = f"{it.score:.0f}" if it.score is not None else "—"
    pct = _pct(it)
    chips = "&nbsp;&nbsp;".join(
        f'<span style="display:inline-block;font-family:{_MONO};font-size:10px;letter-spacing:.04em;'
        f'color:{c};border:1px solid {c}55;background:{c}14;'
        f'border-radius:20px;padding:3px 9px;white-space:nowrap;">{p}</span>'
        for p in (it.patterns or ["Composite score"])
    )
    cp_block = ""
    if it.broker is not None and it.volume_share:
        cp_block = f"""
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:15px;">
            <tr>
              <td><span style="font-family:{_MONO};font-size:9.5px;letter-spacing:.16em;color:{_FAINT};text-transform:uppercase;">Top counterparty</span></td>
              <td align="right"><span style="font-family:{_MONO};font-size:9.5px;letter-spacing:.16em;color:{_FAINT};text-transform:uppercase;">Share of our flow</span></td>
            </tr>
            <tr>
              <td style="padding-top:2px;"><span style="font-family:{_SANS};font-size:14px;color:{_INK};font-weight:600;">Broker&nbsp;</span><span style="font-family:{_MONO};font-size:14px;color:{_GOLD_L};font-weight:600;">#{it.broker}</span></td>
              <td align="right" style="padding-top:2px;"><span style="font-family:{_MONO};font-size:17px;font-weight:600;color:{c};">{pct}%</span></td>
            </tr>
            <tr><td colspan="2" style="padding-top:9px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:separate;border-spacing:0;">
                <tr>
                  <td height="9" width="{max(1, pct)}%" style="background:{c};border-radius:6px 0 0 6px;font-size:0;line-height:0;">&nbsp;</td>
                  <td height="9" width="{max(1, 100 - pct)}%" style="background:{_TRACK};border-radius:0 6px 6px 0;font-size:0;line-height:0;">&nbsp;</td>
                </tr>
              </table></td></tr>
          </table>"""
    return f"""
  <tr><td style="padding:0 26px 14px 26px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{_CARD2};border:1px solid {_BORDER};border-radius:14px;border-collapse:separate;">
      <tr>
        <td width="4" style="background:{c};border-radius:14px 0 0 14px;font-size:0;line-height:0;">&nbsp;</td>
        <td style="padding:18px 20px 18px 22px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
            <tr>
              <td valign="middle">
                <span style="font-family:{_MONO};font-size:11px;color:{_FAINT};letter-spacing:.05em;">{rank:02d}</span>
                &nbsp;&nbsp;<span style="font-family:{_MONO};font-size:18px;font-weight:600;color:{_INK};letter-spacing:.01em;">{it.scrip}</span>
                &nbsp;<span style="font-family:{_MONO};font-size:11px;color:{_FAINT};">{day}</span>
              </td>
              <td valign="middle" align="right"><span style="display:inline-block;font-family:{_MONO};font-size:10.5px;font-weight:600;letter-spacing:.12em;color:{c};border:1px solid {c}66;background:{c}1c;border-radius:20px;padding:4px 11px;">{it.severity.upper()}</span></td>
            </tr>
            <tr><td colspan="2" style="padding-top:3px;"><span style="font-family:{_SANS};font-size:12.5px;color:{_MUTE};">{fund}</span></td></tr>
          </table>
          {cp_block}
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:16px;">
            <tr><td colspan="2"><p style="margin:0;font-family:{_SANS};font-size:12.5px;line-height:1.55;color:{_INK2};">{it.detail}</p></td></tr>
            <tr>
              <td valign="middle" style="padding-top:13px;">{chips}</td>
              <td valign="middle" align="right" style="white-space:nowrap;padding-top:13px;">
                <span style="font-family:{_MONO};font-size:9.5px;letter-spacing:.12em;color:{_FAINT};">SCORE</span>&nbsp;
                <span style="font-family:{_MONO};font-size:15px;font-weight:600;color:{_INK};">{score}</span><span style="font-family:{_MONO};font-size:11px;color:{_FAINT};">/100</span>
              </td>
            </tr>
            <tr>
              <td colspan="2" style="padding-top:14px;border-top:1px solid {_DIV};">
                <div style="height:14px;font-size:0;line-height:0;">&nbsp;</div>
                <a href="{_surv_url(web_base)}" style="font-family:{_MONO};font-size:12px;font-weight:600;color:{_GOLD};text-decoration:none;letter-spacing:.02em;">Open the case &nbsp;&rarr;</a>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </td></tr>"""


def _text_internal(items: list[AlertItem], web_base: str) -> str:
    heading = "Internal trade surveillance — new cases"
    lines = [heading, "=" * len(heading), ""]
    for i, it in enumerate(items, 1):
        fund = it.tags[0] if it.tags else ""
        day = it.tags[2] if len(it.tags) > 2 else ""
        sc = f"{it.score:.0f}/100" if it.score is not None else "—"
        lines.append(f"{i:02d}. [{it.severity.upper()}] {fund} × {it.scrip} — {day} · score {sc}")
        lines.append(f"    {it.detail}")
        lines.append("")
    lines.append(f"Open the surveillance board: {_surv_url(web_base)}")
    lines.append("A flag for review, not a verdict — fund-level attribution only.")
    return "\n".join(lines)


def render_internal_urgent(items: list[AlertItem], web_base: str = "http://localhost:3000") -> tuple[str, str, str]:
    """One consolidated email for newly-flagged INTERNAL trade cases."""
    items = sorted(items, key=lambda it: -(it.score or 0))
    n = len(items)
    crit, elev, watch = _counts(items)
    legend = []
    if crit:
        legend.append(f'<span style="font-family:{_MONO};font-size:10px;color:{_CRIT};">&#9679; {crit} high</span>')
    if elev:
        legend.append(f'<span style="font-family:{_MONO};font-size:10px;color:{_ELEV};">&#9679; {elev} elevated</span>')
    if watch:
        legend.append(f'<span style="font-family:{_MONO};font-size:10px;color:{_WATCH};">&#9679; {watch} moderate</span>')
    legend_html = "&nbsp;&nbsp;&nbsp;".join(legend)

    lead = items[0]
    lead_fund = lead.tags[0] if lead.tags else ""
    subject = f"🔎 {n} new internal trade case{'s' if n != 1 else ''} flagged — internal surveillance"
    title = f"{n} of our own trade{'s' if n != 1 else ''} flagged for review"
    lead_line = (f"The internal trade book scan flagged new case{'s' if n != 1 else ''} — "
                 f"led by {lead_fund} in {lead.scrip} (score {lead.score:.0f}).")
    cards = "".join(_card_internal(it, i + 1, web_base) for i, it in enumerate(items[:_DETAIL_N]))
    rest = items[_DETAIL_N:]
    also = ""
    if rest:
        rows = "".join(
            f"""<tr>
              <td style="padding:13px 8px 13px 0;" valign="middle" width="34"><span style="font-family:{_MONO};font-size:11px;color:{_FAINT};">{_DETAIL_N + 1 + i:02d}</span></td>
              <td style="padding:13px 8px;" valign="middle"><span style="font-family:{_MONO};font-size:13.5px;font-weight:600;color:{_INK};">{it.scrip}</span>
                &nbsp;<span style="font-family:{_SANS};font-size:11.5px;color:{_MUTE};">{it.tags[0] if it.tags else ''} &middot; {it.tags[2] if len(it.tags) > 2 else ''}</span></td>
              <td style="padding:13px 0;white-space:nowrap;" valign="middle" align="right">
                <span style="font-family:{_MONO};font-size:12.5px;color:{_INK2};">{it.score:.0f}</span><span style="font-family:{_MONO};font-size:10px;color:{_FAINT};">/100</span></td>
            </tr>"""
            for i, it in enumerate(rest)
        )
        also = f"""
        <tr><td style="padding:14px 26px 6px 26px;background:{_CARD};">
          <span style="font-family:{_MONO};font-size:10px;letter-spacing:.16em;color:{_MUTE};text-transform:uppercase;">Also flagged</span>
        </td></tr>
        <tr><td style="padding:4px 26px 8px 26px;background:{_CARD};">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{_CARD2};border:1px solid {_BORDER};border-radius:14px;">
            <tr><td style="padding:4px 18px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">{rows}</table></td></tr>
          </table>
        </td></tr>"""

    body = f"""<!DOCTYPE html><html lang="en"><head>
  <meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="color-scheme" content="dark" /><meta name="supported-color-schemes" content="dark" />
  <title>Internal Trade Surveillance</title>{_FONT_LINK}
  <style>body{{margin:0;padding:0;background:{_BG};}} table{{border-collapse:collapse;}} a{{text-decoration:none;}} @media (max-width:620px){{.container{{width:100%!important;}}}}</style>
  </head>
  <body style="margin:0;padding:0;background:{_BG};">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:{_BG};font-size:1px;line-height:1px;">{lead_line}</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{_BG};">
    <tr><td align="center" style="padding:28px 12px 40px 12px;">
      <table role="presentation" width="600" class="container" cellpadding="0" cellspacing="0" border="0" style="width:600px;max-width:600px;background:{_CARD};border:1px solid {_BORDER};border-radius:18px;overflow:hidden;">
        <tr><td style="background:linear-gradient(135deg,#0e1626 0%,#0a0e16 60%,#0b0f18 100%);padding:30px 26px 26px 26px;border-bottom:1px solid {_BORDER};">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
            <td valign="middle">
              <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
                <td valign="middle" width="38" style="padding-right:11px;">
                  <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr><td width="38" height="38" align="center" valign="middle" style="background:{_GOLD};border-radius:9px;font-family:{_SERIF};font-size:20px;font-weight:600;color:#0b0d10;">N</td></tr></table>
                </td>
                <td valign="middle"><div style="font-family:{_MONO};font-size:10px;letter-spacing:.18em;color:{_GOLD};text-transform:uppercase;">NIMB Ace &nbsp;&middot;&nbsp; Internal Trade Surveillance</div></td>
              </tr></table>
            </td>
            <td valign="middle" align="right"><span style="display:inline-block;font-family:{_MONO};font-size:10px;letter-spacing:.06em;color:{_GREEN};border:1px solid {_GREEN}44;background:{_GREEN}14;border-radius:20px;padding:4px 10px;">&#9679;&nbsp; OUR BOOK</span></td>
          </tr></table>
          <div style="height:18px;font-size:0;line-height:0;">&nbsp;</div>
          <h1 style="margin:0;font-family:{_SERIF};font-size:32px;line-height:1.1;font-weight:600;color:{_INK};letter-spacing:-.01em;">{title}</h1>
          <p style="margin:9px 0 0 0;font-family:{_SANS};font-size:13.5px;line-height:1.5;color:{_INK2};">{lead_line}</p>
          <p style="margin:12px 0 0 0;font-family:{_MONO};font-size:10.5px;color:{_FAINT};letter-spacing:.04em;">Live alert &middot; our own fills &middot; five-lens scoring</p>
        </td></tr>
        <tr><td style="padding:22px 26px;background:{_STRIP};border-bottom:1px solid {_BORDER};">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
            <td valign="middle" width="92"><span style="font-family:{_SERIF};font-size:52px;font-weight:600;color:{_GOLD};line-height:1;">{n}</span></td>
            <td valign="middle" style="padding-left:6px;">
              <div style="font-family:{_SANS};font-size:14px;font-weight:600;color:{_INK};letter-spacing:.01em;">New cases on our own trade book</div>
              <div style="font-family:{_SANS};font-size:12px;color:{_MUTE};margin-top:3px;line-height:1.45;">Execution quality &middot; scrip context &middot; counterparty pattern &middot; intra-firm crossing &middot; post-trade outcome.</div>
              <div style="margin-top:11px;">{legend_html}</div>
            </td>
          </tr></table>
        </td></tr>
        <tr><td style="padding:24px 26px 14px 26px;background:{_CARD};">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
            <td><span style="font-family:{_MONO};font-size:10px;letter-spacing:.16em;color:{_MUTE};text-transform:uppercase;">New cases &middot; by score</span></td>
            <td align="right"><span style="font-family:{_MONO};font-size:10px;color:{_FAINT};">{min(n, _DETAIL_N)} of {n}</span></td>
          </tr></table>
        </td></tr>
        {cards}
        {also}
        <tr><td align="center" style="padding:26px 26px 30px 26px;background:{_CARD};">
          <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr><td align="center" style="border-radius:12px;background:linear-gradient(135deg,{_GOLD_L},{_GOLD});">
            <a href="{_surv_url(web_base)}" style="display:inline-block;font-family:{_SANS};font-size:14px;font-weight:600;color:#0b0d10;text-decoration:none;padding:15px 30px;letter-spacing:.01em;white-space:nowrap;">Open the surveillance board &nbsp;&rarr;</a>
          </td></tr></table>
          <p style="margin:14px 0 0 0;font-family:{_SANS};font-size:11.5px;color:{_MUTE};">Full case dossiers &mdash; fill clusters, markout curves, counterparty stats &amp; case notes.</p>
        </td></tr>
        <tr><td style="padding:20px 26px 24px 26px;background:{_BG};border-top:1px solid {_BORDER};">
          <p style="margin:0;font-family:{_SANS};font-size:11px;line-height:1.6;color:{_FAINT};"><span style="color:{_MUTE};font-weight:600;">Methodology.</span> Each of our fills is scored through five lenses &mdash; execution vs interval VWAP, scrip manipulation context, counterparty surprise, intra-firm crossing and post-trade markouts &mdash; then grouped into fund &times; scrip &times; day cases.</p>
          <p style="margin:10px 0 0 0;font-family:{_SANS};font-size:11px;line-height:1.6;color:{_FAINT};"><span style="color:{_WATCH};">A flag for review, not a verdict.</span> Attribution is at the fund level, deliberately never at the individual level.</p>
          <p style="margin:14px 0 0 0;font-family:{_MONO};font-size:10px;color:{_FAINT};letter-spacing:.03em;">NIMB Capital &middot; Research &amp; Surveillance Desk &nbsp;&nbsp;|&nbsp;&nbsp; <a href="{_alerts_url(web_base)}" style="color:{_MUTE};text-decoration:underline;">Manage alerts</a></p>
        </td></tr>
      </table>
      <div style="font-family:{_MONO};font-size:9.5px;color:#3a4252;margin-top:18px;letter-spacing:.05em;">NEPSE INTELLIGENCE PORTAL &nbsp;&middot;&nbsp; CONFIDENTIAL</div>
    </td></tr>
  </table></body></html>"""
    return subject, body, _text_internal(items, web_base)


def _empty_shell(as_of: str, web_base: str) -> str:
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"/>{_FONT_LINK}</head>
  <body style="margin:0;background:{_BG};"><table width="100%" style="background:{_BG};"><tr><td align="center" style="padding:40px 12px;">
    <table width="600" style="max-width:600px;background:{_CARD};border:1px solid {_BORDER};border-radius:18px;"><tr><td style="padding:34px 28px;">
      <div style="font-family:{_MONO};font-size:10px;letter-spacing:.18em;color:{_GOLD};text-transform:uppercase;">NIMB Ace &middot; NEPSE Surveillance</div>
      <h1 style="margin:12px 0 0;font-family:{_SERIF};font-size:28px;font-weight:600;color:{_INK};">All clear &mdash; {as_of}</h1>
      <p style="margin:10px 0 0;font-family:{_SANS};font-size:13.5px;color:{_INK2};line-height:1.5;">No stocks crossed the manipulation-risk threshold on the floor today. The surveillance engine is running.</p>
      <p style="margin:18px 0 0;"><a href="{_alerts_url(web_base)}" style="font-family:{_MONO};font-size:12px;color:{_GOLD};">Open surveillance board &rarr;</a></p>
    </td></tr></table>
  </td></tr></table></body></html>"""


def _text(items: list[AlertItem], heading: str, web_base: str) -> str:
    lines = [heading, "=" * len(heading), ""]
    if not items:
        lines.append("No stocks crossed the manipulation-risk threshold today.")
        return "\n".join(lines)
    lines.append(f"{len(items)} stocks flagged — ranked by single-broker concentration:\n")
    for i, it in enumerate(items, 1):
        pct = _pct(it)
        sc = f"{it.score:.0f}/100" if it.score is not None else "—"
        broker = f"#{it.broker}" if it.broker is not None else "—"
        lines.append(f"{i:02d}. [{it.severity.upper()}] {it.scrip} — {it.company_name or ''}")
        lines.append(f"    Broker {broker} · {pct}% of volume · score {sc} · {', '.join(it.patterns)}")
        lines.append(f"    {_scrip_url(web_base, it.scrip)}")
        lines.append("")
    lines.append(f"Open surveillance board: {_alerts_url(web_base)}")
    lines.append("Automated floor-sheet surveillance — data only, no recommendation implied.")
    return "\n".join(lines)
