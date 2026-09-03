# Trader Core Usage Reference

## Installation and imports

Trader is one Python distribution containing several packages. From a checkout:

<!-- verified: integration:repository tests/test_package_documentation.py -->
```bash
uv sync --dev --group docs
```

Prefer stable package or subpackage exports. The root `trader` facade covers common composition; specialist value
objects remain under focused modules such as `trader.backtest` and `trader.predictions`.

## Configuration

<!-- verified: doctest -->
```pycon
>>> from trader import build_config
>>> config = build_config({"strategy": {"id": "example"}})
>>> (config.strategy_id, config.mode, config.event_store)
('example', 'once', 'postgres')
```

`load_yaml_config(path)` reads a mapping and expands environment placeholders. `build_config(mapping)` normalizes it
into `Config`. Configuration errors should be resolved before constructing adapters. The complete field map and
precedence rules are in [Configuration](configuration.md).

## Composition entry points

| Concern | Contract or entry point | Concrete choices |
| --- | --- | --- |
| Historical execution | `trader.backtest.BacktestRunner` | always uses bounded historical data and the internal simulation broker |
| Paper execution | `trader.TraderService` | `NoOpBroker`, `InternalPaperBroker`, or `AlpacaPaperBroker` according to configuration |
| Strategy | `trader.Strategy` | caller implementation or `trader_standard` |
| Risk | `trader.RiskManager`, `trader.RiskPipeline` | caller implementation or `trader_standard` |
| Persistence | `trader.EventStore` | `PostgresEventStore` or deliberate `NoOpEventStore` |
| Market data | `trader.MarketDataSource` | static/no-op sources or the Alpaca adapter |
| Predictions | contracts under `trader.predictions` | feature provider, predictor, mapper, and prediction-driven standard strategy |

`BacktestRunner` accepts explicit strategy, risk manager, spec, universe, starting cash, configuration snapshot, and
assumptions. `TraderService` owns the live service lifecycle and must perform recovery before normal execution.

## Result handling

Use `serialize_backtest_result` for plain-data transport. Use `export_backtest_result_json`,
`export_backtest_equity_curve_csv`, and `export_backtest_trades_csv` for stable review artifacts. Exports do not replace
the canonical event-store record used by research services.

## Extension rules

- Keep deterministic calculations in value transformations; isolate persistence, clocks, provider calls, and logging
  in adapters or orchestration shells.
- Normalize provider payloads at the boundary.
- Give strategies stable metadata and make state ownership explicit.
- Keep candidate-order creation in strategies and authorization in risk managers.
- Use the broker interface; do not make venue SDK calls from strategy or risk code.
- Test a new implementation directly, then test it through the runtime surface it is intended to use.

## Operational requirements

Postgres-backed paths require the database environment described in the repository
[environment guide](../../../docs/environment.md). Alpaca paths additionally require paper credentials. Core tests and
offline documentation never require live credentials. See [Operations](operations.md) for commands and recovery.
