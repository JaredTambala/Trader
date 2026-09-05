# Trader Core Tutorial

This tutorial starts with the package's mental model, exercises its pure boundaries offline, then points to the exact
integration path for a Postgres-backed backtest. It deliberately avoids a broker connection.

## 1. Think in contracts and injected implementations

The core runtime does not select a trading idea. A caller supplies an object implementing `Strategy` and an object
implementing `RiskManager`. The same objects can be used by historical replay or the paper runtime. This keeps strategy
choice outside the engine and makes the execution context explicit.

The key flow is:

```text
normalized bars -> strategy intent -> risk decision -> broker fill -> portfolio transition -> append-only evidence
```

## 2. Normalize configuration at the boundary

`build_config` turns nested, external data into the typed `Config` consumed by runtime code. Symbols and timeframes are
normalized here rather than throughout the engine.

<!-- verified: doctest -->
```pycon
>>> from trader import build_config
>>> config = build_config({
...     "runtime": {"mode": "once"},
...     "strategy": {"id": "tutorial", "timeframe": "1min"},
...     "market_data": {"symbols": [" aapl ", "MSFT"]},
...     "broker": {"type": "noop"},
...     "database": {"event_store": "noop"},
... })
>>> config.strategy_timeframe
'1Min'
>>> config.market_data_symbols
('AAPL', 'MSFT')
>>> config.broker_type
'noop'
```

For file and environment expansion, use `load_yaml_config` before `build_config`; see
[Configuration](configuration.md).

## 3. Create auditable simulation assumptions

Backtest assumptions are immutable values recorded with the result. They make costs and missing-data behavior visible
to downstream comparison code.

<!-- verified: doctest -->
```pycon
>>> from trader import build_backtest_assumptions
>>> assumptions = build_backtest_assumptions({
...     "fees": {"fixed_per_order": 0.25, "bps": 1.0},
...     "slippage": {"bps": 2.0},
...     "data": {"allow_latest_prior_bar": False},
... })
>>> assumptions.fees.fixed_per_order
0.25
>>> assumptions.slippage.bps
2.0
>>> assumptions.data.allow_latest_prior_bar
False
```

## 4. Choose the implementation layer

Use `trader_standard` when a maintained implementation fits. Define your own `Strategy`, `RiskManager`, `Signal`, or
`Indicator` against the core abstractions when it does not. Do not place provider calls inside a strategy: market data,
the clock, persistence, and brokers are runtime-owned effects.

The smallest safe dry-run strategy is the maintained `NoOpStrategy`:

<!-- verified: doctest -->
```pycon
>>> from trader_standard import NoOpStrategy, NoOpRiskManager
>>> strategy = NoOpStrategy()
>>> risk_manager = NoOpRiskManager()
>>> strategy.strategy_id
'noop'
```

That example proves composition only; it does not run a backtest.

## 5. Reach the first Postgres-backed result

The canonical sample loads deterministic CSV bars, composes a maintained strategy, runs historical replay, and exports
JSON plus CSV. It requires the repository checkout and local Postgres.

<!-- verified: integration:postgres tests/cross_package/workflows/test_sample_data.py tests/trader/backtest/test_backtest.py -->
```bash
docker compose -f docker-compose.postgres.yml up -d
uv run python examples/load_sample_market_data.py
uv run python examples/run_reproducible_backtest.py --output-dir /tmp/trader-tutorial-result
```

Inspect `result.json`, `equity_curve.csv`, and `trades.csv`. The result reports the run window, execution assumptions,
trade accounting, strategy and benchmark performance, warnings, and provenance. Review warnings before comparing
metrics; unequal scopes or assumptions are not silently treated as equivalent evidence.

## 6. Compose, extend, and handle failure

- Compose maintained strategies and risk managers using the
  [`trader_standard` tutorial](../../trader_standard/docs/tutorial.md).
- Add a custom implementation by subclassing the relevant core abstraction and inject the instance; there is no
  general-purpose dynamic strategy loader in the runtime.
- Treat missing/stale data, ambiguous broker state, failed recovery, and portfolio mismatch as stop conditions. The
  paper runtime is intentionally fail-closed.
- Never interpret a successful simulation as authorization to submit orders. Live paper startup has separate
  configuration, reconciliation, and operator responsibilities.

Continue with [Backtesting](backtesting.md), [Runtime](runtime.md), and
[Runtime hot path and reconciliation](runtime_hot_path_and_reconciliation.md).
