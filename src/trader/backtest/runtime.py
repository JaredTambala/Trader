"""Backtest runtime dependency and replay-planning helpers."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
import logging
from typing import Iterator, Mapping, Sequence

from ..broker import Broker, InternalPaperBroker
from ..config import Config
from ..strategies import Strategy
from .models import BacktestAssumptions


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
    return max(windows, default=0)


def _build_backtest_broker(assumptions: BacktestAssumptions) -> Broker:
    """Create a deterministic internal broker for backtest execution."""
    return InternalPaperBroker(
        reject_probability=0.0,
        fill_delay_ms_mean=max(0.0, assumptions.latency_ms),
        fill_delay_ms_stddev=0.0,
        fill_qty_fraction_mean=1.0,
        fill_qty_fraction_stddev=0.0,
        slippage_bps=max(0.0, assumptions.slippage.bps),
        fee_fixed_per_order=max(0.0, assumptions.fees.fixed_per_order),
        fee_bps=max(0.0, assumptions.fees.bps),
        fee_minimum=max(0.0, assumptions.fees.minimum_fee),
        sleep_on_fill_delay=False,
    )


@contextmanager
def _cycle_log_suppression(enabled: bool = True) -> Iterator[None]:
    """Temporarily suppress per-cycle logging noise."""
    if not enabled:
        yield
        return
    targets = [
        "trader.cycle",
        "trader.market_data",
        "trader.portfolio",
        "trader.signals",
        "trader.signal_generators",
        "trader.strategies",
    ]
    previous: list[tuple[logging.Logger, int]] = []
    for name in targets:
        target = logging.getLogger(name)
        previous.append((target, target.level))
        target.setLevel(logging.WARNING)
    try:
        yield
    finally:
        for target, level in previous:
            target.setLevel(level)
