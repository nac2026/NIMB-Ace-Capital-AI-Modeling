"""Verify local infrastructure is reachable from the host.

Run after `make up`. Prints one line per service with ✓ / ✗ status.
Exits non-zero if any service fails so it can gate bootstrap scripts."""
from __future__ import annotations
import os, socket, sys, urllib.request
from urllib.error import URLError


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def check_port(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def check_minio() -> tuple[bool, str]:
    endpoint = _env("MINIO_ENDPOINT", "http://localhost:9000")
    url = f"{endpoint.rstrip('/')}/minio/health/live"
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            if r.status == 200:
                return True, f"live at {endpoint}"
            return False, f"HTTP {r.status} from {url}"
    except URLError as e:
        return False, f"unreachable: {e.reason}"
    except Exception as e:
        return False, str(e)


def check_postgres() -> tuple[bool, str]:
    host = _env("POSTGRES_HOST", "localhost")
    port = int(_env("POSTGRES_PORT", "5432"))
    if not check_port(host, port):
        return False, f"port {host}:{port} closed"
    try:
        import psycopg  # type: ignore
    except ImportError:
        return True, f"{host}:{port} reachable (psycopg not installed — skipping query check)"
    try:
        user = _env("POSTGRES_USER", "nepse")
        pw = _env("POSTGRES_PASSWORD", "nepse")
        db = _env("POSTGRES_DB", "nepse")
        with psycopg.connect(f"postgresql://{user}:{pw}@{host}:{port}/{db}",
                             connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version()")
                v = cur.fetchone()[0].split(",")[0]
                cur.execute(
                    "SELECT extname FROM pg_extension WHERE extname IN ('vector','pg_trgm') ORDER BY extname")
                exts = [r[0] for r in cur.fetchall()]
        return True, f"{v}, extensions: {exts}"
    except Exception as e:
        return False, f"connect/query failed: {e}"


def check_redis() -> tuple[bool, str]:
    host, port = "localhost", 6379
    if not check_port(host, port):
        return False, f"port {host}:{port} closed"
    # Use raw RESP ping (no lib dep needed at this stage)
    try:
        with socket.create_connection((host, port), timeout=3) as s:
            s.sendall(b"PING\r\n")
            resp = s.recv(64).decode("utf-8", errors="replace").strip()
        if resp == "+PONG":
            return True, f"{host}:{port} PONG"
        return False, f"unexpected response: {resp!r}"
    except Exception as e:
        return False, str(e)


def main() -> int:
    checks = [
        ("MinIO   ", check_minio),
        ("Postgres", check_postgres),
        ("Redis   ", check_redis),
    ]
    ok_all = True
    print("Infra check")
    for label, fn in checks:
        ok, detail = fn()
        mark = "\033[32m✓\033[0m" if ok else "\033[31m✗\033[0m"
        print(f"  {mark} {label}  {detail}")
        ok_all = ok_all and ok
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
