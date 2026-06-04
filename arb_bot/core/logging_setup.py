"""Single place to configure structured console logging.

P0 logs to the console only. Machine-readable JSONL/CSV trade journals are P1.
"""

from __future__ import annotations

import logging
import sys
import time

_CONFIGURED = False


def setup_logging(level: str = "INFO") -> None:
    """Initialize root logging once. Safe to call repeatedly."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    numeric = getattr(logging, level.upper(), logging.INFO)
    handler = logging.StreamHandler(stream=sys.stderr)
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    formatter.converter = time.gmtime  # force UTC timestamps
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(numeric)

    # ccxt is chatty at DEBUG; keep it at WARNING unless we are debugging.
    logging.getLogger("ccxt").setLevel(max(numeric, logging.WARNING))

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
