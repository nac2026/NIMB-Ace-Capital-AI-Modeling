{# -
    Construct the s3:// Delta location for a Gold model.

    Used as:
        {{ config(location=gold_external_location()) }}

    at the top of each gold model. Factoring the URI into a macro keeps
    the lakehouse root overridable via the NRC_LAKEHOUSE_URI env var
    (useful for CI fixtures, alternate MinIO tenants, or future Spark/S3
    migration) without touching model files.
- #}

{% macro gold_external_location(table_name=none) -%}
    {%- set name = table_name if table_name else this.identifier -%}
    {{ env_var('NRC_LAKEHOUSE_URI', 's3://nepse-lakehouse') }}/gold/{{ name }}.parquet
{%- endmacro %}
