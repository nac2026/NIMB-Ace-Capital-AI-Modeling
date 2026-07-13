{# -
    CASE expression mirroring nrc_ingestion.source_tier_rank_sql. Used when
    a Gold model needs to break ties or weight rows by source quality —
    e.g., when two sources cover the same (scrip, date) in a Gold-level
    union, this ranks them so the authoritative row wins.

    Kept here as a macro so changing the tier order only requires an edit
    in one place across the whole dbt project. Lower rank = higher quality.

    Usage:
        {{ source_tier_rank('source_tier') }} AS tier_rank
- #}

{% macro source_tier_rank(column='source_tier') -%}
    CASE {{ column }}
        WHEN 'client_authoritative' THEN 0
        WHEN 'client_historical'    THEN 1
        WHEN 'live_api'             THEN 2
        WHEN 'scraped'              THEN 3
        ELSE 4
    END
{%- endmacro %}
