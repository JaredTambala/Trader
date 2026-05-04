from __future__ import annotations

from trader.strategy_metadata import StrategyInfo, resolve_strategy_info
from trader_standard.strategies import ToggleUnitStrategy, build_trend_following_strategy


def test_strategy_metadata_fallback_for_plain_strategy() -> None:
    strategy = ToggleUnitStrategy(symbols=("DEMO",), order_qty=2.0)

    info = resolve_strategy_info(strategy, parameters={"order_qty": 2.0})

    assert info.strategy_id == "toggle"
    assert info.version == "1"
    assert info.parameters["order_qty"] == 2.0
    assert info.source is not None


def test_standard_policy_strategy_exposes_metadata() -> None:
    strategy = build_trend_following_strategy(
        symbols=("DEMO",),
        asset_class="stocks",
        timeframe="1Min",
        ema_fast_period=2,
        ema_slow_period=4,
    )

    info = resolve_strategy_info(strategy)

    assert isinstance(info, StrategyInfo)
    assert info.strategy_id == "trend_following"
    assert info.parameters["symbols"] == ["DEMO"]
    assert "signals" in info.parameters
