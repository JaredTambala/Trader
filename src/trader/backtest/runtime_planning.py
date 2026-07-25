"""Pure planning helpers for deterministic backtest runtime execution."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Mapping, Sequence

from ..config import Config
from ..strategies import Strategy

__all__ = [
    "_build_backtest_runtime_config",
    "_build_symbol_runtime_configs",
    "_count_scheduled_symbol_runs",
    "_normalize_backtest_symbols",
    "_resolve_effective_replay_limit",
    "_resolve_backtest_asset_class",
    "_signal_lookback_window",
]


def _normalize_backtest_symbols(
    symbols: Sequence[str] | None,
    *,
    config_symbols: Sequence[str],
) -> tuple[str, ...]:
    """Return uppercase non-empty backtest symbols from explicit or config values."""
    raw_symbols = symbols if symbols is not None else config_symbols
    return tuple(str(symbol).strip().upper() for symbol in raw_symbols if str(symbol).strip())


def _resolve_backtest_asset_class(
    asset_class: str | None,
    *,
    config_asset_class: str,
) -> str:
    """Return the normalized asset class for a backtest run."""
    return (asset_class or config_asset_class).lower()


def _build_backtest_runtime_config(
    config: Config,
    *,
    symbols: Sequence[str],
    asset_class: str,
    timeframe: str,
) -> Config:
    """Return the production config transformed for deterministic backtest execution."""
    return replace(
        config,
        mode="backtest",
        market_data_source="noop",
        market_data_symbols=tuple(symbols),
        market_data_asset_class=asset_class,
        strategy_timeframe=timeframe,
        broker_type="internal",
    )


def _build_symbol_runtime_configs(config: Config, symbols: Sequence[str]) -> dict[str, Config]:
    """Return one runtime config per symbol for single-symbol cycle execution."""
    return {symbol: replace(config, market_data_symbols=(symbol,)) for symbol in symbols}


def _count_scheduled_symbol_runs(
    symbol_schedule: Mapping[datetime, Sequence[str]],
    timestamps: Sequence[datetime],
) -> int:
    """Count symbol-level cycle executions in a timestamp schedule."""
    return sum(len(symbol_schedule[ts]) for ts in timestamps)


def _resolve_effective_replay_limit(*, total_bars: int, max_runs: int | None) -> int:
    """Resolve the progress denominator after applying an optional max-runs cap."""
    if max_runs is None:
        return total_bars
    return min(total_bars, max_runs)


def _signal_lookback_window(strategy: Strategy) -> int:
    """Infer bar lookback needs from the injected strategy object."""
    signal_generator = getattr(strategy, "signal_generator", None)
    signals = getattr(signal_generator, "signals", ())
    windows: list[int] = []
    for signal in signals or ():
        window = getattr(signal, "window", None)
        if isinstance(window, int) and window > 0:
            windows.append(window)
    required_lookback = strategy.required_lookback
    if isinstance(required_lookback, bool) or not isinstance(required_lookback, int):
        raise ValueError("strategy required_lookback must be an integer")
    if required_lookback < 0:
        raise ValueError("strategy required_lookback must be non-negative")
    return max([required_lookback, *windows], default=0)
