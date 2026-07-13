"""HTTP publisher — POSTs a full tick batch in one request per round."""
from __future__ import annotations

import logging

import httpx

_log = logging.getLogger("nrc_simulator.publisher")
_TIMEOUT = httpx.Timeout(5.0)
_DEFAULT_URL = "http://localhost:8080/ingest/ticks"


def publish_batch(ticks: list[dict], *, ingest_url: str = _DEFAULT_URL) -> None:
    """POST all ticks for one round as a single JSON array — one HTTP call."""
    if not ticks:
        return
    for attempt in range(3):
        try:
            resp = httpx.post(ingest_url, json=ticks, timeout=_TIMEOUT)
            resp.raise_for_status()
            return
        except httpx.HTTPStatusError as exc:
            _log.error("ingest rejected  status=%d  body=%s",
                       exc.response.status_code, exc.response.text[:200])
            return  # non-retriable — bad request
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            if attempt == 2:
                _log.warning("ingest unreachable after 3 attempts: %s", exc)
