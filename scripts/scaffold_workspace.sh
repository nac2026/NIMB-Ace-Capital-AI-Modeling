#!/usr/bin/env bash
# One-shot scaffold of uv-workspace members. Idempotent: skips existing files.
set -euo pipefail
cd "$(dirname "$0")/.."

make_member() {
    local kind="$1"        # libs | services
    local slug="$2"        # short name, e.g. "contracts"
    local pyname="nrc_${slug//-/_}"
    local pkgname="nrc-${slug}"
    local desc="$3"
    local deps="$4"        # comma-separated python deps (may be empty)

    local dir="${kind}/${slug}"
    mkdir -p "${dir}/${pyname}"

    # __init__.py
    if [[ ! -f "${dir}/${pyname}/__init__.py" ]]; then
        cat >"${dir}/${pyname}/__init__.py" <<EOF
"""${desc}"""
__version__ = "0.1.0"
EOF
    fi

    # pyproject.toml
    if [[ ! -f "${dir}/pyproject.toml" ]]; then
        local deps_block=""
        if [[ -n "${deps}" ]]; then
            deps_block='dependencies = ['
            IFS=',' read -ra arr <<<"${deps}"
            for d in "${arr[@]}"; do
                deps_block+=$'\n  "'${d}'",'
            done
            deps_block+=$'\n]'
        else
            deps_block='dependencies = []'
        fi

        cat >"${dir}/pyproject.toml" <<EOF
[project]
name = "${pkgname}"
version = "0.1.0"
description = "${desc}"
requires-python = ">=3.12,<3.13"
${deps_block}

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["${pyname}"]
EOF
    fi
    echo "  ✓ ${kind}/${slug}"
}

echo "→ libs/"
make_member libs contracts      "Shared Pydantic schemas (Quote, OHLCV, Fundamentals, NewsArticle, QueryTrace)" "pydantic>=2.8,python-dateutil>=2.9"
make_member libs compute        "ComputeEngine abstraction — DuckDB (local) / Spark (prod)"                     ""
make_member libs storage        "Storage clients — MinIO, Delta (via delta-rs), Postgres, Redis"                ""
make_member libs llm            "LLM provider abstraction — Claude, Gemini, vLLM"                               ""
make_member libs embeddings     "Embedding provider abstraction (bge-m3)"                                        ""
make_member libs nepal          "Nepal-specific utilities — Bikram Sambat calendar, Devanagari helpers"         ""
make_member libs observability  "Structured logging + OpenTelemetry setup"                                      ""

echo "→ services/"
make_member services ingestion    "Scrape → Bronze ingestion"                                        "nrc-contracts"
make_member services processing   "Bronze → Silver → Gold processing jobs"                            "nrc-contracts,nrc-nepal"
make_member services tools        "Typed-tool FastAPI service (later phase)"                          ""
make_member services orchestrator "LLM agent loop FastAPI service (later phase)"                      ""

# Placeholder dirs for later phases
for d in pipelines migrations scripts config tests/unit tests/integration tests/fixtures; do
    mkdir -p "$d"
    [[ -f "${d}/.gitkeep" ]] || touch "${d}/.gitkeep"
done

echo
echo "✓ scaffold complete."
