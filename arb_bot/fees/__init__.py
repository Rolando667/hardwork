"""Fees: THE single source of truth for cost/profit accounting.

Every phase (scanner, simulator, live) computes P&L through this module so a
paper simulation can never drift from what live would actually cost.
"""
