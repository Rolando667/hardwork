"""Entry point for the arbitrage bot.

Phase 1 (P0): read-only cross-exchange perp spread scanner. No keys, no orders.

    python main.py                 # Phase 1 console scanner, ./config.yaml
    python main.py path/to.yaml    # console scanner, specific config
    python main.py web             # Phase 1 read-only web dashboard (same data)
    python main.py sim             # Phase 2 paper simulator (virtual trades only)
    python main.py live            # Phase 3 executor (DRY_RUN unless config+confirm)

Richer CLI flags and per-strategy selection arrive later. Phases 1 (scan/web),
2 (sim) and 3 (live, DRY_RUN by default) are implemented.
"""

from __future__ import annotations

import sys
import time

from arb_bot.core.config import load_config
from arb_bot.core.logging_setup import get_logger, setup_logging
from arb_bot.exchanges.factory import build_exchanges
from arb_bot.scanner.report import format_scan
from arb_bot.scanner.scanner import scan


def main(argv: list[str]) -> int:
    args = argv[1:]
    mode = "console"
    if args and args[0] in ("web", "sim", "live"):
        mode, args = args[0], args[1:]
    config_path = args[0] if args else "config.yaml"

    cfg = load_config(config_path)
    setup_logging(cfg.runtime.log_level)
    log = get_logger("main")

    if cfg.phase != "p0":
        log.error("only phase 'p0' is implemented; config requested '%s'", cfg.phase)
        return 2

    if mode == "web":
        from arb_bot.web.server import run_dashboard

        log.info("Phase 1 (P0) web dashboard — read-only, no keys. exchanges=%s", cfg.exchanges)
        return run_dashboard(cfg, host=cfg.web.host, port=cfg.web.port)

    if mode == "sim":
        from arb_bot.simulator.paper import run_paper

        return run_paper(cfg)

    if mode == "live":
        from arb_bot.executor.live import run_live

        return run_live(cfg)

    log.info("Phase 1 (P0) scanner — read-only, no keys. exchanges=%s", cfg.exchanges)
    clients = build_exchanges(cfg)
    if len(clients) < 2:
        log.error("need at least 2 loaded exchanges to scan; exiting")
        return 1

    try:
        while True:
            try:
                result = scan(clients, cfg)
                print(format_scan(result, cfg.thresholds.entry_net_spread_bps))
            except Exception as exc:  # noqa: BLE001 - keep the loop alive on transient errors
                log.exception("scan failed: %s", exc)

            if not cfg.runtime.loop:
                break
            time.sleep(cfg.runtime.loop_interval_seconds)
    except KeyboardInterrupt:
        log.info("interrupted; exiting")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
