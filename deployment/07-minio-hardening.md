# 07 — MinIO hardening

The MinIO defaults (`minioadmin` / `minioadmin`, plaintext, console open) are for local dev
only. In production MinIO holds the Delta lakehouse **and** the private internal-uploads
bucket, so it must be locked down. This doc covers: replacing root creds, giving the app a
scoped service account, enabling TLS, and keeping the console off the public internet.

Prereqs: the `mc` MinIO client on the server, and an admin alias to your instance. All
commands assume you tunnel/localhost to `:9000` (never expose it — see
[05-firewall-ports](05-firewall-ports.md)).

```bash
# Point mc at the running server using the CURRENT root creds
mc alias set nimb http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
mc admin info nimb
```

---

## 1. Replace the root credentials

Never run production on `minioadmin/minioadmin`. Generate strong values and set them in
`.env` **before** first boot (they seed the server), then restart MinIO.

```bash
# generate strong secrets (example)
openssl rand -hex 12        # → MINIO_ROOT_USER
openssl rand -base64 32     # → MINIO_ROOT_PASSWORD
```

In `.env` ([02-environment](02-environment.md)):

```
MINIO_ROOT_USER=<strong-user>
MINIO_ROOT_PASSWORD=<strong-password>
```

```bash
make down && make up        # MinIO re-seeds root creds from the environment
```

> If MinIO already has data, changing root creds via env re-seeds only on a fresh server.
> For a running instance, prefer creating a new admin user and demoting the old one with
> `mc admin user` + policies, then rotating. Root creds should be **break-glass only** —
> day-to-day the app uses a scoped service account (below).

---

## 2. Scoped service account for the app

The app only ever touches the **uploads bucket** (via the in-app upload page) and reads the
**lakehouse** bucket (pipeline). Don't give it root. Create a least-privilege policy and a
service account (access key pair) limited to what it needs.

### Policy limited to the uploads bucket

`nrc-uploads-policy.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::nrc-internal-uploads",
        "arn:aws:s3:::nrc-internal-uploads/*"
      ]
    }
  ]
}
```

> If the **same** credentials also run the Dagster pipeline (Bronze/Silver/Gold on
> `nepse-lakehouse`) and read `raw-snapshots`, extend `Resource` to include those buckets.
> Split into two accounts (an uploads/app account and a pipeline account) if you want the
> user-facing API to be unable to touch the lakehouse at all — a stronger posture.

### Create the policy + a service account

```bash
# 1) register the policy
mc admin policy create nimb nrc-uploads-policy ./nrc-uploads-policy.json

# 2) create a dedicated user and attach the policy
mc admin user add nimb nrc-app "$(openssl rand -base64 24)"
mc admin policy attach nimb nrc-uploads-policy --user nrc-app

# 3) (recommended) mint a service account (access key/secret) for that user
mc admin user svcacct add nimb nrc-app
# → prints  Access Key / Secret Key  — put these in the app's MinIO client config
```

Point the app at the service-account keys instead of root. Where the storage client reads
credentials depends on `nrc_storage` config (`libs/storage/nrc_storage/config.py`,
`minio_client.py`); wire the access-key/secret there (env or config), keeping
`MINIO_ROOT_*` as break-glass only.

Verify the scope holds:

```bash
mc alias set nimbapp http://127.0.0.1:9000 <ACCESS_KEY> <SECRET_KEY>
mc ls nimbapp/nrc-internal-uploads          # works
mc ls nimbapp/nepse-lakehouse               # should be denied (unless you granted it)
```

---

## 3. Enable TLS

Even internal, encrypt MinIO traffic (Delta writes, upload streams). MinIO reads certs from
`/data/.minio/certs/` (i.e. `./data/minio/.minio/certs/` on the host bind mount):

```bash
mkdir -p ./data/minio/.minio/certs
cp fullchain.pem ./data/minio/.minio/certs/public.crt
cp privkey.pem   ./data/minio/.minio/certs/private.key
make restart
```

Then set `MINIO_ENDPOINT=https://<internal-host>:9000` in `.env` so the app/pipeline and
`scripts/verify_infra.py` use TLS. For a private CA, ensure the app's boto3/urllib trust
store includes it. If MinIO fronts via nginx instead, terminate TLS there and keep MinIO on
loopback.

---

## 4. Keep the console on localhost / VPN

- The console (`:9001`) and S3 API (`:9000`) must **never** be public
  ([05-firewall-ports](05-firewall-ports.md)). Bind them to `127.0.0.1` in a compose
  override and/or block them at the host firewall.
- Admin access is via SSH tunnel: `ssh -L 9001:127.0.0.1:9001 nimb@server`, then browse
  `http://localhost:9001`.
- End users **never** get a console login. They use the in-app upload page only
  ([06-file-uploads-and-surveillance](06-file-uploads-and-surveillance.md)).

---

## Hardening checklist

- [ ] Root creds rotated off `minioadmin`; strong `MINIO_ROOT_*` in `.env` (mode 600).
- [ ] App runs on a **scoped service account**, not root.
- [ ] Uploads bucket policy limited to `nrc-internal-uploads` (+ lakehouse only if needed).
- [ ] All three buckets private (`mc anonymous get nimb/<bucket>` → `none`).
- [ ] TLS enabled (MinIO certs or nginx front) and `MINIO_ENDPOINT` uses it.
- [ ] `:9000`/`:9001` bound to loopback/VPN and firewalled.
