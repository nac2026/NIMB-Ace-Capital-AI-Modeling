# 01 — Prerequisites

Everything the server needs before the first deploy. See [README](README.md) for the big
picture and [02-environment](02-environment.md) for the variables you'll set once the
software is installed.

---

## Server sizing

The prototype stack is modest. Container memory limits are declared in
`docker-compose.yml` (MinIO 400M, Postgres 800M, Redis 200M). The app processes (Python
API, Dagster, Next.js) and the DuckDB compute jobs are the variable cost.

| Profile | vCPU | RAM | Disk | Suitable for |
|---------|------|-----|------|--------------|
| Minimum | 2 | 4 GB | 40 GB SSD | Single-user demo, light pipeline runs |
| **Recommended** | 4 | 8 GB | 80–100 GB SSD | Production single-tenant, daily EOD + surveillance |
| Comfortable | 8 | 16 GB | 200 GB SSD | Headroom for concurrent Dagster + dbt + web build |

Notes:
- **Disk is the thing to watch.** MinIO Delta tables (`nepse-lakehouse`), raw snapshots,
  the uploads bucket, and Postgres data all live under `./data/`. Budget for growth and
  for backups (see [09-backup-restore](09-backup-restore.md)).
- The Next.js production build (`npm run build`) is memory-hungry; on a 4 GB box give it
  swap or build during a quiet window.

---

## Operating system

- **Linux (x86-64)** — Ubuntu 22.04 LTS or Debian 12 recommended. Any distro with a
  current Docker Engine + systemd works.
- 64-bit only. The container images (`pgvector/pgvector:pg16`, `minio/minio`, `redis:7`)
  are multi-arch, but standardize on amd64 for the server.

---

## Required software

| Software | Version | Why | Install |
|----------|---------|-----|---------|
| Docker Engine | 24+ | Runs MinIO, Postgres, Redis | https://docs.docker.com/engine/install/ |
| Docker Compose | v2 (plugin) | `make up` uses `docker compose` | bundled with Docker Engine |
| Python | **3.12** (`>=3.12,<3.13`) | Workspace requires-python | https://www.python.org/downloads/ |
| uv | latest | Installs/runs the Python workspace | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js | **20+** | Builds/serves the Next.js 16 app | https://nodejs.org (or nvm) |
| npm | 10+ | Bundled with Node 20 | — |
| git | any | Pull the client repo | distro package |
| make | any | Runbook shortcuts | distro package (`build-essential`) |

Optional but recommended:
- **`mc`** (MinIO client) — bucket backups + scoped-account creation ([07](07-minio-hardening.md), [09](09-backup-restore.md)).
- **A process supervisor** — systemd (default on the server) or pm2 for the Node/Python
  processes ([04-services](04-services.md)).

Verify versions:

```bash
docker --version           # 24+
docker compose version     # v2.x
python3 --version          # 3.12.x   (uv can also manage this: `uv python install 3.12`)
uv --version
node --version             # v20+
npm --version              # 10+
```

> The `requires-python = ">=3.12,<3.13"` pin is enforced by every workspace member's
> `pyproject.toml`. If the system Python differs, let `uv` provision 3.12 with
> `uv python install 3.12`.

---

## Outbound network access

The server must reach these hosts. **Only inbound `443` needs to be open** (see
[05-firewall-ports](05-firewall-ports.md)); everything below is outbound.

| Destination | Purpose | Protocol |
|-------------|---------|----------|
| Vertex AI (`*.googleapis.com`, Gemini) | LLM intent + synthesis | HTTPS 443 |
| `dataapi.smtmcapital.com.np` (SMTM) | Live NEPSE market feed | HTTPS 443 |
| News RSS (`sharesansar.com/rss`, `news.google.com/rss`) | Ambient news ingestion | HTTPS 443 |
| Resend / SendGrid / SMTP host | Email alerts (if enabled) | HTTPS 443 / SMTP 587 |
| `ghcr.io`, Docker Hub, PyPI, npm registry, `astral.sh` | Image/dep pulls at deploy time | HTTPS 443 |
| GitHub (`github.com`) | `git pull` of the client repo | HTTPS/SSH |

If the server sits behind an egress proxy or allow-list firewall, whitelist the above.
The credentials for Vertex, SMTM, and notifications are set in `.env` — see
[02-environment](02-environment.md).
