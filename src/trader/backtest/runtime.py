"""Backtest runtime dependency and logging adapters."""

from __future__ import annotations

from contextlib import contextmanager
import logging
from typing import Iterator

from ..broker import Broker, InternalPaperBroker
from .models import BacktestAssumptions
from .runtime_planning import (
    _build_backtest_runtime_config,
    _build_symbol_runtime_configs,
    _count_scheduled_symbol_runs,
    _resolve_effective_replay_limit,
    _signal_lookback_window,
)

__all__ = [
    "_build_backtest_broker",
    "_build_backtest_runtime_config",
    "_build_symbol_runtime_configs",
    "_count_scheduled_symbol_runs",
    "_cycle_log_suppression",
    "_resolve_effective_replay_limit",
    "_signal_lookback_window",
]


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
