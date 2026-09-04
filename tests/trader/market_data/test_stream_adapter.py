"""Contracts for lazy stream-adapter dependencies and provider-bar conversion.

Subject: Warning-clean imports, scoped Alpaca live loading, and stock or crypto stream-event construction.
Level: Fresh-process import contracts and deterministic adapter unit contracts.
Collaborators: Real stream helpers, two bounded Python subprocesses, and provider-shaped in-memory bars.
Guarantees: Core imports stay lazy while requested live types load safely and bars retain canonical values.
Non-goals: Network subscriptions, reconnect behavior, Postgres writes, notifications, or sustained streaming.
"""

from __future__ import annotations

from datetime import datetime, timezone
import subprocess
import sys

from trader.market_data import CryptoBarEvent, StockBarEvent
from trader.market_data.stream import StreamContext, _build_bar_event


def test_core_and_stream_module_imports_are_warning_clean_and_lazy() -> None:
    """Ensure importing core stream helpers does not eagerly load Alpaca live dependencies."""
    result = subprocess.run(
        [
            sys.executable,
            "-W",
            "error",
            "-c",
            (
                "import sys; import trader; "
                "assert 'alpaca.data.live' not in sys.modules; "
                "import trader.market_data.stream; "
                "assert 'alpaca.data.live' not in sys.modules"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_alpaca_live_adapter_import_scopes_upstream_deprecation() -> None:
    """Ensure explicit live-type loading contains the provider deprecation warning boundary."""
    result = subprocess.run(
        [
            sys.executable,
            "-W",
            "error",
            "-c",
            (
                "from trader.market_data.stream import _load_alpaca_live_types; "
                "assert len(_load_alpaca_live_types()) == 4"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


class FakeBar:
    def __init__(
        self,
        symbol: str,
        ts: datetime,
        open_price: float,
        high: float,
        low: float,
        close: float,
        volume: float,
    ) -> None:
        self.symbol = symbol
        self.timestamp = ts
        self.open = open_price
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume


def test_build_bar_event_for_stocks() -> None:
    """Ensure streamed stock bars retain prices, identity, and configured timeframe."""
    now = datetime(2026, 1, 20, tzinfo=timezone.utc)
    bar = FakeBar("AAPL", now, 100.0, 101.0, 99.5, 100.5, 10.0)
    context = StreamContext(
        event_store=None,
        asset_class="stocks",
        source="alpaca",
        timeframe="1Min",
    )
    event = _build_bar_event(context, bar)
    assert isinstance(event, StockBarEvent)
    assert event.symbol == "AAPL"
    assert event.close == 100.5
    assert event.timeframe == "1Min"


def test_build_bar_event_for_crypto() -> None:
    """Ensure streamed crypto bars retain prices, identity, and configured timeframe."""
    now = datetime(2026, 1, 20, tzinfo=timezone.utc)
    bar = FakeBar("BTC/USD", now, 1.0, 2.0, 0.5, 1.5, 0.1)
    context = StreamContext(
        event_store=None,
        asset_class="crypto",
        source="alpaca",
        timeframe="1Min",
    )
    event = _build_bar_event(context, bar)
    assert isinstance(event, CryptoBarEvent)
    assert event.symbol == "BTC/USD"
    assert event.close == 1.5
