# 04 — App services

The app tier runs as **long-running host processes**, not containers. There are four:

| Service | Port | Command | Public? |
|---------|------|---------|---------|
| FastAPI orchestrator API | 8080 | `uv run nrc-serve` | proxied (internal bind) |
| Next.js web app | 3000 | `cd services/web && npm run start` | proxied (internal bind) |
| Dagster UI (pipelines) | 3001 | `make dagster-dev` | **internal-only** |
| dbt docs | 8081 | `make dbt-docs` | **internal-only** |

Only the reverse proxy on `:443` is public (see [05-firewall-ports](05-firewall-ports.md)).
The API entrypoint `nrc-serve` maps to `nrc_orchestrator.server:main`; it binds
`NRC_HOST` (default `127.0.0.1`) : `NRC_PORT` (default `8080`).

Assume the repo is checked out at `/opt/nimb-ace/nep-trade-analytics` and runs as the
service user `nimb`. Adjust paths/users to your host.

---

## Build the web app (production)

The Next.js 16 app must be **built** before `start` (dev uses `npm run dev`, prod uses
`build` + `start`). `services/web` is excluded from the uv workspace and managed by npm.

```bash
cd services/web
npm install            # first time + whenever package.json changes
npm run build          # produces the optimized production build
npm run start          # serves the built app on :3000
```

Env the web build/runtime reads: `NEXT_PUBLIC_BACKEND_URL` (default
`http://localhost:8080`) — set it if the API is on a different host/port.

---

## Env injection

All four processes need the repo-root `.env`:

- **Python (`nrc-serve`, Dagster, dbt):** `uv run` and the Makefile dbt targets load the
  root `.env` (the dbt targets pass `--env-file ../.env` explicitly). For systemd, point
  `EnvironmentFile=` at the same `.env`.
- **Node (`npm run start`):** Next.js reads `.env` from `services/web/` for its own vars;
  set `NEXT_PUBLIC_BACKEND_URL` there or in the unit's `Environment=`.

Keep `NRC_HOST=127.0.0.1` so the API is only reachable via the proxy.

---

## systemd units (recommended)

Create these under `/etc/systemd/system/`. They start after Docker infra is up.

### `nimb-api.service`

```ini
[Unit]
Description=NIMB Ace — FastAPI orchestrator API (:8080)
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
User=nimb
WorkingDirectory=/opt/nimb-ace/nep-trade-analytics
EnvironmentFile=/opt/nimb-ace/nep-trade-analytics/.env
Environment=NRC_HOST=127.0.0.1
Environment=NRC_PORT=8080
ExecStart=/usr/bin/uv run nrc-serve
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### `nimb-web.service`

```ini
[Unit]
Description=NIMB Ace — Next.js web app (:3000)
After=network-online.target nimb-api.service
Wants=network-online.target

[Service]
Type=simple
User=nimb
WorkingDirectory=/opt/nimb-ace/nep-trade-analytics/services/web
Environment=NEXT_PUBLIC_BACKEND_URL=http://127.0.0.1:8080
Environment=PORT=3000
ExecStart=/usr/bin/npm run start
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### `nimb-dagster.service`

```ini
[Unit]
Description=NIMB Ace — Dagster UI + pipelines (:3001)
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
User=nimb
WorkingDirectory=/opt/nimb-ace/nep-trade-analytics
EnvironmentFile=/opt/nimb-ace/nep-trade-analytics/.env
ExecStart=/usr/bin/uv run dagster dev -m nrc_pipelines --port 3001
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

> `dagster dev` is the single-process dev/prototype server used throughout this repo
> (`make dagster-dev`). It hosts the UI **and** runs the jobs. Bind it to loopback / keep
> `:3001` firewalled. dbt-docs (`make dbt-docs`, `:8081`) is generate-and-serve and is
> typically run on demand rather than as a permanent unit; add an analogous unit only if
> you want it always-on.

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now nimb-api nimb-web nimb-dagster
sudo systemctl status nimb-api          # check
journalctl -u nimb-api -f               # logs
```

Start order: **infra (`make up`) → API → Dagster → web** ([10-runbook](10-runbook.md)).

---

## pm2 alternative

If you prefer pm2 over systemd, an `ecosystem.config.js` at the repo root:

```js
module.exports = {
  apps: [
    {
      name: "nimb-api",
      cwd: "/opt/nimb-ace/nep-trade-analytics",
      script: "uv",
      args: "run nrc-serve",
      env: { NRC_HOST: "127.0.0.1", NRC_PORT: "8080" },
    },
    {
      name: "nimb-web",
      cwd: "/opt/nimb-ace/nep-trade-analytics/services/web",
      script: "npm",
      args: "run start",
      env: { NEXT_PUBLIC_BACKEND_URL: "http://127.0.0.1:8080", PORT: "3000" },
    },
    {
      name: "nimb-dagster",
      cwd: "/opt/nimb-ace/nep-trade-analytics",
      script: "uv",
      args: "run dagster dev -m nrc_pipelines --port 3001",
    },
  ],
};
```

```bash
pm2 start ecosystem.config.js
pm2 save && pm2 startup       # persist across reboots
pm2 logs nimb-api
```

> pm2 does **not** auto-load the repo `.env` for the Python apps — either run the app under
> `uv run --env-file .env …` or export the vars in the pm2 `env` block. systemd's
> `EnvironmentFile=` is simpler here.

---

## Reverse proxy (nginx) — expose only the web + API

Terminate TLS at nginx, serve the web app, and proxy `/api/*` (plus `/health`, `/ready`,
`/chat`, `/docs`) to the API. **Do not** expose `:3000`, `:8080`, `:3001`, `:8081`,
`:9000/9001`, `:5432`, `:6379` directly.

```nginx
server {
    listen 443 ssl http2;
    server_name ace.example.com;

    ssl_certificate     /etc/letsencrypt/live/ace.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ace.example.com/privkey.pem;

    client_max_body_size 50m;              # allow trade-book xlsx uploads

    # API — chat + data + internal uploads
    location /api/    { proxy_pass http://127.0.0.1:8080; }
    location /health  { proxy_pass http://127.0.0.1:8080; }
    location /ready   { proxy_pass http://127.0.0.1:8080; }
    location /chat    { proxy_pass http://127.0.0.1:8080; }
    location /docs    { proxy_pass http://127.0.0.1:8080; }   # optional: restrict/deny in prod

    # Everything else — the Next.js app
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade    $http_upgrade;   # Next.js HMR / streaming
        proxy_set_header Connection "upgrade";
        proxy_set_header Host       $host;
    }
}

# Redirect http → https
server { listen 80; server_name ace.example.com; return 301 https://$host$request_uri; }
```

Raise `client_max_body_size` to fit the largest trade-book file; uploads stream through
the API to MinIO ([06-file-uploads-and-surveillance](06-file-uploads-and-surveillance.md)).
Consider denying `/docs` (Swagger) publicly in production.

---

## Health checks

```bash
curl -fsS http://127.0.0.1:8080/health   # → {"status":"ok"}
curl -fsS http://127.0.0.1:8080/ready    # → {"status":"ok","checks":{"postgres":true}}
```

`/ready` fails if Postgres is unreachable — the readiness gate for the API. Point your load
balancer / uptime check at `/ready`.
