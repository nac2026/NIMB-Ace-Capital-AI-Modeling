"""Silver transform: bronze.corporate_actions_raw → silver.corporate_actions.

Conforms to nrc_contracts.CorporateAction. Three things happen here:
  1. fiscal_year_bs_raw ('2081/2082') → fiscal_year_bs (int 2081) via
     nrc_nepal.parse_fiscal_year.
  2. action_type uppercase → enum-valued lowercase ('BONUS' → 'bonus').
  3. Ratios are normalized:
       * BONUS / CASH_DIVIDEND: ratio_pct (percent) → ratio (fraction, e.g. 12.5 → 0.125).
         For CASH_DIVIDEND, `amount` is derived as `ratio_pct × paid_up_value / 100`.
       * RIGHTS: ratio_raw '2:1' → ratio 2/1=2.0 (new shares per existing share).
         Accepts forms '2:1', '10:2.5', '1:9.5157'. Malformed rows are dropped.
  4. Limited to active scrips (via silver.scrip_master)."""
from __future__ import annotations
from datetime import datetime, timezone

import pyarrow as pa
from pydantic import ValidationError

from nrc_compute import DuckDBEngine
from nrc_contracts import ActionType, CorporateAction
from nrc_nepal import parse_fiscal_year
from nrc_storage import DeltaIO, StorageSettings, get_settings

from ._report import ProcessingReport

_SRC = "bronze.corporate_actions_raw"
_MASTER = "silver.scrip_master"
_DST = "silver.corporate_actions"


def _parse_rights_ratio(raw: str | None) -> float | None:
    """Parse a Sharesansar rights ratio string ('2:1', '10:2.5', '1:9.5157').

    The convention is `existing:new` — so '2:1' means 1 new share per 2
    existing, i.e. ratio=0.5. Returns None for malformed input."""
    if not raw:
        return None
    parts = raw.strip().split(":")
    if len(parts) != 2:
        return None
    try:
        existing, new = float(parts[0]), float(parts[1])
    except ValueError:
        return None
    if existing <= 0:
        return None
    return new / existing


def transform_corporate_actions(
    *,
    settings: StorageSettings | None = None,
    mode: str = "overwrite",
    active_only: bool = True,
) -> ProcessingReport:
    started_at = datetime.now(timezone.utc)
    settings = settings or get_settings()

    with DuckDBEngine(settings) as engine:
        engine.register_table("bca", _SRC)
        engine.register_table("sm", _MASTER)
        rows_read = engine.sql("SELECT COUNT(*) AS n FROM bca").to_pylist()[0]["n"]

        active_filter = "JOIN sm ON sm.scrip = bca.scrip AND sm.is_active" if active_only else "LEFT JOIN sm ON sm.scrip = bca.scrip"

        raw = engine.sql(f"""
            SELECT
                bca.scrip,
                bca.action_type,
                bca.fiscal_year_bs_raw,
                bca.announcement_date,
                bca.bookclose_date,
                bca.distribution_date,
                bca.opening_date,
                bca.closing_date,
                bca.ratio_pct,
                bca.ratio_raw,
                bca.issue_price,
                COALESCE(sm.paid_up_value, 100.0) AS paid_up_value
            FROM bca
            {active_filter}
        """)

    # Python-side conformance: parse FY string + rights ratio + map enum + derive amount.
    warnings: list[str] = []
    conformed_rows = []
    for r in raw.to_pylist():
        try:
            fy_bs = parse_fiscal_year(r["fiscal_year_bs_raw"]) if r["fiscal_year_bs_raw"] else None
        except ValueError as e:
            warnings.append(f"{r['scrip']} {r['action_type']}: bad FY {r['fiscal_year_bs_raw']!r} ({e})")
            fy_bs = None

        action_type = r["action_type"].lower()
        if action_type not in {at.value for at in ActionType}:
            warnings.append(f"{r['scrip']}: unknown action_type {action_type!r}")
            continue

        ratio: float | None
        amount: float | None = None
        if action_type == "rights":
            ratio = _parse_rights_ratio(r["ratio_raw"])
            if ratio is None:
                warnings.append(f"{r['scrip']}: unparseable rights ratio {r['ratio_raw']!r}")
                continue
        else:  # BONUS or CASH_DIVIDEND — ratio_pct is the percent scale
            pct = r["ratio_pct"]
            if pct is None:
                continue
            ratio = pct / 100.0
            if action_type == "cash_dividend":
                # amount per share = (pct / 100) × paid_up_value
                amount = ratio * float(r["paid_up_value"])

        # ex_date convention: dividends+bonus = bookclose_date; rights = opening_date
        ex_date = r["bookclose_date"] if action_type != "rights" else r["opening_date"]

        row = {
            "scrip": r["scrip"],
            "action_type": action_type,
            "ratio": ratio,
            "amount": amount,
            "announcement_date": r["announcement_date"],
            "book_closure_date": r["bookclose_date"],
            "ex_date": ex_date,
            "fiscal_year_bs": fy_bs,
            "source": "sharesansar",
        }
        try:
            CorporateAction.model_validate(row)
            conformed_rows.append(row)
        except ValidationError as e:
            warnings.append(f"{r['scrip']} {action_type}: {e.errors()[0]['msg']}")

    # Build the pyarrow schema explicitly since some dates can be None.
    schema = pa.schema([
        ("scrip", pa.string()),
        ("action_type", pa.string()),
        ("ratio", pa.float64()),
        ("amount", pa.float64()),
        ("announcement_date", pa.date32()),
        ("book_closure_date", pa.date32()),
        ("ex_date", pa.date32()),
        ("fiscal_year_bs", pa.int32()),
        ("source", pa.string()),
    ])
    valid = pa.Table.from_pylist(conformed_rows, schema=schema)
    io = DeltaIO(settings)
    io.write(_DST, valid, mode=mode)

    return ProcessingReport(
        table=_DST,
        rows_read=rows_read,
        rows_written=valid.num_rows,
        delta_version=io.version(_DST),
        started_at=started_at,
        warnings=warnings,
    )
