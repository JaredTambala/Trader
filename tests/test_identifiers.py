"""Tests for deterministic identifier helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trader.identifiers import (
    deterministic_client_order_id,
    deterministic_run_id,
)


def test_deterministic_run_id_stable():
    """Ensure run IDs are stable for identical inputs.

    Raises:
        AssertionError: If identifiers are not stable or differ unexpectedly.
    """
    decision_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    first = deterministic_run_id("demo", decision_ts)
    second = deterministic_run_id("demo", decision_ts)
    assert first == second

    different = deterministic_run_id("demo", decision_ts + timedelta(seconds=1))
    assert first != different


def test_deterministic_client_order_id_stable():
    """Ensure client order IDs normalize symbol, side, and qty inputs.

    Raises:
        AssertionError: If identifiers differ for equivalent inputs.
    """
    order_id = deterministic_client_order_id("run-1", "aapl", "BUY", 1.0)
    same = deterministic_client_order_id("run-1", "AAPL", "buy", "1.00000000")
    assert order_id == same
