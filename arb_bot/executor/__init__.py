"""Phase 3 — live execution safety core.

DRY_RUN by default. Nothing here places a real order unless live.live_trading is
true AND the interactive confirmation passes. Execution is deterministic — there
is NO LLM in the trading loop.
"""
