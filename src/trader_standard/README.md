# `trader_standard`

`trader_standard` contains the first-party implementations maintained with Trader: technical indicators, signals,
bar-backed signal generators, risk managers, strategies, policy objects, and model-feature/mapping helpers. It depends
on `trader` contracts and is intentionally outside the core package so the engine never needs to know which trading
ideas are installed.

The package does not own runtime orchestration, event-store schemas, experiment protocols, research artifacts, MCP
schemas, agent tools, or model loading.

## Public surface

The root facade exports common indicators (SMA, EMA, RSI, MACD, Bollinger, volatility, and z-score), their signal
implementations, maintained risk controls, minimal deterministic strategies, the policy-driven long/flat engine, and
builders for trend-following, mean-reversion, pairs, and Bollinger compositions. Prediction feature providers, mappers,
and the prediction-driven strategy live under `trader_standard.predictions` and `trader_standard.strategies`.

## Learning path

1. Follow the [tutorial](docs/tutorial.md) to inspect a policy decision and compose a maintained strategy.
2. Use the [usage reference](docs/usage.md) for supported imports and extension rules.
3. Read the [catalogue](docs/catalogue.md) to select an implementation by responsibility.
4. Read the [architecture](docs/architecture.md) before adding maintained behavior.
5. Follow [strategy authoring](docs/strategy_authoring.md) before implementing a new composition.
6. Use the [strategy composition notebook](docs/strategy_composition_tutorial.ipynb) for an offline executable path.

For engine lifecycle and persistence, use the [`trader` documentation](../trader/README.md). For implementation
catalogue search and candidate admission exposed to agents, use [`trader_research`](../trader_research/README.md) and
[`trader_mcp`](../trader_mcp/README.md).
