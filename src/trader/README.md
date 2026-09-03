# `trader`

`trader` is the dependency root of the Trader distribution. It owns the platform contracts and runtime primitives for
market data, strategies, risk, brokers, portfolios, event persistence, backtesting, predictions, and operator control.
It does not contain maintained trading ideas, research workflows, MCP transport, agent logic, or MLflow loading.

The package is designed as a Python library. Applications construct a `Strategy` and `RiskManager`, choose concrete
adapters at the boundary, and inject those objects into `BacktestRunner` or `TraderService`. Postgres is the durable
runtime source of truth. In-memory and no-op implementations exist for deterministic tests and deliberately bounded
examples.

## Public surface

The package root exposes the stable, commonly composed contracts:

- configuration: `Config`, `load_yaml_config`, and `build_config`
- event stores: `EventStore`, `PostgresEventStore`, and `NoOpEventStore`
- strategies and risk: `Strategy`, `RiskManager`, `RiskPipeline`, and `RiskContext`
- market data: normalized bar events, sources, ingestion, streaming, backfill, and sample loading
- execution state: `Broker`, portfolio value objects, and deterministic identifiers
- backtesting: `BacktestRunner`, execution assumptions, results, serialization, and exports
- prediction integration: provider-neutral feature, predictor, model-identity, and mapping contracts under
  `trader.predictions`
- live paper runtime: `TraderService` and explicit operator primitives

Concrete first-party indicators, signals, strategies, and risk managers belong to
[`trader_standard`](../trader_standard/README.md). Research agents must reach these capabilities through
[`trader_mcp`](../trader_mcp/README.md), rather than importing core internals.

## Status and safety boundary

Core backtesting and paper-trading primitives are implemented. Live operation is restricted to Alpaca paper trading;
the research and agent packages cannot place orders or clear operational halts. A backtest is evidence about the
declared data and simulation assumptions, not evidence of live profitability.

## Learning path

1. Follow the [tutorial](docs/tutorial.md) to understand composition and reach a first deterministic result.
2. Use the [usage reference](docs/usage.md) for imports, configuration, and lifecycle entry points.
3. Read the [architecture](docs/architecture.md) before changing a boundary or state owner.
4. Continue into the focused guides for [configuration](docs/configuration.md), [market data](docs/market_data.md),
   [strategy and risk](docs/strategy_and_risk.md), [backtesting](docs/backtesting.md), and
   [runtime operation](docs/operations.md).
5. Execute [the backtesting notebook](docs/backtesting_tutorial.ipynb) for an output-free, offline walkthrough.

## Focused reference map

- Persistence and storage: [data model](docs/data_model.md), [schema](docs/schema.md), and
  [event store](docs/event_store.md)
- Execution and lifecycle: [execution](docs/execution.md), [runtime](docs/runtime.md), and
  [hot path and reconciliation](docs/runtime_hot_path_and_reconciliation.md)
- Trading state and evidence: [broker and portfolio](docs/broker_and_portfolio.md) and
  [results and metrics](docs/results_and_metrics.md)
- Contributor verification: [testing](docs/testing.md)

The repository-wide environment, product state, and cross-package flows are indexed in the
[root documentation](../../docs/README.md). Package pages are shipped with the wheel and are the canonical source for
`trader` internals.
