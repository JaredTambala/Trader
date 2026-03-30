"""Reusable long/flat strategy engine and built-in compositions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import AsyncIterator, Mapping, Sequence

from trader.data import EventStore
from trader.portfolio import Portfolio, Position
from trader.signals import Signal
from trader.strategies import Strategy

from trader_standard.bar_signals import (
    compute_signal_map,
    fetch_recent_bars,
    max_window_for_signals,
    table_for_asset_class,
)
from trader_standard.indicators import BollingerBandsIndicator, EmaIndicator, MacdIndicator, RsiIndicator, SmaIndicator
from trader_standard.signals import (
    BollingerBandSignal,
    EmaCrossoverSignal,
    MacdCrossoverSignal,
    RsiThresholdSignal,
    SmaStretchSignal,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StrategySnapshot:
    """Per-symbol state used by entry, exit, and stop policies."""

    symbol: str
    decision_ts: datetime
    last_price: float
    position_qty: float
    avg_price: float | None
    signals: Mapping[str, float]

    @property
    def is_long(self) -> bool:
        return self.position_qty > 0.0

    @property
    def is_flat(self) -> bool:
        return not self.is_long


class EntryPolicy(ABC):
    """Decide whether a long entry should be opened."""

    @abstractmethod
    def should_enter(self, snapshot: StrategySnapshot) -> bool:
        """Return True when the strategy should enter a long."""


class ExitPolicy(ABC):
    """Decide whether a long position should be flattened."""

    @abstractmethod
    def should_exit(self, snapshot: StrategySnapshot) -> bool:
        """Return True when the strategy should flatten a long."""


class StopPolicy(ABC):
    """Protective exit policy with optional internal symbol state."""

    def observe(self, snapshot: StrategySnapshot) -> None:
        """Update any internal state from the latest portfolio snapshot."""

    @abstractmethod
    def should_exit(self, snapshot: StrategySnapshot) -> bool:
        """Return True when the stop is hit."""

    def reset(self, symbol: str) -> None:
        """Clear any internal state for the symbol."""


@dataclass(frozen=True)
class SignalThresholdEntryPolicy(EntryPolicy):
    """Enter when configured signals cross the required threshold."""

    signal_names: tuple[str, ...]
    require_all: bool = True
    direction: str = "positive"
    threshold: float = 0.0

    def should_enter(self, snapshot: StrategySnapshot) -> bool:
        return _evaluate_signal_set(
            snapshot.signals,
            signal_names=self.signal_names,
            require_all=self.require_all,
            direction=self.direction,
            threshold=self.threshold,
        )


@dataclass(frozen=True)
class SignalThresholdExitPolicy(ExitPolicy):
    """Exit when configured signals cross the required threshold."""

    signal_names: tuple[str, ...]
    require_all: bool = False
    direction: str = "negative"
    threshold: float = 0.0

    def should_exit(self, snapshot: StrategySnapshot) -> bool:
        return _evaluate_signal_set(
            snapshot.signals,
            signal_names=self.signal_names,
            require_all=self.require_all,
            direction=self.direction,
            threshold=self.threshold,
        )


class NoOpStopPolicy(StopPolicy):
    """Stop policy that never exits."""

    def should_exit(self, snapshot: StrategySnapshot) -> bool:
        return False


@dataclass
class FixedStopLossPolicy(StopPolicy):
    """Exit when price falls below the configured loss threshold."""

    stop_loss_pct: float

    def __post_init__(self) -> None:
        self.stop_loss_pct = max(0.0, float(self.stop_loss_pct))

    def should_exit(self, snapshot: StrategySnapshot) -> bool:
        if not snapshot.is_long:
            return False
        reference_price = snapshot.avg_price if snapshot.avg_price is not None else snapshot.last_price
        return snapshot.last_price <= reference_price * (1.0 - self.stop_loss_pct)


@dataclass
class TrailingStopPolicy(StopPolicy):
    """Exit when price falls below a symbol high-water mark."""

    trailing_stop_pct: float

    def __post_init__(self) -> None:
        self.trailing_stop_pct = max(0.0, float(self.trailing_stop_pct))
        self._high_water_by_symbol: dict[str, float] = {}

    def observe(self, snapshot: StrategySnapshot) -> None:
        if not snapshot.is_long:
            self.reset(snapshot.symbol)
            return
        baseline = snapshot.avg_price if snapshot.avg_price is not None else snapshot.last_price
        current_high_water = self._high_water_by_symbol.get(snapshot.symbol, float(baseline))
        self._high_water_by_symbol[snapshot.symbol] = max(current_high_water, float(snapshot.last_price), float(baseline))

    def should_exit(self, snapshot: StrategySnapshot) -> bool:
        if not snapshot.is_long:
            return False
        high_water = self._high_water_by_symbol.get(
            snapshot.symbol,
            snapshot.avg_price if snapshot.avg_price is not None else snapshot.last_price,
        )
        return snapshot.last_price <= float(high_water) * (1.0 - self.trailing_stop_pct)

    def reset(self, symbol: str) -> None:
        self._high_water_by_symbol.pop(symbol, None)


@dataclass
class CompositeStopPolicy(StopPolicy):
    """Exit when any child stop policy fires."""

    policies: Sequence[StopPolicy]

    def observe(self, snapshot: StrategySnapshot) -> None:
        for policy in self.policies:
            policy.observe(snapshot)

    def should_exit(self, snapshot: StrategySnapshot) -> bool:
        return any(policy.should_exit(snapshot) for policy in self.policies)

    def reset(self, symbol: str) -> None:
        for policy in self.policies:
            policy.reset(symbol)


class LongFlatSignalStrategy(Strategy):
    """Generic long/flat strategy driven by bar-backed signals and policies."""

    def __init__(
        self,
        *,
        strategy_id: str,
        symbols: Sequence[str],
        asset_class: str,
        timeframe: str,
        signals: Sequence[Signal],
        primary_signal: str,
        entry_policy: EntryPolicy,
        exit_policy: ExitPolicy | None = None,
        stop_policy: StopPolicy | None = None,
        target_qty_when_long: float = 1.0,
    ) -> None:
        if not signals:
            raise ValueError("At least one Signal must be provided")
        self._strategy_id = str(strategy_id).strip() or "long_flat_signal"
        self._symbols = tuple(symbol.strip().upper() for symbol in symbols if str(symbol).strip())
        self._asset_class = asset_class
        self._timeframe = timeframe
        self._signals = tuple(signals)
        self._primary_signal = primary_signal
        self._entry_policy = entry_policy
        self._exit_policy = exit_policy
        self._stop_policy = stop_policy or NoOpStopPolicy()
        self._target_qty_when_long = max(0.0, float(target_qty_when_long))

    @property
    def strategy_id(self) -> str:
        return self._strategy_id

    def generate_orders(
        self,
        *,
        run_id: str,
        cycle_id: str,
        decision_ts: datetime,
        event_store: EventStore,
        portfolio: Portfolio,
    ) -> Sequence[Mapping[str, object]]:
        logger.info(
            "Generating policy-driven orders strategy=%s run_id=%s symbols=%s",
            self.strategy_id,
            run_id,
            ",".join(self._symbols) if self._symbols else "<none>",
        )
        orders: list[Mapping[str, object]] = []
        for symbol in self._symbols:
            orders.extend(
                self._generate_orders_for_symbol(
                    symbol,
                    run_id=run_id,
                    cycle_id=cycle_id,
                    decision_ts=decision_ts,
                    event_store=event_store,
                    portfolio=portfolio,
                )
            )
        logger.info("Policy-driven strategy emitted orders count=%s", len(orders))
        return orders

    def generate_orders_for_symbol(
        self,
        symbol: str,
        *,
        run_id: str,
        cycle_id: str,
        decision_ts: datetime,
        event_store: EventStore,
        portfolio: Portfolio,
    ) -> Sequence[Mapping[str, object]]:
        return self._generate_orders_for_symbol(
            symbol.strip().upper(),
            run_id=run_id,
            cycle_id=cycle_id,
            decision_ts=decision_ts,
            event_store=event_store,
            portfolio=portfolio,
        )

    async def order_stream(
        self,
        *,
        run_id: str,
        cycle_id: str,
        decision_ts: datetime,
        event_store: EventStore,
        portfolio: Portfolio,
    ) -> AsyncIterator[Mapping[str, object]]:
        for symbol in self._symbols:
            for order in self._generate_orders_for_symbol(
                symbol,
                run_id=run_id,
                cycle_id=cycle_id,
                decision_ts=decision_ts,
                event_store=event_store,
                portfolio=portfolio,
            ):
                yield order

    def _generate_orders_for_symbol(
        self,
        symbol: str,
        *,
        run_id: str,
        cycle_id: str,
        decision_ts: datetime,
        event_store: EventStore,
        portfolio: Portfolio,
    ) -> list[Mapping[str, object]]:
        table = table_for_asset_class(self._asset_class)
        max_window = max_window_for_signals(self._signals)
        bars = fetch_recent_bars(
            event_store,
            table=table,
            symbol=symbol,
            timeframe=self._timeframe,
            limit=max_window,
            as_of_ts=decision_ts,
        )
        if len(bars) < max_window:
            logger.warning(
                "Skipping policy-driven strategy due to insufficient bars symbol=%s have=%s need=%s",
                symbol,
                len(bars),
                max_window,
            )
            return []

        symbol_signals = compute_signal_map(
            signals=self._signals,
            bars=bars,
            event_store=event_store,
            run_id=run_id,
            cycle_id=cycle_id,
            symbol=symbol,
        )
        if not symbol_signals:
            return []

        position = portfolio.positions.get(symbol, Position(symbol=symbol, qty=0.0, avg_price=None))
        snapshot = StrategySnapshot(
            symbol=symbol,
            decision_ts=decision_ts,
            last_price=float(bars[0].close),
            position_qty=float(position.qty),
            avg_price=position.avg_price,
            signals=dict(symbol_signals),
        )
        if snapshot.is_flat:
            self._stop_policy.reset(symbol)
        else:
            self._stop_policy.observe(snapshot)

        order: Mapping[str, object] | None = None
        if snapshot.is_long and self._stop_policy.should_exit(snapshot):
            order = _flatten_order(symbol, snapshot.position_qty)
        elif snapshot.is_long and self._exit_policy is not None and self._exit_policy.should_exit(snapshot):
            order = _flatten_order(symbol, snapshot.position_qty)
        elif snapshot.is_flat and self._entry_policy.should_enter(snapshot) and self._target_qty_when_long > 0.0:
            order = {
                "symbol": symbol,
                "side": "buy",
                "qty": float(self._target_qty_when_long),
                "order_type": "market",
            }

        _record_signal_event(
            event_store,
            run_id=run_id,
            cycle_id=cycle_id,
            symbol=symbol,
            signal_value=float(symbol_signals.get(self._primary_signal, 0.0)),
            target_qty=float(order.get("qty", 0.0)) if order else 0.0,
        )
        return [order] if order is not None else []


def build_trend_following_strategy(
    *,
    symbols: Sequence[str],
    asset_class: str,
    timeframe: str,
    target_qty_when_long: float = 1.0,
    stop_policy: StopPolicy | None = None,
    ema_fast_period: int = 12,
    ema_slow_period: int = 26,
    macd_fast_period: int = 12,
    macd_slow_period: int = 26,
    macd_signal_period: int = 9,
) -> LongFlatSignalStrategy:
    """Build a trend-following composition over the generic strategy engine."""
    ema_signal = EmaCrossoverSignal(
        fast=EmaIndicator(period=ema_fast_period),
        slow=EmaIndicator(period=ema_slow_period),
    )
    macd_signal = MacdCrossoverSignal(
        indicator=MacdIndicator(
            fast_period=macd_fast_period,
            slow_period=macd_slow_period,
            signal_period=macd_signal_period,
        )
    )
    return LongFlatSignalStrategy(
        strategy_id="trend_following",
        symbols=symbols,
        asset_class=asset_class,
        timeframe=timeframe,
        signals=[ema_signal, macd_signal],
        primary_signal=ema_signal.name,
        entry_policy=SignalThresholdEntryPolicy(
            signal_names=(ema_signal.name, macd_signal.name),
            require_all=False,
            direction="positive",
        ),
        exit_policy=SignalThresholdExitPolicy(
            signal_names=(ema_signal.name, macd_signal.name),
            require_all=False,
            direction="negative",
        ),
        stop_policy=stop_policy,
        target_qty_when_long=target_qty_when_long,
    )


def build_mean_reversion_strategy(
    *,
    symbols: Sequence[str],
    asset_class: str,
    timeframe: str,
    target_qty_when_long: float = 1.0,
    stop_policy: StopPolicy | None = None,
    rsi_period: int = 14,
    oversold: float = 30.0,
    exit_rsi: float = 50.0,
    mean_period: int = 20,
    stretch_pct: float = 0.02,
) -> LongFlatSignalStrategy:
    """Build a mean-reversion composition over the generic strategy engine."""
    rsi_indicator = RsiIndicator(period=rsi_period)
    rsi_entry = RsiThresholdSignal(indicator=rsi_indicator, oversold=oversold, overbought=70.0)
    rsi_recovery = RsiThresholdSignal(
        indicator=rsi_indicator,
        oversold=0.0,
        overbought=exit_rsi,
        name_override=f"rsi_recovery_{rsi_period}_{str(exit_rsi).replace('.', '_')}",
    )
    stretch_signal = SmaStretchSignal(
        indicator=SmaIndicator(period=mean_period),
        min_pct_below=stretch_pct,
        min_pct_above=0.0,
    )
    return LongFlatSignalStrategy(
        strategy_id="mean_reversion",
        symbols=symbols,
        asset_class=asset_class,
        timeframe=timeframe,
        signals=[rsi_entry, rsi_recovery, stretch_signal],
        primary_signal=rsi_entry.name,
        entry_policy=SignalThresholdEntryPolicy(
            signal_names=(rsi_entry.name, stretch_signal.name),
            require_all=True,
            direction="positive",
        ),
        exit_policy=SignalThresholdExitPolicy(
            signal_names=(rsi_recovery.name, stretch_signal.name),
            require_all=False,
            direction="negative",
        ),
        stop_policy=stop_policy,
        target_qty_when_long=target_qty_when_long,
    )


def build_bollinger_band_strategy(
    *,
    symbols: Sequence[str],
    asset_class: str,
    timeframe: str,
    target_qty_when_long: float = 1.0,
    stop_policy: StopPolicy | None = None,
    period: int = 20,
    stddev_multiplier: float = 2.0,
) -> LongFlatSignalStrategy:
    """Build a Bollinger Band composition over the generic strategy engine."""
    band_signal = BollingerBandSignal(
        indicator=BollingerBandsIndicator(period=period, stddev_multiplier=stddev_multiplier)
    )
    return LongFlatSignalStrategy(
        strategy_id="bollinger_band",
        symbols=symbols,
        asset_class=asset_class,
        timeframe=timeframe,
        signals=[band_signal],
        primary_signal=band_signal.name,
        entry_policy=SignalThresholdEntryPolicy(
            signal_names=(band_signal.name,),
            require_all=True,
            direction="positive",
        ),
        exit_policy=SignalThresholdExitPolicy(
            signal_names=(band_signal.name,),
            require_all=True,
            direction="negative",
        ),
        stop_policy=stop_policy,
        target_qty_when_long=target_qty_when_long,
    )


def _evaluate_signal_set(
    signals: Mapping[str, float],
    *,
    signal_names: Sequence[str],
    require_all: bool,
    direction: str,
    threshold: float,
) -> bool:
    values = [signals.get(name) for name in signal_names]
    available = [value for value in values if value is not None]
    if len(available) != len(signal_names):
        return False
    if direction == "negative":
        matches = [value < threshold for value in available]
    else:
        matches = [value > threshold for value in available]
    return all(matches) if require_all else any(matches)


def _flatten_order(symbol: str, qty: float) -> Mapping[str, object]:
    return {
        "symbol": symbol,
        "side": "sell",
        "qty": float(qty),
        "order_type": "market",
    }


def _record_signal_event(
    event_store: EventStore,
    *,
    run_id: str,
    cycle_id: str,
    symbol: str,
    signal_value: float,
    target_qty: float,
) -> None:
    event_store.record_event(
        "signal_events",
        {
            "run_id": run_id,
            "session_id": run_id,
            "cycle_id": cycle_id,
            "symbol": symbol,
            "signal_value": float(signal_value),
            "target_qty": float(target_qty),
            "generated_at": datetime.now(timezone.utc),
        },
    )
