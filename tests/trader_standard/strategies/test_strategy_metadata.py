"""Contracts for metadata exposed by maintained strategy implementations.

Subject: Fallback identity for simple implementations and explicit metadata for policy-driven compositions.
Level: Deterministic public-surface unit contracts.
Collaborators: Real standard strategies with the core strategy-metadata resolver and value object.
Guarantees: Maintained strategies yield stable identifiers, versions, sources, and material parameter evidence.
Non-goals: Strategy execution, implementation admission, source hashing, persistence, or compatibility versioning.
"""

from __future__ import annotations

from trader.strategy_metadata import StrategyInfo, resolve_strategy_info
from trader_standard.strategies import (
    ToggleUnitStrategy,
    build_trend_following_strategy,
)


def test_strategy_metadata_fallback_for_plain_strategy() -> None:
    """Ensure a simple maintained strategy receives stable fallback identity and parameters."""
    strategy = ToggleUnitStrategy(symbols=("DEMO",), order_qty=2.0)

    info = resolve_strategy_info(strategy, parameters={"order_qty": 2.0})

    assert info.strategy_id == "toggle"
    assert info.version == "1"
    assert info.parameters["order_qty"] == 2.0
    assert info.source is not None


def test_standard_policy_strategy_exposes_metadata() -> None:
    """Ensure a maintained policy composition exposes its family and nested signal parameters."""
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
