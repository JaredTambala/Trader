# Core Platform Documentation

This context is bounded to the core `trader` platform and the optional `trader_standard` implementations.

It covers:

- market-data ingestion, replay, and quality checks
- event-store schema and audit behavior
- strategy and risk interfaces
- broker adapters and portfolio accounting
- backtesting and live runtime orchestration
- operator commands and recovery
- core test expectations

It does not own research-agent identities, MCP tool definitions, LangGraph graphs, or agent artifact contracts. Those
belong in [../research_agents/README.md](../research_agents/README.md).

## Start Here

- [system_architecture.md](system_architecture.md)
- [operations/README.md](operations/README.md)
- [runtime_hot_path_and_reconciliation.md](runtime_hot_path_and_reconciliation.md)
- [schema.md](schema.md)
- [backtesting.md](backtesting.md)
- [testing.md](testing.md)
- [ops.md](ops.md)
