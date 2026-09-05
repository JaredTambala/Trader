"""Serialization and file export helpers for backtest results."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .export_payloads import (
    _EQUITY_CURVE_CSV_FIELDS,
    _TRADES_CSV_FIELDS,
    _build_equity_curve_csv_rows,
    _build_trade_csv_rows,
    _sanitize_value,
    serialize_backtest_result,
)
from .models import BacktestResult


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


__all__ = [
    "_build_equity_curve_csv_rows",
    "_build_trade_csv_rows",
    "_sanitize_value",
    "export_backtest_equity_curve_csv",
    "export_backtest_result_json",
    "export_backtest_trades_csv",
    "serialize_backtest_result",
]
