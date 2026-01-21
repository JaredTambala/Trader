"""Tests for market data ingestion flow."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb

from trader.alpaca_market_data import AlpacaMarketDataSource, AlpacaRequestSpec
from trader.config import Config
from trader.cycle import run_cycle
from trader.data import DuckDBEventStore, EventStore
from trader.market_data import CryptoBarEvent, StaticMarketDataSource, StockBarEvent
from trader.strategy import Strategy


class RecordingEventStore(EventStore):
    """Event store that records events in memory for assertions."""

    def __init__(self) -> None:
        """Initialize the in-memory event log."""
        self.events: list[tuple[str, dict[str, object]]] = []

    def record_event(self, event_type: str, payload: dict[str, object]) -> None:
        """Capture an event record for later inspection.

        Args:
            event_type: Name of the event table/type.
            payload: Event payload.

        Raises:
            None.
        """
        self.events.append((event_type, payload))


class ProbeStrategy(Strategy):
    """Strategy that asserts market data was ingested before signal generation."""

    def __init__(self, event_store: RecordingEventStore) -> None:
        """Create the probe strategy.

        Args:
            event_store: Event store used for assertion of ingestion ordering.
        """
        self._event_store = event_store
        self.calls = 0

    @property
    def strategy_id(self) -> str:
        """Return the strategy identifier.

        Returns:
            Strategy identifier string.
        """
        return "probe"

    def generate_signals(self):
        """Assert market data events exist before producing signals.

        Returns:
            Empty list of signals.

        Raises:
            AssertionError: If market data has not been recorded yet.
        """
        self.calls += 1
        assert any(event_type == "stock_bar_events" for event_type, _ in self._event_store.events)
        return []


def _config(tmp_path: Path, max_age_seconds: int = 60) -> Config:
    """Build a Config instance for tests.

    Args:
        tmp_path: Pytest temporary path fixture.
        max_age_seconds: Staleness cutoff.

    Returns:
        Config instance for test runs.
    """
    return Config(
        mode="once",
        strategy_id="probe",
        db_path=str(tmp_path / "events.duckdb"),
        market_data_source="noop",
        market_data_asset_class="stocks",
        market_data_stock_feed="iex",
        market_data_symbols=(),
        market_data_max_age_seconds=max_age_seconds,
        alpaca_api_key="",
        alpaca_secret_key="",
        alpaca_data_base_url="https://data.alpaca.markets",
    )


def test_market_data_ingested_before_strategy(tmp_path: Path) -> None:
    """Ensure ingestion occurs before strategy execution.

    Args:
        tmp_path: Pytest temporary path fixture.

    Raises:
        AssertionError: If market data is not ingested first.
    """
    event_store = RecordingEventStore()
    now = datetime.now(timezone.utc)
    events = [
        StockBarEvent(
            symbol="AAPL",
            timeframe="1Min",
            ts=now,
            ingested_at=now,
            open=149.0,
            high=151.0,
            low=148.5,
            close=150.0,
            volume=10.0,
            trade_count=1.0,
            vwap=150.0,
            source="test",
        )
    ]
    strategy = ProbeStrategy(event_store)
    run_cycle(
        event_store=event_store,
        strategy=strategy,
        market_data_source=StaticMarketDataSource(events),
        config=_config(tmp_path),
        decision_ts=now,
    )
    assert strategy.calls == 1


def test_stale_market_data_skips_strategy(tmp_path: Path) -> None:
    """Ensure stale data causes strategy execution to be skipped.

    Args:
        tmp_path: Pytest temporary path fixture.

    Raises:
        AssertionError: If strategy runs despite stale data.
    """
    event_store = RecordingEventStore()
    stale_ts = datetime.now(timezone.utc) - timedelta(seconds=3600)
    events = [
        StockBarEvent(
            symbol="AAPL",
            timeframe="1Min",
            ts=stale_ts,
            ingested_at=stale_ts,
            open=149.0,
            high=151.0,
            low=148.5,
            close=150.0,
            volume=10.0,
            trade_count=1.0,
            vwap=150.0,
            source="test",
        )
    ]
    strategy = ProbeStrategy(event_store)
    run_cycle(
        event_store=event_store,
        strategy=strategy,
        market_data_source=StaticMarketDataSource(events),
        config=_config(tmp_path, max_age_seconds=60),
        decision_ts=stale_ts,
    )
    assert strategy.calls == 0


def test_market_data_persisted_to_duckdb(tmp_path: Path) -> None:
    """Ensure ingested market data is persisted to DuckDB.

    Args:
        tmp_path: Pytest temporary path fixture.

    Raises:
        AssertionError: If market data is not persisted.
    """
    db_path = tmp_path / "events.duckdb"
    store = DuckDBEventStore(str(db_path))
    now = datetime.now(timezone.utc)
    events = [
        StockBarEvent(
            symbol="MSFT",
            timeframe="1Min",
            ts=now,
            ingested_at=now,
            open=299.0,
            high=301.0,
            low=298.5,
            close=300.0,
            volume=5.0,
            trade_count=1.0,
            vwap=300.0,
            source="test",
        )
    ]

    run_cycle(
        event_store=store,
        market_data_source=StaticMarketDataSource(events),
        config=_config(tmp_path),
        decision_ts=now,
    )

    conn = duckdb.connect(str(db_path))
    count = conn.execute("SELECT COUNT(*) FROM stock_bar_events").fetchone()[0]
    assert count == 1
    store.close()


def test_alpaca_market_data_source_parses_bars() -> None:
    """Ensure Alpaca market data source maps bar data to events.

    Raises:
        AssertionError: If the bar data is not parsed correctly.
    """

    class FakeBar:
        def __init__(
            self,
            ts: datetime,
            open_price: float,
            high: float,
            low: float,
            close: float,
            volume: float,
        ) -> None:
            self.t = ts
            self.o = open_price
            self.h = high
            self.l = low
            self.c = close
            self.v = volume

    class FakeResponse:
        def __init__(self, data: dict[str, list[FakeBar]]) -> None:
            self.data = data

    class FakeClient:
        def __init__(self) -> None:
            self.requests: list[object] = []

        def get_stock_bars(self, request: object) -> FakeResponse:
            self.requests.append(request)
            return FakeResponse(
                {
                    "AAPL": [
                        FakeBar(
                            datetime(2024, 1, 1, tzinfo=timezone.utc),
                            open_price=149.0,
                            high=151.0,
                            low=148.5,
                            close=150.5,
                            volume=10.0,
                        )
                    ]
                }
            )

    def request_builder(symbols, start, end, timeframe, limit, feed):
        return {
            "symbols": symbols,
            "start": start,
            "end": end,
            "timeframe": timeframe,
            "limit": limit,
            "feed": feed,
        }

    source = AlpacaMarketDataSource(
        api_key="key",
        secret_key="secret",
        base_url="https://data.alpaca.markets",
        symbols=["AAPL"],
        asset_class="stocks",
        client=FakeClient(),
        request_spec=AlpacaRequestSpec(
            request_builder=request_builder,
            timeframe="1Min",
            limit=1,
            method="bars",
            feed=None,
        ),
    )

    events = source.fetch()
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, StockBarEvent)
    assert event.symbol == "AAPL"
    assert event.open == 149.0
    assert event.close == 150.5
    assert event.volume == 10.0
    assert event.timeframe == "1Min"


def test_crypto_bar_event_persists(tmp_path: Path) -> None:
    """Ensure crypto bar events are written to the crypto table."""
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    now = datetime.now(timezone.utc)
    event = CryptoBarEvent(
        symbol="BTC/USD",
        timeframe="1Min",
        ts=now,
        ingested_at=now,
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        volume=0.1,
        trade_count=None,
        vwap=None,
        source="test",
    )
    store.record_event(event.table_name, event.to_payload())
    conn = duckdb.connect(str(tmp_path / "events.duckdb"))
    count = conn.execute("SELECT COUNT(*) FROM crypto_bar_events").fetchone()[0]
    assert count == 1
