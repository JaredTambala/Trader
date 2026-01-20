"""Deterministic identifiers for runs and orders."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256


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


def deterministic_run_id(strategy_id: str, decision_ts: datetime) -> str:
    """Create a deterministic run identifier from strategy and decision timestamp.

    Args:
        strategy_id: Strategy identifier.
        decision_ts: Decision timestamp used to seed the run ID.

    Returns:
        Deterministic run identifier string.

    Raises:
        None.
    """
    normalized_ts = _normalize_timestamp(decision_ts)
    payload = f"{strategy_id}:{normalized_ts.isoformat()}"
    return f"run_{sha256(payload.encode('utf-8')).hexdigest()}"


def deterministic_client_order_id(
    run_id: str,
    symbol: str,
    side: str,
    target_qty: float | str | Decimal,
) -> str:
    """Create a deterministic order identifier from order intent fields.

    Args:
        run_id: Deterministic run identifier.
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
    payload = f"{run_id}:{normalized_symbol}:{normalized_side}:{normalized_qty}"
    return f"order_{sha256(payload.encode('utf-8')).hexdigest()}"
