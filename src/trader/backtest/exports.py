"""Serialization and file export helpers for backtest results."""

from __future__ import annotations

import csv
from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
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


def serialize_backtest_result(result: BacktestResult) -> dict[str, Any]:
    """Convert a backtest result into JSON-compatible primitive values.

    Dataclasses become dictionaries and datetimes become ISO-8601 strings so
    the payload can be persisted to metrics snapshots or returned by the API.
    """
    raw = asdict(result)
    return _sanitize_value(raw)


def export_backtest_result_json(result: BacktestResult, path: str | Path) -> Path:
    """Write the complete serialized backtest result to a JSON file.

    Returns:
        The normalized output path after writing.
    """
    output_path = Path(path)
    output_path.write_text(json.dumps(serialize_backtest_result(result), indent=2), encoding="utf-8")
    return output_path


def export_backtest_equity_curve_csv(result: BacktestResult, path: str | Path) -> Path:
    """Write aligned strategy and benchmark equity curves to CSV.

    The CSV uses stable column names and leaves benchmark equity blank when the
    benchmark curve is shorter than the strategy curve.
    """
    output_path = Path(path)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(_EQUITY_CURVE_CSV_FIELDS),
        )
        writer.writeheader()
        writer.writerows(_build_equity_curve_csv_rows(result))
    return output_path


def export_backtest_trades_csv(result: BacktestResult, path: str | Path) -> Path:
    """Write executed trade records to CSV using stable accounting columns.

    The export preserves raw price, adjusted fill price, fees, slippage, and
    realized PnL so downstream analysis can reproduce trade-level accounting.
    """
    output_path = Path(path)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(_TRADES_CSV_FIELDS),
        )
        writer.writeheader()
        writer.writerows(_build_trade_csv_rows(result.trades))
    return output_path


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


__all__ = [
    "export_backtest_equity_curve_csv",
    "export_backtest_result_json",
    "export_backtest_trades_csv",
    "serialize_backtest_result",
]
