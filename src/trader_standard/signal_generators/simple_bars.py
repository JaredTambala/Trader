"""Bar-based signal generator backed by the event store."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Iterable, Mapping, Sequence

from trader.event_store import EventStore
from trader.signals import Bar, Signal
from trader.signal_generators import SignalGenerator

from trader_standard.bar_signals import (
    compute_signal_map,
    fetch_recent_bars,
    max_window_for_signals,
    table_for_asset_class,
)


logger = logging.getLogger(__name__)


class SimpleBarsSignalGenerator(SignalGenerator):
    """Compute bar-based signals from OHLCV rows persisted in the event store.

    The generator fetches latest-first windows per symbol and records indicator
    telemetry through shared bar-signal helpers when correlation IDs are present.
    """

    def __init__(
        self,
        *,
        event_store: EventStore,
        symbols: Iterable[str],
        asset_class: str,
        timeframe: str,
        signals: Sequence[Signal],
    ) -> None:
        """Store event-store access, symbols, asset class, timeframe, and signals."""
        if not signals:
            raise ValueError("At least one Signal must be provided")
        self._event_store = event_store
        self._symbols = tuple(symbols)
        self._asset_class = asset_class.lower()
        self._timeframe = timeframe
        self._signals = tuple(signals)

    @property
    def signals(self) -> Sequence[Signal]:
        """Return the ordered signal definitions evaluated for every configured symbol in output maps."""
        return self._signals

    @property
    def symbols(self) -> Sequence[str]:
        """Return the configured symbol universe in caller-provided deterministic order for generation."""
        return self._symbols

    @property
    def supports_symbol_generation(self) -> bool:
        """Report that this generator can evaluate one requested symbol independently for streaming."""
        return True

    def generate(
        self,
        *,
        as_of_ts: datetime | None = None,
        run_id: str | None = None,
        cycle_id: str | None = None,
    ) -> Mapping[str, Mapping[str, float]]:
        """Generate per-symbol signal maps from event-store bars at an optional cutoff.

        Each symbol fetches a latest-first window from the asset-class table,
        insufficient windows are skipped with warnings, and computed signal maps
        include run/cycle IDs for indicator telemetry.
        """
        table = table_for_asset_class(self._asset_class)
        max_window = max_window_for_signals(self._signals)
        logger.info(
            "Signal generation start table=%s timeframe=%s symbols=%s window=%s as_of_ts=%s",
            table,
            self._timeframe,
            ",".join(self._symbols) if self._symbols else "<none>",
            max_window,
            as_of_ts.isoformat() if as_of_ts else "<latest>",
        )
        output: dict[str, dict[str, float]] = {}
        for symbol in self._symbols:
            bars = _fetch_recent_bars(
                self._event_store,
                table,
                symbol,
                self._timeframe,
                max_window,
                as_of_ts=as_of_ts,
            )
            logger.debug("Fetched bars symbol=%s count=%s", symbol, len(bars))
            if len(bars) < max_window:
                logger.warning(
                    "Skipping signal generation due to insufficient bars symbol=%s have=%s need=%s",
                    symbol,
                    len(bars),
                    max_window,
                )
                continue
            symbol_signals = compute_signal_map(
                signals=self._signals,
                bars=bars,
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
        """Generate signals for one symbol or return `None` when no full window exists.

        The method uses the same event-store fetch, insufficient-bar warning, and
        telemetry path as batch generation while avoiding unrelated symbols.
        """
        table = table_for_asset_class(self._asset_class)
        max_window = max_window_for_signals(self._signals)
        bars = _fetch_recent_bars(
            self._event_store,
            table,
            symbol,
            self._timeframe,
            max_window,
            as_of_ts=as_of_ts,
        )
        logger.debug("Fetched bars symbol=%s count=%s", symbol, len(bars))
        if len(bars) < max_window:
            logger.warning(
                "Skipping signal generation due to insufficient bars symbol=%s have=%s need=%s",
                symbol,
                len(bars),
                max_window,
            )
            return None
        symbol_signals = compute_signal_map(
            signals=self._signals,
            bars=bars,
            event_store=self._event_store,
            run_id=run_id,
            cycle_id=cycle_id,
            symbol=symbol,
        )
        return symbol_signals or None


def _fetch_recent_bars(
    event_store: EventStore,
    table: str,
    symbol: str,
    timeframe: str,
    limit: int,
    *,
    as_of_ts: datetime | None = None,
) -> list[Bar]:
    """Fetch recent OHLCV bars for a symbol/timeframe (latest first)."""
    return fetch_recent_bars(
        event_store,
        table=table,
        symbol=symbol,
        timeframe=timeframe,
        limit=limit,
        as_of_ts=as_of_ts,
    )
