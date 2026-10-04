# `trader_mcp`

`trader_mcp` is the Model Context Protocol transport and policy adapter for Trader research capabilities. It gives a
role-scoped client a discoverable, JSON-safe route into deterministic `trader_research` services:

```text
role-scoped client -> stdio FastMCP server -> catalogue and policy
                                      -> capability adapter
                                      -> trader_research facade
                                      -> canonical store or bounded provider
```

The server registers FastMCP tools, classifies side effects, attaches domain ownership, enforces environment gates,
and returns stable public envelopes. Concrete Postgres, provider, optional MLflow, optimisation, coding, and maintained
prediction dependencies are selected only by `trader_mcp.runtime.composition`; capability adapters receive the
resolved runtime bundle. Its standalone process emits bounded INFO or DEBUG lifecycle logs to `stderr`; protocol
`stdout` remains exclusively JSON-RPC.

It does not contain research decision logic, agent prompts/graphs, canonical artifact semantics, or live trading
controls. It never imports `trader_agents` or constructs a model client: model calls and code-authoring decisions stay
above the protocol boundary. A successful tool call means the declared operation succeeded; it does not mean the
research conclusion is scientifically sound.

## Product boundary

The package adds four transport concerns around a research service:

1. `catalogue` names a capability, describes its schema, records its owner, and declares its side-effect class.
2. `policy` resolves environment flags and decides which capabilities can be registered in this process.
3. `tools` normalizes MCP arguments and maps service results into the public wire envelope.
4. `runtime` composes concrete dependencies and owns the stdio process lifecycle.

The adapter does not change a service's `ApplicationResult`. It adds `command`, `agent_owner`, `side_effect`, schema
version, timestamps, and MCP result conversion. The calling agent still has to narrow the discovered catalogue by
role, session authority, budgets, and current state.

The server never places live orders, grants raw SQL access, exposes credentials, persists hidden model reasoning, or
turns a disabled capability flag into authority. `trader_research` remains the source of truth for deterministic
operation behavior and canonical artifacts.

## Public surface

- `trader_mcp.protocol`: stable envelopes and conversion to MCP results
- `trader_mcp.catalogue`: tool definitions and environment-derived registration policy
- `trader_mcp.tools`: registration adapters grouped by research capability
- `trader_mcp.runtime`: concrete dependency composition and the stdio server
- `trader_mcp.observability`: protocol-safe lifecycle logging

The package root retains only its intentional result-conversion facade. Removed flat module paths are not aliases for
the responsibility-owned modules.

| Surface | What it answers |
| --- | --- |
| `protocol` | How is a service result represented on the wire? |
| `catalogue` | Which tools exist, who owns them, and which gates apply? |
| `tools` | How are capability-specific inputs normalized and registered? |
| `runtime` | Which concrete stores and providers are composed for this process? |
| `observability` | Which bounded lifecycle events are safe to write to diagnostic stderr? |

## Learning path

1. Follow the [tutorial](docs/tutorial.md) to inspect envelopes and server composition.
2. Read [architecture](docs/architecture.md) for the transport/trust boundary.
3. Use [usage](docs/usage.md) and [configuration](docs/configuration.md) to operate the stdio server.
4. Consult the [tool catalogue](docs/tools.md) and [contracts](docs/contracts.md) before changing registration,
   schemas, side effects, or agent ownership.

For a service-level explanation, follow the linked [`trader_research`](../trader_research/README.md) tutorial. For
model-selected tool use, continue to [`trader_agents`](../trader_agents/README.md) only after understanding the MCP
role and policy boundary.

Agent-specific narrowing and model invocation belong to [`trader_agents`](../trader_agents/README.md). Deterministic
operation behavior belongs to [`trader_research`](../trader_research/README.md).
