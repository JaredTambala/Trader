"""Pure tests for deterministic backtest comparison scope metadata.

Subject: Backtest scope and variant fingerprints.
Level: Unit.
Collaborators: Typed review-scope builders and normalized OHLCV inputs.
Guarantees: Equivalent ordering is stable, material scope changes are visible,
and intentional strategy variants remain separate from the compatibility scope.
Non-goals: Database projection, Superset assets, or backtest execution.
"""

from datetime import UTC, datetime

from trader.backtest.models import BacktestAssumptions
from trader.backtest.review_scope import (
    build_backtest_review_scope,
    build_backtest_variant,
)
from trader.portfolio import Position
from trader.signals import Bar


BASE_TS = datetime(2026, 1, 1, 14, 30, tzinfo=UTC)


def _bars() -> dict[str, list[Bar]]:
    return {
        "AAPL": [
            Bar(BASE_TS, 100, 101, 99, 100.5, 10, None, None),
            Bar(BASE_TS.replace(minute=31), 100.5, 102, 100, 101, 11, None, None),
        ],
        "MSFT": [
            Bar(BASE_TS, 200, 201, 199, 200.5, 20, None, None),
        ],
    }


def _scope(*, bars: dict[str, list[Bar]] | None = None, cash: float = 10_000) -> object:
    return build_backtest_review_scope(
        asset_class="stock",
        symbols=("MSFT", "AAPL"),
        timeframe="1Min",
        replay_start=BASE_TS,
        replay_end=BASE_TS.replace(minute=31),
        bars_by_symbol=bars if bars is not None else _bars(),
        initial_cash=cash,
        initial_positions=[Position("AAPL", 2, 99), Position("MSFT", 1, None)],
        assumptions=BacktestAssumptions(),
    )


def test_scope_fingerprint_ignores_input_order() -> None:
    """Equivalent symbols, bars, and positions have one compatibility identity."""
    first = _scope()
    reversed_bars = {"MSFT": list(reversed(_bars()["MSFT"])), "AAPL": list(reversed(_bars()["AAPL"]))}
    second = build_backtest_review_scope(
        asset_class="stock",
        symbols=("AAPL", "MSFT"),
        timeframe="1Min",
        replay_start=BASE_TS,
        replay_end=BASE_TS.replace(minute=31),
        bars_by_symbol=reversed_bars,
        initial_cash=10_000,
        initial_positions=[Position("MSFT", 1, None), Position("AAPL", 2, 99)],
        assumptions=BacktestAssumptions(),
    )

    assert first.scope_fingerprint == second.scope_fingerprint
    assert first.data_scope_id == second.data_scope_id


def test_scope_fingerprint_changes_for_data_or_initial_state() -> None:
    """A changed replay bar or initial cash cannot join the original cohort."""
    changed_bar = _bars()
    changed_bar["AAPL"][0] = Bar(BASE_TS, 100, 101, 99, 100.75, 10, None, None)

    assert _scope().scope_fingerprint != _scope(bars=changed_bar).scope_fingerprint
    assert _scope().scope_fingerprint != _scope(cash=9_000).scope_fingerprint


def test_variant_fingerprint_is_separate_from_scope() -> None:
    """Strategy and parameters identify intentional variants without changing scope."""
    first = build_backtest_variant(strategy_id="strategy_a", parameters={"threshold": 0.5})
    second = build_backtest_variant(strategy_id="strategy_b", parameters={"threshold": 0.5})
    reordered = build_backtest_variant(strategy_id="strategy_a", parameters={"threshold": 0.5})

    assert first.variant_fingerprint != second.variant_fingerprint
    assert first.parameters_fingerprint == reordered.parameters_fingerprint
    assert first.parameters == {"threshold": 0.5}
