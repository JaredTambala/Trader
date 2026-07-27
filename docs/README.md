# Documentation Contexts

Documentation is split by bounded context. Keep new documents in the context that owns the behavior being described.

Use [python_code_quality.md](python_code_quality.md) for cross-codebase Python contributor guidance: readability,
testability, observability, comments, docstrings, error handling, and review expectations.

## Core Platform

Use [core/README.md](core/README.md) for the `trader` and `trader_standard` runtime documentation: market data, event
store, brokers, strategy/risk interfaces, backtesting, live runtime, operations, schema, and tests.

## Research Agents and MCP

Start with [research_agents/product_state.md](research_agents/product_state.md) for the current research capability and
qualification baseline. Use [research_agents/README.md](research_agents/README.md) for architecture, agent identities,
MCP catalogs, workflows, operations, detailed contracts, and the active capability roadmap.

## History

Use [history/README.md](history/README.md) for historical audits, sprint plans, and superseded task breakdowns. These
documents preserve context but are not the active operating manual.
