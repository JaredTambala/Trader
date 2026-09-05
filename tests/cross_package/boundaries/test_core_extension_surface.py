"""Contract tests for the core-to-maintained-extension facade.

Subject: The public separation between core Trader contracts and trader_standard implementations.
Level: Cross-package architecture contract.
Collaborators: The imported public trader and trader_standard facades; no external service.
Guarantees: Core exports protocols while maintained concrete implementations remain outward.
Non-goals: Internal core layering, strategy behavior, and runtime execution.
"""

import trader
import trader_standard


def test_trader_core_exports_contracts_not_standard_implementations() -> None:
    """Keep core extension contracts separate from maintained standard implementations."""
    assert hasattr(trader, 'Strategy')
    assert hasattr(trader, 'RiskManager')
    assert hasattr(trader, 'BacktestRunner')
    assert not hasattr(trader, 'ToggleUnitStrategy')
    assert not hasattr(trader, 'NoOpRiskManager')
    assert not hasattr(trader, 'build_trend_following_strategy')
    assert hasattr(trader_standard, 'ToggleUnitStrategy')
    assert hasattr(trader_standard, 'NoOpRiskManager')
    assert hasattr(trader_standard, 'build_trend_following_strategy')
