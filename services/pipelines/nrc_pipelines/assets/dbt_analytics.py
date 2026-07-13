"""dagster-dbt integration — every dbt Gold model surfaces as a Dagster asset.

How it works:
  * `DbtProject` points at the top-level `dbt/` directory. In dev it calls
    `dbt parse` on import to keep the manifest fresh; in prod the manifest
    is pre-compiled so startup stays fast.
  * `DagsterDbtTranslator` maps dbt `source('silver', <table>)` references
    back to the Python Silver Dagster asset keys (which currently use the
    `silver_<table>` naming). This makes dbt model deps show up in the
    Dagster UI as edges from the Silver Python assets.
  * `@dbt_assets` expands into one Dagster asset per dbt model. All of
    them materialize in a single `dbt build` invocation (so dbt handles
    the internal DAG; Dagster wraps the whole thing as a multi-asset).

New dbt models added under `dbt/models/` automatically appear in Dagster
once `dbt parse` regenerates the manifest. No code changes needed here."""
from pathlib import Path
from typing import Any

from dagster import AssetExecutionContext, AssetKey
from dagster_dbt import (
    DagsterDbtTranslator,
    DbtCliResource,
    DbtProject,
    dbt_assets,
)

# Repo root / dbt project dir. Resolved at import time so the manifest
# path is stable regardless of CWD.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_DBT_PROJECT_DIR = _REPO_ROOT / "dbt"

# DbtProject packages project-dir + profile-dir + manifest location into one
# handle. `prepare_if_dev()` re-runs `dbt parse` on module load so the
# manifest matches model source, but is a no-op in a built artifact (when
# DAGSTER_IS_DEV_CLI is unset) — that keeps prod boot cheap.
dbt_project = DbtProject(
    project_dir=_DBT_PROJECT_DIR,
    profiles_dir=_DBT_PROJECT_DIR,
    target="dev",
)
dbt_project.prepare_if_dev()


class NrcDbtTranslator(DagsterDbtTranslator):
    """Bridges dbt source names → our Python Silver asset keys.

    Silver Python assets currently use the redundant naming pattern
    `AssetKey(["silver", "silver_fundamentals_long"])`. dbt sources look
    like `source('silver', 'fundamentals_long')`. This translator rewrites
    the dbt-side source key to match the Python asset key so dagster-dbt
    draws the correct upstream edge.

    When the Python Silver assets get renamed to drop the `silver_`
    prefix (future cleanup), this translator simplifies to pass-through
    and the whole class can be removed."""

    def get_asset_key(self, dbt_resource_props: dict[str, Any]) -> AssetKey:
        if dbt_resource_props.get("resource_type") == "source":
            source_group = dbt_resource_props["source_name"]
            table_name = dbt_resource_props["name"]
            return AssetKey([source_group, f"{source_group}_{table_name}"])
        return super().get_asset_key(dbt_resource_props)


@dbt_assets(
    manifest=dbt_project.manifest_path,
    dagster_dbt_translator=NrcDbtTranslator(),
)
def dbt_gold_assets(context: AssetExecutionContext, dbt: DbtCliResource):
    """Materialize every dbt model + run its tests in one dbt build invocation.

    `dbt build` runs `dbt run` followed by `dbt test` in dependency order,
    so model failures short-circuit before we burn compute on downstream
    models. Test failures surface in the Dagster UI as AssetCheck events
    (dagster-dbt handles the translation automatically)."""
    yield from dbt.cli(["build"], context=context).stream()
