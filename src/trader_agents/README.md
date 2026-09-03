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
wiring, checkpoint projections, the MCP client/runtime, tracing, and the user-facing session lifecycle. It does not own
research artifacts or tools, direct platform access, provider credentials, code execution, live trading, or scientific
truth.

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
