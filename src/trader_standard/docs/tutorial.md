# Maintained Strategy Tutorial

This offline tutorial shows how maintained pieces fit together before introducing Postgres-backed bar access.

## 1. Inspect a strategy policy decision

Policies consume a `StrategySnapshot`, not adapters or database rows. This makes their decision surface easy to test.

<!-- verified: doctest -->
```pycon
>>> from datetime import UTC, datetime
>>> from trader_standard import FixedStopLossPolicy, StrategySnapshot
>>> policy = FixedStopLossPolicy(stop_loss_pct=0.10)
>>> stable = StrategySnapshot(
...     symbol="AAPL", decision_ts=datetime(2026, 1, 1, tzinfo=UTC),
...     last_price=95.0, position_qty=1.0, avg_price=100.0, signals={},
... )
>>> policy.should_exit(stable)
False
>>> breached = StrategySnapshot(
...     symbol="AAPL", decision_ts=datetime(2026, 1, 2, tzinfo=UTC),
...     last_price=89.0, position_qty=1.0, avg_price=100.0, signals={},
... )
>>> policy.should_exit(breached)
True
```

## 2. Compose a maintained strategy

Builders bind indicators, signals, entry/exit policies, and optional stops into a `LongFlatSignalStrategy`.

<!-- verified: doctest -->
```pycon
>>> from trader_standard import build_trend_following_strategy
>>> strategy = build_trend_following_strategy(
...     symbols=("AAPL", "MSFT"),
...     asset_class="stocks",
...     timeframe="1Hour",
...     ema_fast_period=10,
...     ema_slow_period=30,
...     target_qty_when_long=2.0,
... )
>>> strategy.strategy_id
'trend_following'
>>> strategy.strategy_info.parameters["symbols"]
['AAPL', 'MSFT']
```

The strategy has not read data or emitted an order. Those effects occur only when the runtime supplies an event store,
portfolio, decision timestamp, and run identifiers.

## 3. Add risk independently

Strategy stop policies create exit intent. Runtime risk managers authorize candidate orders. Keep both layers even when
they appear to enforce related limits: they answer different questions and generate different evidence.

<!-- verified: doctest -->
```pycon
>>> from trader import RiskPipeline
>>> from trader_standard import MaxOrdersPerRunRiskManager, MaxPositionUsdPerSymbolRiskManager
>>> risk = RiskPipeline([
...     MaxOrdersPerRunRiskManager(limit=20),
...     MaxPositionUsdPerSymbolRiskManager(limit_usd=5_000.0),
... ])
>>> len(risk.managers)
2
```

## 4. Execute through core

Use the [`trader` tutorial](../../trader/docs/tutorial.md) for the Postgres-backed sample. The wrapper constructs a
maintained strategy and risk manager, injects them into `BacktestRunner`, and exports results. The strategy package does
not own execution.

## 5. Extend safely

Subclass a core interface when no maintained implementation has the required semantics. Test pure calculations first;
then test event-store reads, metadata, and runtime composition. Do not alter a maintained strategy merely to make one
experiment fit: author and admit a separate research candidate so comparison and provenance remain visible.

The [strategy authoring workflow](strategy_authoring.md) provides a larger Postgres example. Its research steps are
executed through the current MCP evidence boundary, not by loading arbitrary YAML code.

## 6. Inspect results and failure behavior

Inspect the core `BacktestResult`, warnings, trade ledger, assumptions, and benchmark rather than treating a strategy
object or headline return as success. Insufficient lookback, missing bars, non-finite calculations, rejected risk, and
invalid metadata are explicit failures or no-action outcomes; do not replace them with a convenient signal.

Continue with the [catalogue](catalogue.md) for available components and the [architecture](architecture.md) for the
package boundary.
