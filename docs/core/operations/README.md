# Operations Documentation

This directory is the current component-oriented operating manual for the core engine. The docs are organized around
the runtime components an operator or platform integrator has to understand. Each component document explains:

- how the component behaves in backtest and live trading modes
- which configuration controls it
- which records or artifacts it produces
- where its current operating limits sit
- which assumptions matter for interpreting its behavior

Cross-cutting properties such as auditability, scalability, and accuracy are described where they arise in each
component's operation. They are not separate component-doc sections.

Existing reference docs remain useful:

- [../system_architecture.md](../system_architecture.md) explains the engine design and source-of-truth model.
- [../runtime_hot_path_and_reconciliation.md](../runtime_hot_path_and_reconciliation.md) explains the live hot path.
- [../backtesting.md](../backtesting.md) is the focused backtesting guide.
- [../first_strategy.md](../first_strategy.md) walks through the first repeatable research experiment.
- [../schema.md](../schema.md) is the authoritative runtime schema reference.
- [../testing.md](../testing.md) describes the required local and CI quality gates.
- [../ops.md](../ops.md) remains the short command/runbook reference.

Research-agent and MCP documentation lives in [../../research_agents/README.md](../../research_agents/README.md).

## Component documents

| Component doc | Runtime component | Use it for |
| --- | --- | --- |
| [runtime_orchestration.md](runtime_orchestration.md) | `BacktestRunner`, `TraderService`, `run_cycle` | How the engine enters backtest, once, loop, and realtime modes. |
| [market_data.md](market_data.md) | Backfill, stream, replay, sample loader, data-quality tooling | How bars enter the system and how stored bars are used. |
| [strategy_and_risk.md](strategy_and_risk.md) | Injected `Strategy`, `RiskManager`, `RiskPipeline`, `trader_standard` | How strategy intent and risk approval work in each mode. |
| [broker_execution_portfolio.md](broker_execution_portfolio.md) | Brokers, fills, order lifecycle, portfolio accounting | How orders become fills and how cash/positions are updated. |
| [event_store_and_audit.md](event_store_and_audit.md) | Postgres event store, schema, notification path | How runtime history is persisted and reconstructed. |
| [results_and_metrics.md](results_and_metrics.md) | Backtest result objects, exports, metrics snapshots | How outputs are serialized, inspected, and compared. |

## Component dependency map

```text
YAML/env config
  -> user wrapper builds Strategy + RiskManager
  -> runtime orchestration selects BacktestRunner or TraderService
  -> market-data component supplies bars
  -> run_cycle builds market context
  -> strategy emits orders
  -> risk filters orders
  -> broker executes or simulates orders
  -> portfolio records cash/positions
  -> event store persists audit trail
  -> metrics/results expose review artifacts
```

## Mode-to-component matrix

| Component | Backtest mode | Live trading mode |
| --- | --- | --- |
| Runtime orchestration | `BacktestRunner` drives deterministic timestamp replay. | `TraderService` drives once, loop, or realtime cycles. |
| Market data | Historical bars are loaded from Postgres into memory and treated as immutable inputs. | Stream/backfill/replay writes bars to Postgres; realtime service reacts to `NOTIFY`. |
| Strategy and risk | Injected Python objects are reused across the run. | Injected Python objects are reused across the service lifetime. |
| Broker/execution/portfolio | Forced deterministic internal broker; in-memory portfolio accounts for adjusted fills and fees. | Broker adapter submits orders; Alpaca-backed mode refreshes portfolio truth from the broker. |
| Event store/audit | Records run, cycle, signal, order, fill, position, and result history. | Records session, cycle, recovery, order, fill, position, and metrics history. |
| Results/metrics | Returns `BacktestResult` and optional JSON/CSV exports. | Writes metrics snapshots and operational audit rows. |

Research and MCP tools are external consumers of these components. They may call core market-data, backtest, event-store,
and operator-read APIs, but their agent identities, tool contracts, and artifacts are documented outside the core
platform context.

## Primary workflows

Reproducible sample backtest:

```bash
docker compose -f docker-compose.postgres.yml up -d
uv run python examples/load_sample_market_data.py
uv run python examples/run_reproducible_backtest.py
```

Injected research backtest:

```bash
uv run python examples/run_injected_backtest.py
uv run python examples/run_library_backtest.py
```

Research implementation, specification, backtest, optimization, and review workflows run through MCP and canonical
Postgres research artifacts. See [Research Agent Operations](../../research_agents/operations.md).

Realtime paper trading:

```bash
docker compose -f docker-compose.postgres.yml up -d
uv run python run_market_data_stream.py configs/example.yaml
uv run python examples/run_injected_trader_service.py
```

Operator status and halt:

```bash
uv run python run_operator.py configs/example.yaml status --json
uv run python run_operator.py configs/example.yaml health --json
uv run python run_operator.py configs/example.yaml halt set --reason "manual safety stop"
uv run python run_operator.py configs/example.yaml halt clear
uv run python run_operator.py configs/example.yaml reconcile --json
```

## Required quality gates

```bash
uv sync --dev
uv run ruff check src tests examples run_*.py external_strategy_demo.py
uv run mypy
uv run pytest
```

Postgres behavior:

```bash
docker compose -f docker-compose.postgres.yml up -d
uv run pytest -m postgres
```
