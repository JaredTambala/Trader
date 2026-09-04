# `trader_mcp`

`trader_mcp` is the Model Context Protocol transport and policy adapter for Trader research capabilities. It registers
FastMCP tools over `trader_research` services, classifies side effects, attaches domain ownership, enforces environment
gates, and returns stable public envelopes. Concrete Postgres, provider, optional MLflow, optimization, coding, and
maintained prediction dependencies are selected only by `trader_mcp.runtime.composition`; capability adapters receive the
resolved runtime bundle. Its standalone process emits bounded INFO or DEBUG lifecycle logs to `stderr`; protocol
`stdout` remains exclusively JSON-RPC.

It does not contain research decision logic, agent prompts/graphs, canonical artifact semantics, or live trading
controls. It never imports `trader_agents` or constructs a model client: model calls and code-authoring decisions stay
above the protocol boundary. A successful tool call means the declared operation succeeded; it does not mean the
research conclusion is scientifically sound.

## Public surface

- `trader_mcp.protocol`: stable envelopes and conversion to MCP results
- `trader_mcp.catalogue`: tool definitions and environment-derived registration policy
- `trader_mcp.tools`: registration adapters grouped by research capability
- `trader_mcp.runtime`: concrete dependency composition and the stdio server
- `trader_mcp.observability`: protocol-safe lifecycle logging

The package root retains only its intentional result-conversion facade. Removed flat module paths are not aliases for
the responsibility-owned modules.

## Learning path

1. Follow the [tutorial](docs/tutorial.md) to inspect envelopes and server composition.
2. Read [architecture](docs/architecture.md) for the transport/trust boundary.
3. Use [usage](docs/usage.md) and [configuration](docs/configuration.md) to operate the stdio server.
4. Consult the [tool catalogue](docs/tools.md) and [contracts](docs/contracts.md) before changing registration,
   schemas, side effects, or agent ownership.

Agent-specific narrowing and model invocation belong to [`trader_agents`](../trader_agents/README.md). Deterministic
operation behavior belongs to [`trader_research`](../trader_research/README.md).
