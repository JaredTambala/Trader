# Strategy Authoring Workflow

This tutorial runs a small repeatable research loop without the UI or a live broker. It uses the checked-in synthetic
`DEMO` data, a maintained `trader_standard` strategy, Postgres audit tables, and local JSON/CSV artifacts.

## Mental Model

The engine is split into operational components:

- Market data writes bars into Postgres.
- Indicator code computes derived values from bar windows.
- Indicator observations can be audited independently, including structured model outputs.
- Signal code converts indicators and bars into scalar decision values.
- Strategy code reads market context, evaluates signals, and emits candidate orders.
- Risk code approves or rejects those orders.
- The backtest broker simulates deterministic fills with configured cost assumptions.
- The portfolio applies fills to cash and positions.
- The event store persists runs, cycles, orders, fills, positions, metrics, experiments, and provenance.
- Result exports turn the run into files that can be compared or inspected by tools.

## 1. Start Postgres

<!-- verified: integration:postgres tests/test_sample_data.py tests/test_backtest.py -->
```bash
docker compose -f docker-compose.postgres.yml up -d
```

Postgres is the runtime source of truth. DuckDB support remains for tests and local support utilities only.

## 2. Load Sample Data

<!-- verified: integration:postgres tests/test_sample_data.py tests/test_backtest.py -->
```bash
uv run python examples/load_sample_market_data.py
```

The loader reads `examples/data/demo_stock_1min.csv` and writes idempotent `DEMO` stock bars with:

```text
symbol,asset_class,timeframe,ts,open,high,low,close,volume,trade_count,vwap,source
```

Running the loader multiple times should not duplicate bars because market-data tables are unique on
`(symbol, timeframe, ts, source)`.

## 3. Run One Canonical Research Backtest

Register and validate the strategy implementation, create and validate its immutable strategy and backtest
specifications, then call the backtest MCP tool. The run is stored in Postgres as canonical `backtest_run` evidence.
See [Research Workflows](../../../docs/workflows/research.md) for the exact implementation-to-evidence graph.

## 4. Compare Results

Use the MCP comparison and optimization result tools over explicit `research://postgres/...` refs. Comparisons preserve
scope and assumption warnings; parameter searches preserve every trial and selected-specification lineage.

## 5. Try A Tiny Custom Wrapper

Custom indicators, signals, and strategies stay in explicit Python wrappers. That keeps code ownership clear and avoids
a general dynamic code loader.

<!-- verified: doctest -->
```pycon
>>> from datetime import UTC, datetime, timedelta
>>> from typing import Sequence
>>> from trader import Bar, Indicator
>>> class OneBarMomentumIndicator(Indicator):
...     @property
...     def name(self) -> str:
...         return "one_bar_momentum"
...     @property
...     def window(self) -> int:
...         return 2
...     def compute_series(self, bars: Sequence[Bar]) -> Sequence[float]:
...         return [bars[0].close - bars[1].close]
...
>>> now = datetime(2026, 1, 1, tzinfo=UTC)
>>> bars = (
...     Bar(ts=now, open=12.0, high=12.0, low=12.0, close=12.0, volume=1.0, vwap=None, trade_count=None),
...     Bar(ts=now - timedelta(minutes=1), open=10.0, high=10.0, low=10.0, close=10.0, volume=1.0, vwap=None, trade_count=None),
... )
>>> OneBarMomentumIndicator().compute_series(bars)
[2.0]
```

Use this pattern for a pure custom indicator, then compose it behind a signal and strategy that implement the core
contracts. Inject the completed strategy into `BacktestRunner` as shown in the core tutorial.
The current research CLI does not instantiate arbitrary custom indicators from YAML; Python wrappers are the supported
extension path. When indicator persistence is enabled, scalar indicator observations are written to
`indicator_events.value` and structured observations are written to `indicator_events.payload`.

## Modeling Limits

- Backtests use bar data, not tick data or exchange order books.
- Slippage and fees are deterministic assumptions, not venue microstructure simulation.
- The benchmark is frictionless in this phase.
- Research runs do not call Alpaca and do not prove live fill quality.
- Data quality checks report gaps and coverage, but they do not yet enforce a hard gate before every experiment.
