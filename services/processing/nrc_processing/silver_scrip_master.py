"""Silver transform: bronze scrip-master → silver.scrip_master.

Primary source is SMTM `company_list` (bronze.scrip_master_smtm_raw) — the full
all-sector universe with canonical sectors and explicit active/inactive status.
Share-structure fields SMTM doesn't carry (listed_shares, paid_up, registered
date, contacts) are enriched from the legacy Sharesansar scrape
(bronze.scrip_master_raw) where it overlaps.

Non-equity instruments (bonds, mutual funds, preferred) are excluded — this is
the equity research universe. Every row is validated against the ScripMaster
contract; invalid rows are dropped with a warning.

Falls back to the legacy scraper-only path when the SMTM Bronze table is absent
(keeps the old pipeline runnable without live data)."""
from __future__ import annotations
from datetime import datetime, timezone

import pyarrow as pa
from pydantic import ValidationError

from nrc_compute import DuckDBEngine
from nrc_contracts import ScripMaster
from nrc_nepal import canonical_ticker
from nrc_storage import DeltaIO, StorageSettings, get_settings

from ._report import ProcessingReport

_SMTM_SRC = "bronze.scrip_master_smtm_raw"
_SCRAPER_SRC = "bronze.scrip_master_raw"
_DST = "silver.scrip_master"


def transform_scrip_master(
    *,
    settings: StorageSettings | None = None,
    mode: str = "overwrite",
) -> ProcessingReport:
    started_at = datetime.now(timezone.utc)
    settings = settings or get_settings()
    io = DeltaIO(settings)
    has_smtm = io.exists(_SMTM_SRC)
    has_scraper = io.exists(_SCRAPER_SRC)

    with DuckDBEngine(settings) as engine:
        engine._conn.create_function(  # pyright: ignore[reportPrivateUsage]
            "canonical_ticker", canonical_ticker, ["VARCHAR"], "VARCHAR"
        )

        if has_smtm:
            engine.register_table("smtm", _SMTM_SRC)
            rows_read = engine.sql(
                "SELECT COUNT(*) AS n FROM smtm WHERE is_equity"
            ).to_pylist()[0]["n"]

            # Enrich share-structure + contacts from the scraper where it overlaps.
            if has_scraper:
                engine.register_table("scraper", _SCRAPER_SRC)
                enrich_cte = """
                    enrich AS (
                        SELECT
                            canonical_ticker(scrip) AS scrip,
                            ANY_VALUE(sub_sector)       AS sub_sector,
                            ANY_VALUE(listed_shares)    AS listed_shares,
                            ANY_VALUE(paid_up_value)    AS paid_up_value,
                            ANY_VALUE(paid_up_capital)  AS paid_up_capital,
                            ANY_VALUE(registered_date)  AS registered_date,
                            ANY_VALUE(phone)            AS phone,
                            ANY_VALUE(address)          AS address
                        FROM scraper GROUP BY canonical_ticker(scrip)
                    )
                """
                enrich_join = "LEFT JOIN enrich e USING (scrip)"
            else:
                enrich_cte = """
                    enrich AS (SELECT NULL::VARCHAR AS scrip WHERE FALSE)
                """
                enrich_join = "LEFT JOIN enrich e USING (scrip)"

            conformed = engine.sql(f"""
                WITH {enrich_cte}
                SELECT
                    s.scrip,
                    COALESCE(NULLIF(TRIM(s.company_name), ''),
                             NULLIF(TRIM(s.security_name), ''), s.scrip) AS company_name,
                    s.sector,
                    e.sub_sector                              AS sub_sector,
                    e.listed_shares                           AS listed_shares,
                    e.paid_up_value                           AS paid_up_value,
                    e.paid_up_capital                         AS paid_up_capital,
                    CAST(NULL AS DOUBLE)                      AS promoter_shares,
                    CAST(NULL AS DOUBLE)                      AS public_shares,
                    CAST(NULL AS VARCHAR)                     AS isin,
                    e.registered_date                         AS registered_date,
                    e.phone                                   AS phone,
                    s.email                                   AS email,
                    e.address                                 AS address,
                    s.website                                 AS website,
                    s.is_active                               AS is_active,
                    s.company_id                              AS company_id
                FROM smtm s
                {enrich_join}
                WHERE s.is_equity
            """)
        else:
            # Legacy fallback: scraper-only, banks universe.
            if not has_scraper:
                raise FileNotFoundError(
                    f"neither {_SMTM_SRC} nor {_SCRAPER_SRC} exists — run an ingest first"
                )
            engine.register_table("raw", _SCRAPER_SRC)
            rows_read = engine.sql("SELECT COUNT(*) AS n FROM raw").to_pylist()[0]["n"]
            conformed = engine.sql("""
                SELECT
                    canonical_ticker(scrip) AS scrip,
                    company_name,
                    CASE WHEN sector = 'Merged' THEN 'Commercial Bank' ELSE sector END AS sector,
                    sub_sector,
                    listed_shares, paid_up_value, paid_up_capital,
                    CAST(NULL AS DOUBLE)  AS promoter_shares,
                    CAST(NULL AS DOUBLE)  AS public_shares,
                    CAST(NULL AS VARCHAR) AS isin,
                    registered_date, phone, email, address, website,
                    CASE WHEN sector = 'Merged' THEN FALSE ELSE TRUE END AS is_active,
                    company_id
                FROM raw
            """)

    warnings: list[str] = []
    valid_rows = []
    for row in conformed.to_pylist():
        try:
            ScripMaster.model_validate(row)
            valid_rows.append(row)
        except ValidationError as e:
            warnings.append(f"scrip={row.get('scrip')}: {e.errors()[0]['msg']}")

    valid = pa.Table.from_pylist(valid_rows, schema=conformed.schema)
    io.write(_DST, valid, mode=mode, schema_mode="overwrite" if mode == "overwrite" else None)

    return ProcessingReport(
        table=_DST,
        rows_read=rows_read,
        rows_written=valid.num_rows,
        delta_version=io.version(_DST),
        started_at=started_at,
        warnings=warnings,
    )
