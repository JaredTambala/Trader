# Trader

`Trader` is a **core trading engine** focused on:

- market data ingestion
- importable strategy extension
- risk management
- backtesting
- AI/tool-facing signal discovery workflows
- live paper execution through Alpaca
- runtime orchestration and event persistence

The repository now has a strict package boundary:

- `trader`: core contracts, orchestration, state models, and runtime primitives
- `trader_standard`: maintained first-party indicators, signals, strategies, and concrete risk managers

The active runtime architecture is **Postgres-first**.

## Current Phase 1 Scope

In scope:

- market data stream, backfill, replay, and data quality checks
- direct strategy and risk-manager injection from user code
- composable risk pipeline via injected `RiskManager` objects
- backtesting
- experiment-backed research, comparison, recommendations, and dry-run paper-promotion packets
- trader service / realtime orchestration
- Alpaca paper execution
- metrics snapshots and trading-session tagging

Deferred beyond the current phase:

- the Reflex frontend in `src/ui/`
- the UI backtest workflow
- Apache Superset analytics
- splitting the repo into `trader-core` and `trader-ui`
- deployment packaging and VPS/runtime productization

## Setup

```bash
uv venv
uv sync --dev
```

`uv sync --dev` is the canonical local setup for core development and test work.
UI dependencies remain optional and can be installed separately with:

```bash
uv sync --group ui
```

Local MCP and research-agent environment defaults are templated in [env.template](env.template). Create your ignored
local copy with:

```bash
cp env.template local.env
```

See [README_ENV.md](README_ENV.md) for the `local.env`, Data Agent LLM, OpenRouter/Ollama, and runtime `.env` setup
details.

For local Postgres development:

```bash
docker compose -f docker-compose.postgres.yml up -d
```

## Getting Started

Use this flow if you want to get the engine running from scratch and kick off trading with a strategy.

1. Create and populate `.env`.
   Required values usually include:
   - `PG_HOST`, `PG_PORT`, `PG_DB`, `PG_USER`, `PG_PASSWORD`
   - `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_BASE_URL`
2. Start Postgres.
   ```bash
   docker compose -f docker-compose.postgres.yml up -d
   ```
3. Review [configs/example.yaml](configs/example.yaml).
   The important sections are:
   - `market_data`: what symbols and asset class you trade
   - `broker`: how orders are executed
   - `trader_service`: how the live engine runs
   - `strategy`: strategy metadata and strategy-specific settings
4. Ingest data.
   For a historical seed:
   ```bash
   uv run python run_market_data_backfill.py configs/example.yaml
   ```
   For live bars:
   ```bash
   uv run python run_market_data_stream.py configs/example.yaml
   ```
5. Build or choose a strategy and risk pipeline in Python and inject them into the runtime.
   The reference implementation is [examples/run_injected_trader_service.py](examples/run_injected_trader_service.py), which constructs a `trader_standard.ToggleUnitStrategy`, builds a risk manager, and starts `TraderService`.
   If you want the maintained standard trend-following, mean-reversion, or Bollinger Band compositions, use
   [examples/run_library_trader_service.py](examples/run_library_trader_service.py).
6. Start trading from your wrapper script.
   ```bash
   uv run python examples/run_injected_trader_service.py
   ```
7. Inspect the runtime from the operator CLI.
   ```bash
   uv run python run_operator.py configs/example.yaml status --json
   uv run python run_operator.py configs/example.yaml health --json
   ```

Typical workflow:
- run a backfill first so the strategy has bar history
- start the market-data stream in one terminal
- start your injected trader-service wrapper in another terminal
- let `TraderService` react to incoming bars and execute the injected strategy

If you want a minimal example of external strategy authoring, use [external_strategy_demo.py](external_strategy_demo.py).

## Documentation Map

Start with [docs/README.md](docs/README.md) for the bounded documentation contexts.

Core platform documentation for `trader` and `trader_standard`:

- [docs/core/operations/README.md](docs/core/operations/README.md)
- [docs/core/operations/runtime_orchestration.md](docs/core/operations/runtime_orchestration.md)
- [docs/core/operations/market_data.md](docs/core/operations/market_data.md)
- [docs/core/operations/strategy_and_risk.md](docs/core/operations/strategy_and_risk.md)
- [docs/core/operations/broker_execution_portfolio.md](docs/core/operations/broker_execution_portfolio.md)
- [docs/core/operations/event_store_and_audit.md](docs/core/operations/event_store_and_audit.md)
- [docs/core/operations/results_and_metrics.md](docs/core/operations/results_and_metrics.md)
- [docs/core/first_strategy.md](docs/core/first_strategy.md)
- [docs/core/system_architecture.md](docs/core/system_architecture.md)
- [docs/core/runtime_hot_path_and_reconciliation.md](docs/core/runtime_hot_path_and_reconciliation.md)
- [docs/core/schema.md](docs/core/schema.md)
- [docs/core/backtesting.md](docs/core/backtesting.md)
- [docs/core/testing.md](docs/core/testing.md)

Research-agent, MCP, and LangGraph documentation:

- [docs/research_agents/README.md](docs/research_agents/README.md)
- [docs/research_agents/architecture.md](docs/research_agents/architecture.md)
- [docs/research_agents/agents.md](docs/research_agents/agents.md)
- [docs/research_agents/mcp_tools.md](docs/research_agents/mcp_tools.md)
- [docs/research_agents/workflows.md](docs/research_agents/workflows.md)
- [docs/research_agents/operations.md](docs/research_agents/operations.md)
- [docs/research_agents/tool_contracts.md](docs/research_agents/tool_contracts.md)

## Live Runtime Safety

For Alpaca-backed live trading, the runtime is intentionally fail-closed.

- `trader_service.portfolio_source: alpaca` makes startup reset local `position_snapshots` from the broker account before trading begins.
- After the reset, startup validates that broker positions belong to the configured trading universe.
- If Alpaca contains positions outside the configured symbols or asset class, the service aborts rather than trading against an ambiguous account state.
- `trader_service.order_reconciliation_interval_seconds` enables periodic append-only open-order reconciliation in loop/realtime service modes.
- The global halt flag lives in Postgres `config_kv` and is enforced by `run_cycle` before strategy execution.
- During live execution, order lifecycle logs now show `created`, `validated`, `submitted`, and broker-response states, and risk rejections are logged explicitly.

Equivalent Alpaca crypto forms such as `BTC/USD`, `BTCUSD`, and enum-style asset classes returned by the SDK are normalized into the runtime’s canonical symbol and asset-class model.

Operator commands:

```bash
uv run python run_operator.py configs/example.yaml status --json
uv run python run_operator.py configs/example.yaml health --json
uv run python run_operator.py configs/example.yaml positions --json
uv run python run_operator.py configs/example.yaml open-orders --json
uv run python run_operator.py configs/example.yaml halt set --reason "manual safety stop"
uv run python run_operator.py configs/example.yaml halt clear
uv run python run_operator.py configs/example.yaml reconcile --json
```

Read-only operator commands are event-store-first and do not construct a broker. `reconcile` is explicit and appends
local order/fill audit events based on broker state.

## AI-Toolable Research

The supported research control plane is the Postgres-first MCP server. Data, implementation, specification, backtest,
optimization, knowledge, Evaluation, and Adversarial tools return canonical `research://postgres/...` references and do
not control live trading. The old filesystem discovery, recommendation, promotion, and event-store experiment command
wrappers have been retired.

See [docs/research_agents/tool_contracts.md](docs/research_agents/tool_contracts.md) for the stable envelope schema and
side-effect classes, and [docs/research_agents/workflows.md](docs/research_agents/workflows.md) for the current
research-agent workflow model.

## Order Recovery

Use [run_operator.py](run_operator.py) as the primary operator tool for status, health, halt, and explicit
reconciliation. [run_order_recovery.py](run_order_recovery.py) remains available for focused recovery reports and
local clean-start operations.

```bash
uv run python run_operator.py configs/example.yaml reconcile --json
uv run python run_order_recovery.py configs/example.yaml report
uv run python run_order_recovery.py configs/example.yaml reconcile
uv run python run_order_recovery.py configs/example.yaml clean-start
```

- `report` inspects local open orders and broker open orders without mutating anything.
- `reconcile` reads broker state and repairs local `order_events` so stale local-open orders do not block trading.
- `clean-start` closes local open orders in the configured universe only. It does not cancel broker orders and it is not a trading entrypoint.

Neither recovery command starts trading. The canonical live entrypoint remains [examples/run_injected_trader_service.py](examples/run_injected_trader_service.py).

## Configuration

All runtime entrypoints take a single YAML config file.

Use `configs/example.yaml` as the starting point.

The YAML supports environment variable expansion such as `${ALPACA_API_KEY}` and `${PG_HOST}`. Load `.env` into the shell or rely on the top-level entrypoints, which call `load_dotenv(".env")`.

MCP server configuration is intentionally separate from this runtime environment. Keep MCP control-plane settings in
`local.env`; keep trader execution-plane secrets and YAML substitutions in `.env`. See [README_ENV.md](README_ENV.md)
for the boundary contract.

### Minimal runtime shape

```yaml
runtime:
  mode: once

strategy:
  id: toggle
  timeframe: 1Min
  toggle:
    order_qty: 0.01

broker:
  type: alpaca
  time_in_force: gtc

market_data:
  source: alpaca
  asset_class: crypto
  symbols:
    - BTC/USD

database:
  event_store: postgres
  pg:
    host: ${PG_HOST}
    port: ${PG_PORT}
    db: ${PG_DB}
    user: ${PG_USER}
    password: ${PG_PASSWORD}
```

### Strategy and risk injection

The supported integration model is normal Python imports and direct object injection.

```python
from trader.config import build_config, load_yaml_config
from trader.risk import RiskPipeline
from trader_standard.risk import MaxOrdersPerRunRiskManager
from trader_standard.strategies import ToggleUnitStrategy
from trader.runtime.service import TraderService

config_data = load_yaml_config("configs/example.yaml")
config = build_config(config_data)

strategy = ToggleUnitStrategy(
    symbols=config.market_data_symbols,
    order_qty=config.toggle_order_qty,
)
risk_manager = RiskPipeline(
    [
        MaxOrdersPerRunRiskManager(limit=10),
    ]
)

service = TraderService(
    config=config,
    strategy=strategy,
    risk_manager=risk_manager,
    config_snapshot=config_data,
)
service.run()
```

Reference examples:

```bash
uv run python external_strategy_demo.py
uv run python examples/run_injected_trader_service.py
uv run python examples/run_injected_backtest.py
uv run python examples/run_library_trader_service.py
uv run python examples/run_library_backtest.py
```

### Standard implementation library

The maintained `trader_standard` package ships with a reusable long/flat strategy engine and standard compositions for:

- trend-following
- mean-reversion
- Bollinger Band re-entry

These are still composed in user-owned Python wrappers, not instantiated by the runtime itself.

```python
from trader_standard.strategies import FixedStopLossPolicy, build_trend_following_strategy

strategy = build_trend_following_strategy(
    symbols=config.market_data_symbols,
    asset_class=config.market_data_asset_class,
    timeframe=config.strategy_timeframe,
    target_qty_when_long=1.0,
    stop_policy=FixedStopLossPolicy(stop_loss_pct=0.03),
    ema_fast_period=12,
    ema_slow_period=26,
    macd_fast_period=12,
    macd_slow_period=26,
    macd_signal_period=9,
)
```

Standard implementation helpers live under:

- `trader_standard.indicators`
- `trader_standard.signals`
- `trader_standard.strategies`
- `trader_standard.risk`

The example wrappers in `examples/run_library_backtest.py` and `examples/run_library_trader_service.py`
show how to build these from passive YAML input while keeping strategy ownership in user code.
Those wrappers read [configs/library_example.yaml](configs/library_example.yaml).

### Risk composition

```yaml
risk:
  max_orders_per_run: 10
  max_gross_usd: 250000
  max_pos_usd_per_symbol: 100000
  max_open_buy_orders_per_symbol: 1
```

If you keep risk values in YAML, treat them as passive input for your wrapper script. The library does not build risk managers from config.

```python
from trader.risk import RiskPipeline
from trader_standard.risk import (
    MaxGrossExposureRiskManager,
    MaxOrdersPerRunRiskManager,
    MaxPositionUsdPerSymbolRiskManager,
    OpenBuyOrderLimitRiskManager,
)

risk_cfg = config_data.get("risk", {})
risk_manager = RiskPipeline(
    [
        MaxOrdersPerRunRiskManager(limit=int(risk_cfg["max_orders_per_run"])),
        MaxGrossExposureRiskManager(limit_usd=float(risk_cfg["max_gross_usd"])),
        MaxPositionUsdPerSymbolRiskManager(limit_usd=float(risk_cfg["max_pos_usd_per_symbol"])),
        OpenBuyOrderLimitRiskManager(
            max_open_buy_orders_per_symbol=int(risk_cfg["max_open_buy_orders_per_symbol"])
        ),
    ]
)
```

You can also ignore YAML completely and instantiate custom `RiskManager` subclasses directly in Python.

### Broker configuration

```yaml
broker:
  type: alpaca  # noop|internal|alpaca
  time_in_force: gtc
  internal:
    reject_probability: 0.0
    fill_delay_ms_mean: 0
    fill_delay_ms_stddev: 0
    fill_qty_fraction_mean: 1.0
    fill_qty_fraction_stddev: 0.0
    rng_seed: null
```

For Alpaca paper trading:

```yaml
alpaca:
  api_key: ${ALPACA_API_KEY}
  secret_key: ${ALPACA_SECRET_KEY}
  base_url: ${ALPACA_BASE_URL}
  data_base_url: https://data.alpaca.markets
```

Crypto orders require a valid crypto time-in-force such as `gtc`, `ioc`, or `fok`.

## Core Runtime Commands

### Stream live market data

```bash
uv run python run_market_data_stream.py configs/example.yaml
```

### Backfill historical bars

```bash
uv run python run_market_data_backfill.py configs/example.yaml
```

### Run the trader service from a user-owned wrapper

```bash
uv run python examples/run_injected_trader_service.py
```

`runtime.mode` supports `once`, `loop`, and realtime variants such as `real_time`.

### Run a backtest from a user-owned wrapper

```bash
uv run python examples/run_injected_backtest.py
uv run python examples/run_library_backtest.py
```

Useful `backtest` config fields:

- `start`
- `end`
- `timeframe`
- `symbols`
- `asset_class`
- `initial_cash`
- `initial_positions`
- `max_runs`
- `log_cycle_details`
- `assumptions`

Backtest assumptions are optional and stay at the wrapper/backtest layer rather than the global runtime config. They
can declare deterministic fees, slippage, latency metadata, and data fallback behavior.

### Run the reproducible sample backtest workflow

```bash
docker compose -f docker-compose.postgres.yml up -d
uv run python examples/load_sample_market_data.py
uv run python examples/run_reproducible_backtest.py
```

This loads the checked-in synthetic `DEMO` 1-minute dataset and exports stable artifacts under
`artifacts/reproducible_backtest/`.

### Run canonical research through MCP

Research backtests and optimization runs are created from registered implementation versions and immutable
specifications. See [docs/research_agents/workflows.md](docs/research_agents/workflows.md) for the execution graph and
[docs/research_agents/operations.md](docs/research_agents/operations.md) for policy gates and Postgres inspection.

### Replay stored bars through the realtime path

```bash
uv run python -m trader.market_data_replay configs/example.yaml
```

### Run data-quality checks

```bash
uv run python run_data_quality.py configs/example.yaml
uv run python run_data_quality.py configs/example.yaml --output-json artifacts/data_quality/example.json
```

## Operational Notes

- The injected wrapper scripts under `examples/` show the preferred Phase 1 runtime pattern.
- `run_cycle`, `TraderService`, and `BacktestRunner` are library primitives intended to be called from user-owned wrapper scripts.
- The streamer, replay tooling, backfill, and data-quality scripts remain normal infrastructure entrypoints.
- The runtime is event-sourced and writes to Postgres.
- Metrics snapshots can be enabled through:

```yaml
metrics:
  enable_snapshots: true
  interval_seconds: 30
  window_seconds: null
```

- For live Alpaca paper trading, `trader_service.portfolio_source: alpaca` keeps portfolio state aligned with the broker-side account.
- `trader_service.startup_recovery_mode` supports `resume` and `fail_closed`.
- `run_order_recovery.py clean-start` is local event-store cleanup only; it does not cancel broker orders.

## Tests

Run the full suite:

```bash
uv run pytest -q
```

Run the Postgres integration subset against a local Docker-backed Postgres instance:

```bash
docker compose -f docker-compose.postgres.yml up -d
uv run python -m tests.support.postgres_verification provision --reset
uv run python -m tests.support.postgres_verification begin --phase 57J
uv run pytest -m postgres
uv run python -m tests.support.postgres_verification end --phase 57J --outcome passed
```

First configure the explicit `PG_ADMIN_*`, `PG_OPERATOR_*`, `PG_TEST_*`, and `PG_OPTUNA_TEST_*` connection profiles,
`PG_TEST_LOCALE`, and the verification namespace variables documented in
[research-agent operations](docs/research_agents/operations.md#controlled-verification-procedure). Postgres tests
truncate fixture tables and therefore require a provisioned `PG_TEST_DB` ending in `_test` or `_testing`. They never
read the legacy/operator `PG_HOST`, `PG_USER`, or `PG_PASSWORD` variables as test credentials.

Targeted examples:

```bash
uv run pytest tests/test_alpaca_broker.py
uv run pytest tests/test_risk_manager.py
uv run pytest tests/test_backtest.py
uv run ruff check src tests examples run_*.py external_strategy_demo.py
uv run mypy
```

## Deferred Interface Work

The repo still contains deferred interface/platform work, but it is not part of the active Phase 1 roadmap:

- Reflex UI in `src/ui/`
- UI backtest workflow as the primary research/control surface
- API/UI expansion for non-default backtest assumptions and richer strategy selection
- UI plans in `plans/task_0_8b_breakdown.md` and `plans/task_0_8g_reflex_ui_refactor_plan.md`

These remain in the repo for later phases and historical continuity, not as current-phase commitments.

## Runtime contract

- Strategies and risk managers are instantiated in user code and injected directly.
- YAML config files describe runtime settings, not code-loading instructions.
- `python -m trader.cycle`, `python -m trader.backtest`, and `run_trader_service.py` are not supported execution paths for strategy-bearing workflows.
