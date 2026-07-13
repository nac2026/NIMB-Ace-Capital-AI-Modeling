"""Client-internal trade-book adapters.

The firm's own daily trade-book Excel dumps (one fill per row). Distinct from
the public market data in `client_csv` / `smtm`: these are NIMB Ace Capital's
own executions, joined to the public floor sheet (by contract_number) downstream
to power internal-trade surveillance. Tagged CLIENT_AUTHORITATIVE."""
from __future__ import annotations

from .internal_trades import ingest_client_internal_trades

__all__ = [
    "ingest_client_internal_trades",
]
