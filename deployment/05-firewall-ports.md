# 05 — Firewall & port exposure

**Only the reverse proxy on `443` is public.** Every backing service and internal tool is
firewalled to the host / VPN. This is a hard requirement: MinIO holds the internal-uploads
bucket, Postgres holds serving state, and Dagster can trigger pipeline runs — none of them
authenticate end users.

---

## Port-exposure matrix

| Port | Service | Bind | Exposure | Rationale |
|------|---------|------|----------|-----------|
| `443` | Reverse proxy (nginx/TLS) | `0.0.0.0` | **PUBLIC** | The only user-facing surface |
| `80` | nginx (redirect → 443) | `0.0.0.0` | public (redirect only) | ACME + http→https |
| `3000` | Next.js web app | `127.0.0.1` | internal (proxied by nginx) | Users reach it only via 443 |
| `8080` | FastAPI API | `127.0.0.1` | internal (proxied by nginx) | Users reach it only via 443 |
| `3001` | Dagster UI | `127.0.0.1` / VPN | **INTERNAL-ONLY** | Can launch pipeline jobs — no end-user auth |
| `8081` | dbt docs | `127.0.0.1` / VPN | **INTERNAL-ONLY** | Internal documentation |
| `9000` | MinIO S3 API | `127.0.0.1` / VPN | **INTERNAL-ONLY** | Object store; app talks to it server-side |
| `9001` | MinIO web console | `127.0.0.1` / VPN | **INTERNAL-ONLY** | Admin console — never public |
| `5432` | Postgres | `127.0.0.1` / VPN | **INTERNAL-ONLY** | Serving DB |
| `6379` | Redis | `127.0.0.1` / VPN | **INTERNAL-ONLY** | Session cache |

**Explicit statement:** MinIO `:9000`/`:9001`, Postgres `:5432`, Redis `:6379`, Dagster
`:3001`, and dbt-docs `:8081` are **internal-only** and must be unreachable from the public
internet. End users interact only with the web app (and its API) through the `:443` reverse
proxy. In particular, users **never** touch MinIO — they upload files through the in-app
page ([06-file-uploads-and-surveillance](06-file-uploads-and-surveillance.md)).

---

## Defense in depth

1. **Bind to loopback.** Keep app processes on `127.0.0.1` (`NRC_HOST=127.0.0.1`, web on
   loopback). See [04-services](04-services.md).
2. **Docker port publishing.** `docker-compose.yml` publishes `9000/9001/5432/6379` to the
   host. On a single-host deploy that is fine **only if the host firewall blocks them**
   externally. To be safe, bind them to loopback by overriding the port mappings, e.g. in a
   `docker-compose.override.yml`:

   ```yaml
   services:
     minio:    { ports: ["127.0.0.1:9000:9000", "127.0.0.1:9001:9001"] }
     postgres: { ports: ["127.0.0.1:5432:5432"] }
     redis:    { ports: ["127.0.0.1:6379:6379"] }
   ```

3. **Host firewall.** Enforce with ufw/iptables below regardless.

---

## ufw (Ubuntu) example

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing        # outbound to Vertex/SMTM/news/etc. (see 01)
sudo ufw allow 22/tcp                  # SSH (restrict to your admin CIDR if possible)
sudo ufw allow 443/tcp                 # public HTTPS
sudo ufw allow 80/tcp                  # http→https redirect / ACME
# Everything else stays denied — 3000/8080/3001/8081/9000/9001/5432/6379 are NOT opened.
sudo ufw enable
sudo ufw status verbose
```

To reach the internal tools (Dagster, MinIO console, dbt-docs) as an admin, use an **SSH
tunnel** rather than opening ports:

```bash
ssh -L 3001:127.0.0.1:3001 -L 9001:127.0.0.1:9001 -L 8081:127.0.0.1:8081 nimb@server
# then browse http://localhost:3001 etc. locally
```

---

## iptables example

```bash
# Loopback + established
iptables -A INPUT -i lo -j ACCEPT
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
# Public
iptables -A INPUT -p tcp --dport 22  -s <ADMIN_CIDR> -j ACCEPT
iptables -A INPUT -p tcp --dport 80  -j ACCEPT
iptables -A INPUT -p tcp --dport 443 -j ACCEPT
# Default deny (blocks 3000/8080/3001/8081/9000/9001/5432/6379 from the outside)
iptables -P INPUT DROP
```

If Docker's userland-proxy publishes container ports past the `INPUT` chain, also add rules
on the `DOCKER-USER` chain (or use the loopback port-bind override above, which is
simpler and more robust).
