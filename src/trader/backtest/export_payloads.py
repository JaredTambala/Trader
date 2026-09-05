"""Pure serialization and CSV row builders for backtest results."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any, Sequence

from .models import BacktestResult, TradeRecord

_EQUITY_CURVE_CSV_FIELDS = ("ts", "strategy_equity", "benchmark_equity")
_TRADES_CSV_FIELDS = (
    "client_order_id",
    "cycle_id",
    "symbol",
    "side",
    "fill_ts",
    "fill_qty",
    "raw_fill_price",
    "fill_price",
    "fee_amount",
    "slippage_amount",
    "notional",
    "realized_pnl",
)

__all__ = [
    "_EQUITY_CURVE_CSV_FIELDS",
    "_TRADES_CSV_FIELDS",
    "_build_equity_curve_csv_rows",
    "_build_trade_csv_rows",
    "_sanitize_value",
    "serialize_backtest_result",
]


def serialize_backtest_result(result: BacktestResult) -> dict[str, Any]:
    """Convert a backtest result into JSON-compatible primitive values.

    Dataclasses become dictionaries and datetimes become ISO-8601 strings so
    the payload can be persisted to metrics snapshots or returned by the API.
    """
    raw = asdict(result)
    return _sanitize_value(raw)


def _build_equity_curve_csv_rows(result: BacktestResult) -> tuple[dict[str, object], ...]:
    """Build stable CSV rows for aligned strategy and benchmark equity curves."""
    rows: list[dict[str, object]] = []
    for index, point in enumerate(result.equity_curve):
        benchmark_point = result.benchmark_curve[index] if index < len(result.benchmark_curve) else None
        rows.append(
            {
                "ts": point.ts.isoformat(),
                "strategy_equity": point.equity,
                "benchmark_equity": benchmark_point.equity if benchmark_point is not None else None,
            }
        )
    return tuple(rows)


def _build_trade_csv_rows(trades: Sequence[TradeRecord]) -> tuple[dict[str, object], ...]:
    """Build stable CSV rows for executed trade accounting records."""
    return tuple(
        {
            "client_order_id": trade.client_order_id,
            "cycle_id": trade.cycle_id,
            "symbol": trade.symbol,
            "side": trade.side,
            "fill_ts": trade.fill_ts.isoformat(),
            "fill_qty": trade.fill_qty,
            "raw_fill_price": trade.raw_fill_price,
            "fill_price": trade.fill_price,
            "fee_amount": trade.fee_amount,
            "slippage_amount": trade.slippage_amount,
            "notional": trade.notional,
            "realized_pnl": trade.realized_pnl,
        }
        for trade in trades
    )


def _sanitize_value(value: Any) -> Any:
    """Recursively normalize values for JSON serialization."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _sanitize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(v) for v in value]
    if isinstance(value, tuple):
        return [_sanitize_value(v) for v in value]
    return value
