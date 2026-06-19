# Documentation Contexts

Documentation is split by bounded context. Keep new documents in the context that owns the behavior being described.

Use [python_code_quality.md](python_code_quality.md) for cross-codebase Python contributor guidance: readability,
testability, observability, comments, docstrings, error handling, and review expectations.

## Core Platform

Use [core/README.md](core/README.md) for the `trader` and `trader_standard` runtime documentation: market data, event
store, brokers, strategy/risk interfaces, backtesting, live runtime, operations, schema, and tests.

## Research Agents and MCP

Use [research_agents/README.md](research_agents/README.md) for research-agent identities, MCP tool contracts,
LangGraph orchestration, data/research artifacts, and implementation plans for agent-facing tooling.

## History

Use [history/README.md](history/README.md) for historical audits, sprint plans, and superseded task breakdowns. These
documents preserve context but are not the active operating manual.
