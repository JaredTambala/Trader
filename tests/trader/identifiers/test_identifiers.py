"""Protect reproducible identifiers used across runs, cycles, and broker orders.

Subject: Deterministic identifier derivation from normalized domain inputs and timestamps.
Level: Pure unit contracts.
Collaborators: Identifier helpers and fixed in-memory values only.
Guarantees: Equivalent inputs repeat identifiers while material identity changes alter them.
Non-goals: Database uniqueness, distributed allocation, cryptographic secrecy, or collision analysis.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trader.identifiers import (
    deterministic_client_order_id,
    deterministic_cycle_id,
    deterministic_run_session_id,
)


def test_deterministic_cycle_id_stable():
    """Repeat a cycle identifier and change it when the decision timestamp changes."""
    decision_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    first = deterministic_cycle_id("demo", decision_ts)
    second = deterministic_cycle_id("demo", decision_ts)
    assert first == second

    different = deterministic_cycle_id("demo", decision_ts + timedelta(seconds=1))
    assert first != different


def test_deterministic_run_session_id_stable():
    """Repeat a run-session identifier and vary it with the run start time."""
    started_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    first = deterministic_run_session_id("backtest", started_at)
    second = deterministic_run_session_id("backtest", started_at)
    assert first == second

    different = deterministic_run_session_id(
        "backtest", started_at + timedelta(seconds=1)
    )
    assert first != different


def test_deterministic_client_order_id_stable():
    """Treat equivalent symbol, side, and quantity representations as one order identity."""
    order_id = deterministic_client_order_id("cycle-1", "aapl", "BUY", 1.0)
    same = deterministic_client_order_id("cycle-1", "AAPL", "buy", "1.00000000")
    assert order_id == same
