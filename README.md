# Trader

Trader is a Postgres-first Python platform for market-data ingestion, strategy/risk execution, historical backtesting,
research evidence, model-facing tools, model-backed research coordination, MLflow inference, and Alpaca paper trading.

It is distributed as one project but organized into packages with explicit dependency and documentation ownership:

| Package | Responsibility | Start here |
| --- | --- | --- |
| `trader` | Core contracts, runtime, persistence, brokers, portfolios, backtesting, and predictions | [`src/trader/README.md`](src/trader/README.md) |
| `trader_standard` | Maintained indicators, signals, strategies, risk managers, and prediction mappings | [`src/trader_standard/README.md`](src/trader_standard/README.md) |
| `trader_research` | Deterministic research services and canonical evidence | [`src/trader_research/README.md`](src/trader_research/README.md) |
| `trader_mcp` | MCP transport, tool registration, policy gates, and envelopes | [`src/trader_mcp/README.md`](src/trader_mcp/README.md) |
| `trader_agents` | Model-backed coordinator/specialist graphs over role-scoped MCP | [`src/trader_agents/README.md`](src/trader_agents/README.md) |
| `trader_mlflow` | Optional MLflow pyfunc inference adapter | [`src/trader_mlflow/README.md`](src/trader_mlflow/README.md) |

## Setup

Python 3.12 and `uv` are required.

<!-- verified: integration:postgres tests/test_package_documentation.py tests/test_postgres_event_store_schema.py -->
```bash
uv sync --dev --group docs
docker compose -f docker-compose.postgres.yml up -d
```

Copy `env.template` to ignored `local.env` for MCP/agent control-plane configuration. Runtime YAML may expand values
from a separate ignored `.env`. See [Environment and local services](docs/environment.md) before enabling provider or
mutation capabilities.

## Choose a learning path

- Core and backtesting: [`trader` tutorial](src/trader/docs/tutorial.md)
- Maintained strategy composition: [`trader_standard` tutorial](src/trader_standard/docs/tutorial.md)
- Research evidence: [`trader_research` tutorial](src/trader_research/docs/tutorial.md)
- MCP tool operation: [`trader_mcp` tutorial](src/trader_mcp/docs/tutorial.md)
- Multi-agent architecture and use: [`trader_agents` tutorial](src/trader_agents/docs/tutorial.md)
- MLflow prediction: [`trader_mlflow` tutorial](src/trader_mlflow/docs/tutorial.md)

The [documentation index](docs/README.md) owns cross-package architecture, current product state, environment, complete
workflows, contributor standards, and history.

## Safety

Live integration is Alpaca paper trading only. Research agents are outside the trading hot path and cannot submit
orders, mutate brokers, clear halts, or perform direct SQL writes. Backtests, optimisation results, citations, and model
recommendations are inspectable research evidence—not authorization to trade and not proof of future performance.

The model-backed agent slice is under development qualification. Its implementation is testable, but the pinned local
model has not passed the complete behavioral gate; see [Product State](docs/product_state.md).

## Quality gates

<!-- verified: integration:repository tests/test_package_documentation.py -->
```bash
uv run ruff check src tests examples run_*.py external_strategy_demo.py
uv run mypy
uv run pytest
```

Postgres, local-model, notebook, and controlled qualification requirements are declared by their owning docs and tests.
