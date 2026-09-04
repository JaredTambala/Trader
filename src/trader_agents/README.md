# `trader_agents`

`trader_agents` is Trader's model-backed multi-agent coordination package. It forms a Research Coordinator and
role-specific specialists as LangGraph state machines over role-scoped MCP tools. Models interpret briefs, select
relevant specialists, propose tool calls, review evidence, and choose bounded next actions; deterministic code validates
every public model output, enforces authority and budgets, executes tools, owns checkpoint transitions, and fails closed.

The implemented vertical slice contains the Research Coordinator, Data Research Agent, and Strategy Engineering Agent.
It is genuine model-directed orchestration, but it is not yet product-qualified: the pinned local LFM profile failed the
material-ambiguity behavioral gate and broader controlled qualification remains intentionally blocked.

At the public boundary this means a model-backed Coordinator agenda, structured specialist returns, and canonical
artifact reads and digest checks before an accepted coordinator decision. The Research Coordinator is the only
user-facing model; specialists are invoked behind its evidence-review boundary.

## Boundaries

This package owns agent programs, model profiles, strict public contracts, role/tool policy, scheduling, LangGraph
wiring, checkpoint projections, the MCP client/runtime, the sink-neutral observability event contract, tracing, and the
user-facing session lifecycle. It does not own research artifacts or tools, direct platform access, provider
credentials, code execution, live trading, or scientific truth.

The runtime emits a versioned public event stream to `stderr`. INFO gives an operator-readable narrative of sessions,
model calls, tool execution, delegations, evidence review, decisions, and terminal outcomes; DEBUG adds schema,
scheduling, checkpoint, and budget detail. Human-readable and JSON-lines formats use the same safe projections and
recursive redaction rules. Final CLI results remain JSON on `stdout`, and the child MCP processes reserve `stdout`
exclusively for JSON-RPC.

## Source layout

The package tree expresses durable control responsibilities rather than development phases:

- `application/` composes the runtime and owns the CLI lifecycle boundary.
- `contracts/` defines public state, decisions, evidence references, and normalized session inputs.
- `coordination/` owns the Coordinator graph and dependency-aware scheduler.
- `specialists/` contains the Data Research and Strategy Engineering model/tool loops.
- `model_runtime/` owns provider clients, admitted profiles, agent programs, and strict structured output.
- `mcp/` owns the code-side catalogue, authorization policy, role-scoped execution, and transport client.
- `checkpointing/` owns bounded LangGraph state plus the PostgreSQL saver adapter.
- `observability/` owns semantic events, public projections, emission, console rendering, and trace sinks.

Only `trader_agents.__init__` is a public convenience facade. The responsibility packages are canonical internal
locations; the removed flat module paths are not compatibility entry points.

## Learning path

1. Follow the [tutorial](docs/tutorial.md) for an offline inspection and the guarded runtime entrypoint.
2. Read [architecture](docs/architecture.md) for the complete multi-agent topology.
3. Read [roles and authority](docs/roles_and_authority.md), [coordinator](docs/coordinator.md), and
   [specialists](docs/specialists.md) to understand who may decide what.
4. Read [contracts](docs/contracts.md), [MCP integration](docs/mcp_integration.md), and
   [model runtime](docs/model_runtime.md) to understand the trust transitions.
5. Read [checkpointing and recovery](docs/checkpointing_and_recovery.md) and
   [qualification](docs/qualification.md) before operating or extending the system.
6. Use [usage](docs/usage.md) for CLI and Python lifecycle calls.

The target designs remain in the repository planning records. This package documentation describes implemented code,
including its current limits, and never treats a delivery checkpoint label as an architectural component.
