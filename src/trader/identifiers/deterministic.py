"""Deterministic identifiers for runs, cycles, orders, signals, and fills."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from typing import Sequence


_DECIMAL_QUANTIZE = Decimal("0.00000001")


def _normalize_timestamp(timestamp: datetime) -> datetime:
    """Normalize timestamps to UTC with timezone awareness.

    Args:
        timestamp: Input datetime.

    Returns:
        UTC-aware datetime.

    Raises:
        None.
    """
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def _normalize_qty(qty: float | str | Decimal) -> str:
    """Normalize quantities to a fixed decimal string.

    Args:
        qty: Quantity value.

    Returns:
        Normalized decimal string.

    Raises:
        decimal.InvalidOperation: If qty cannot be parsed.
    """
    decimal_qty = Decimal(str(qty)).quantize(_DECIMAL_QUANTIZE)
    return format(decimal_qty, "f")


def deterministic_cycle_id(strategy_id: str, decision_ts: datetime) -> str:
    """Create a deterministic cycle identifier from strategy and decision timestamp.

    Args:
        strategy_id: Strategy identifier.
        decision_ts: Decision timestamp used to seed the run ID.

    Returns:
        Deterministic cycle identifier string.

    Raises:
        None.
    """
    normalized_ts = _normalize_timestamp(decision_ts)
    payload = f"{strategy_id}:{normalized_ts.isoformat()}"
    return f"cycle_{sha256(payload.encode('utf-8')).hexdigest()}"


def deterministic_run_id(strategy_id: str, decision_ts: datetime) -> str:
    """Return the legacy run ID value, now equivalent to the cycle ID.

    Older callers used this helper for per-decision identifiers. Keeping the
    alias avoids changing public imports while newer code distinguishes
    run-session IDs from deterministic cycle IDs.
    """
    return deterministic_cycle_id(strategy_id, decision_ts)


def deterministic_backtest_cycle_id(
    run_id: str,
    strategy_id: str,
    decision_ts: datetime,
    symbols: Sequence[str],
) -> str:
    """Identify one replay decision within its run and decision universe.

    Args:
        run_id: Owning backtest session, separating independent replays.
        strategy_id: Strategy identifier.
        decision_ts: Decision timestamp, normalized to UTC.
        symbols: Symbols handled by this cycle; order and casing are ignored.

    Returns:
        Stable cycle ID for retries of the same decision in the same run.
        Different runs or symbol subsets produce different IDs.
    """
    payload = json.dumps(
        ["backtest", run_id, strategy_id, _normalize_timestamp(decision_ts).isoformat(),
         sorted({symbol.strip().upper() for symbol in symbols})],
        separators=(",", ":"),
    )
    return f"cycle_{sha256(payload.encode('utf-8')).hexdigest()}"


def deterministic_run_session_id(run_type: str, started_at: datetime) -> str:
    """Create a deterministic run session identifier from run type and wall clock.

    Args:
        run_type: Run type label (backtest/trading).
        started_at: Wall-clock start timestamp.

    Returns:
        Deterministic run session identifier string.

    Raises:
        None.
    """
    normalized_ts = _normalize_timestamp(started_at)
    payload = f"{run_type}:{normalized_ts.isoformat()}"
    return f"run_{sha256(payload.encode('utf-8')).hexdigest()}"


def deterministic_client_order_id(
    cycle_id: str,
    symbol: str,
    side: str,
    target_qty: float | str | Decimal,
) -> str:
    """Create a deterministic order identifier from order intent fields.

    Args:
        cycle_id: Deterministic cycle identifier.
        symbol: Trading symbol.
        side: Order side.
        target_qty: Target quantity.

    Returns:
        Deterministic client order identifier string.

    Raises:
        decimal.InvalidOperation: If target_qty cannot be parsed.
    """
    normalized_symbol = symbol.upper()
    normalized_side = side.lower()
    normalized_qty = _normalize_qty(target_qty)
    payload = f"{cycle_id}:{normalized_symbol}:{normalized_side}:{normalized_qty}"
    return f"order_{sha256(payload.encode('utf-8')).hexdigest()}"


def deterministic_signal_event_id(
    run_id: str,
    cycle_id: str,
    symbol: str,
    signal_name: str | None = None,
    *,
    identity_suffix: str | None = None,
) -> str:
    """Create a stable producer identity for one strategy signal.

    The optional suffix lets strategies that emit multiple inputs for the same
    symbol and cycle supply a stable source identity without using wall-clock
    timestamps.
    """
    payload = ":".join(
        (
            str(run_id),
            str(cycle_id),
            str(symbol).strip().upper(),
            str(signal_name or "").strip(),
            str(identity_suffix or "").strip(),
        )
    )
    return f"signal_{sha256(payload.encode('utf-8')).hexdigest()}"


def deterministic_fill_event_id(
    client_order_id: str,
    fill_ts: datetime,
    fill_qty: float | str | Decimal,
    fill_price: float | str | Decimal,
    *,
    sequence: int = 0,
    broker_fill_id: str | None = None,
) -> str:
    """Create a stable identity for one execution evidence record.

    ``sequence`` disambiguates repeated identical fills for one client order;
    broker-provided fill IDs take precedence when available through the
    identity payload.
    """
    normalized_ts = _normalize_timestamp(fill_ts)
    payload = ":".join(
        (
            str(client_order_id),
            normalized_ts.isoformat(),
            _normalize_qty(fill_qty),
            _normalize_qty(fill_price),
            str(sequence),
            str(broker_fill_id or "").strip(),
        )
    )
    return f"fill_{sha256(payload.encode('utf-8')).hexdigest()}"
