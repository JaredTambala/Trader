"""In-memory bar-based signal generator for backtests."""

from __future__ import annotations

from bisect import bisect_right
from datetime import datetime, timezone
import logging
from typing import Iterable, Mapping, Sequence

from trader.data import EventStore
from trader.signals import Bar, Signal
from trader.signal_generators import SignalGenerator

from trader_standard.bar_signals import compute_signal_map, max_window_for_signals


logger = logging.getLogger(__name__)


class InMemoryBarsSignalGenerator(SignalGenerator):
    """Compute bar-based signals using preloaded in-memory bars."""

    def __init__(
        self,
        *,
        bars_by_symbol: Mapping[str, Sequence[Bar]],
        signals: Sequence[Signal],
        symbols: Iterable[str] | None = None,
        timeframe: str | None = None,
        event_store: EventStore | None = None,
    ) -> None:
        """Initialize the instance."""
        if not signals:
            raise ValueError("At least one Signal must be provided")
        self._signals = tuple(signals)
        self._symbols = tuple(symbols) if symbols is not None else tuple(bars_by_symbol.keys())
        self._timeframe = timeframe or "<unknown>"
        self._event_store = event_store
        self._bars_by_symbol: dict[str, list[Bar]] = {}
        self._timestamps_by_symbol: dict[str, list[datetime]] = {}
        for symbol, bars in bars_by_symbol.items():
            ordered = sorted(bars, key=lambda bar: bar.ts)
            self._bars_by_symbol[symbol] = ordered
            self._timestamps_by_symbol[symbol] = [_normalize_timestamp(bar.ts) for bar in ordered]

    @property
    def signals(self) -> Sequence[Signal]:
        """Return configured signal definitions."""
        return self._signals

    @property
    def symbols(self) -> Sequence[str]:
        """Return the configured symbol universe."""
        return self._symbols

    @property
    def supports_symbol_generation(self) -> bool:
        """Report whether per-symbol signal generation is supported."""
        return True

    def generate(
        self,
        *,
        as_of_ts: datetime | None = None,
        run_id: str | None = None,
        cycle_id: str | None = None,
    ) -> Mapping[str, Mapping[str, float]]:
        """Generate signal events from available market data."""
        max_window = max_window_for_signals(self._signals)
        cutoff = _normalize_timestamp(as_of_ts) if as_of_ts else None
        logger.info(
            "Signal generation start timeframe=%s symbols=%s window=%s as_of_ts=%s",
            self._timeframe,
            ",".join(self._symbols) if self._symbols else "<none>",
            max_window,
            cutoff.isoformat() if cutoff else "<latest>",
        )
        output: dict[str, dict[str, float]] = {}
        for symbol in self._symbols:
            bars = self._bars_by_symbol.get(symbol, [])
            timestamps = self._timestamps_by_symbol.get(symbol, [])
            if not bars:
                continue
            if cutoff is None:
                window_bars = bars[-max_window:]
            else:
                idx = bisect_right(timestamps, cutoff) - 1
                if idx < 0:
                    continue
                start = max(0, idx + 1 - max_window)
                window_bars = bars[start : idx + 1]
            if len(window_bars) < max_window:
                logger.warning(
                    "Skipping signal generation due to insufficient bars symbol=%s have=%s need=%s",
                    symbol,
                    len(window_bars),
                    max_window,
                )
                continue
            latest_first = list(reversed(window_bars))
            symbol_signals = compute_signal_map(
                signals=self._signals,
                bars=latest_first,
                event_store=self._event_store,
                run_id=run_id,
                cycle_id=cycle_id,
                symbol=symbol,
            )
            if symbol_signals:
                output[symbol] = symbol_signals
        return output

    def generate_for_symbol(
        self,
        symbol: str,
        *,
        as_of_ts: datetime | None = None,
        run_id: str | None = None,
        cycle_id: str | None = None,
    ) -> Mapping[str, float] | None:
        """Generate signal events for a single symbol."""
        max_window = max(signal.window for signal in self._signals)
        cutoff = _normalize_timestamp(as_of_ts) if as_of_ts else None
        bars = self._bars_by_symbol.get(symbol, [])
        timestamps = self._timestamps_by_symbol.get(symbol, [])
        if not bars:
            return None
        if cutoff is None:
            window_bars = bars[-max_window:]
        else:
            idx = bisect_right(timestamps, cutoff) - 1
            if idx < 0:
                return None
            start = max(0, idx + 1 - max_window)
            window_bars = bars[start : idx + 1]
        if len(window_bars) < max_window:
            logger.warning(
                "Skipping signal generation due to insufficient bars symbol=%s have=%s need=%s",
                symbol,
                len(window_bars),
                max_window,
            )
            return None
        latest_first = list(reversed(window_bars))
        symbol_signals = compute_signal_map(
            signals=self._signals,
            bars=latest_first,
            event_store=self._event_store,
            run_id=run_id,
            cycle_id=cycle_id,
            symbol=symbol,
        )
        return symbol_signals or None


def _normalize_timestamp(value: datetime) -> datetime:
    """Normalize timestamp values to UTC-aware datetimes."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
