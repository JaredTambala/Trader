"""Contract for the checked-in BTC/USD Bollinger backtest composition.

Subject: Reproducible configuration and maintained Bollinger composition.
Level: Deterministic strategy/configuration test.
Collaborators: YAML config normalization and trader_standard indicator/signal/strategy builders.
Guarantees: The requested crypto symbol, timeframe, window, Bollinger parameters, and persistence flags are wired.
Non-goals: Running the full three-month replay, profitability, provider availability, or database qualification.
"""

from pathlib import Path
from datetime import datetime, timezone

from trader.config import build_config, load_yaml_config
from trader.indicators import IndicatorObservation
from trader.signals import Bar
from trader_standard.indicators import BollingerBandsIndicator
from trader_standard.signals import BollingerBandSignal

from examples.strategy_library_support import build_library_strategy


CONFIG_PATH = Path("configs/btc_usd_bollinger_backtest.yaml")


def test_btc_bollinger_config_wires_the_maintained_composition() -> None:
    """Keep the reproducible BTC/USD scope connected to the typed Bollinger strategy."""
    data = load_yaml_config(CONFIG_PATH)
    config = build_config(data)
    strategy = build_library_strategy(data, config)

    assert config.market_data_asset_class == "crypto"
    assert config.market_data_symbols == ("BTC/USD",)
    assert config.strategy_timeframe == "1Min"
    assert data["backtest"]["start"] == "2026-06-21T00:00:00Z"
    assert data["backtest"]["end"] == "2026-09-21T21:25:00Z"
    assert strategy.strategy_id == "bollinger_band"
    assert strategy.required_lookback == 21
    assert strategy.strategy_info.parameters["signals"] == ["bollinger_band_20_2_0"]
    assert data["logging"]["persist"] == {
        "signals": True,
        "indicators": True,
        "orders": True,
        "fills": True,
        "positions": True,
    }


def test_bollinger_signal_emits_typed_price_and_volatility_series() -> None:
    """Expose each Bollinger component with explicit chart semantics."""
    bars = [
        Bar(ts=datetime(2026, 1, 1, 0, index, tzinfo=timezone.utc),
            open=100 + index, high=101 + index, low=99 + index, close=100 + index,
            volume=1.0, vwap=None, trade_count=None)
        for index in range(25)
    ][::-1]
    observations = BollingerBandSignal(
        indicator=BollingerBandsIndicator(period=20, stddev_multiplier=2.0),
    ).indicator_values(bars)

    assert all(isinstance(observation, IndicatorObservation) for observation in observations)
    displays = [observation.payload["display"] for observation in observations]
    assert [display["pane"] for display in displays] == ["price", "price", "price", "secondary"]
    assert displays[-1]["scale_group"] == "volatility"
