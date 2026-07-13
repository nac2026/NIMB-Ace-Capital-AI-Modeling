# NRC Orchestrator — FastAPI chat service.
# Multi-stage build: builder installs the uv monorepo; runtime carries only
# the resolved .venv + the source for the orchestrator and its deps.

# ----------------------------------------------------------------- builder
FROM python:3.12-slim AS builder

# Install uv (the package manager we use for the monorepo).
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /uvx /usr/local/bin/

WORKDIR /build

# Copy the whole workspace — uv needs all workspace members at resolve time.
# This is cheaper than it looks: Docker caches unchanged layers, so the slow
# uv sync only re-runs when pyproject.toml files change.
COPY pyproject.toml uv.lock ./
COPY libs ./libs
COPY services ./services

# Install into a venv under /build/.venv with no dev deps, frozen lockfile.
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_CACHE=1
RUN uv sync --frozen --no-dev

# ----------------------------------------------------------------- runtime
FROM python:3.12-slim AS runtime

# Non-root user — Cloud Run / GKE best practice.
RUN useradd --create-home --uid 10001 nrc

WORKDIR /app

# Copy resolved venv + code.
COPY --from=builder /build/.venv /app/.venv
COPY --from=builder /build/libs /app/libs
COPY --from=builder /build/services /app/services
COPY --from=builder /build/pyproject.toml /app/pyproject.toml

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    NRC_HOST=0.0.0.0 \
    NRC_PORT=8080 \
    LOG_LEVEL=info

USER nrc

EXPOSE 8080

# Cloud Run sets PORT; honour it.
CMD ["sh", "-c", "uvicorn nrc_orchestrator.server:app --host 0.0.0.0 --port ${PORT:-8080} --log-level ${LOG_LEVEL}"]
