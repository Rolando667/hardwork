"""Build ExchangeClients, skipping any that fail to load.

Graceful skip is a first-class behavior, not error handling: in a restricted
network some venues (e.g. Binance, Bybit) may be unreachable, and the scanner
must still run on whatever loaded as long as >= 2 venues are available.
"""

from __future__ import annotations

from ..core.config import Config
from ..core.logging_setup import get_logger
from .base import ExchangeClient, ExchangeLoadError

log = get_logger(__name__)


def build_exchanges_verbose(
    cfg: Config,
) -> tuple[dict[str, ExchangeClient], dict[str, str]]:
    """Like :func:`build_exchanges` but also return ``{name: skip_reason}``."""
    clients: dict[str, ExchangeClient] = {}
    skipped: dict[str, str] = {}
    for name in cfg.exchanges:
        client = ExchangeClient(
            name=name,
            market_cfg=cfg.market,
            fees_cfg=cfg.fees,
            request_timeout_ms=cfg.runtime.request_timeout_ms,
        )
        try:
            client.load()
            clients[name] = client
        except ExchangeLoadError as exc:
            # Keep the reason short (drop any large response body the exchange echoed).
            reason = str(exc).splitlines()[0][:160]
            skipped[name] = reason
            log.warning("exchange skipped: %s", reason)

    if len(clients) < 2:
        loaded = ", ".join(clients) or "none"
        log.error(
            "only %d exchange(s) loaded (%s); need >= 2 for cross-exchange arbitrage",
            len(clients),
            loaded,
        )
    return clients, skipped


def build_exchanges(cfg: Config) -> dict[str, ExchangeClient]:
    """Return name -> loaded ExchangeClient for every exchange that loads."""
    clients, _ = build_exchanges_verbose(cfg)
    return clients
