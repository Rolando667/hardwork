"""Phase 2 — paper (simulated) trading over the read-only scanner feed.

Opens virtual delta-neutral positions on wide gross spreads, holds them, and
closes on convergence / stop / timeout, accounting every cost through the shared
fees/ engine so paper P&L matches what live would cost. No real orders.
"""
