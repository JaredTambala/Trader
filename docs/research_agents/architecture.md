# Research Agent Architecture

Trader separates core trading runtime code from research tooling, MCP transport, and LangGraph agent orchestration.
Research agents produce deterministic artifacts for inspection and backtesting; they do not control live trading.

## Layer Model

| Package | Responsibility | Must not own |
| --- | --- | --- |
| `trader` | Core runtime platform: market data, event store, brokers, portfolio, strategy/risk interfaces, runtime service, backtesting, metrics, operator primitives. | Research services, MCP schemas, LangGraph agents. |
| `trader_standard` | Maintained implementations of core interfaces: indicators, signals, strategies, and risk managers. | Experiment orchestration, MCP adapters, agent state. |
| `trader_research` | Deterministic research services, tool envelopes, domain schemas, artifact contracts, method packages, strategy/risk candidates, diagnostics, backtests, reports. | MCP transport, live broker control. |
| `trader_mcp` | MCP server, tool registration, JSON adapters, server policy/config metadata, dependency injection into research services. | Research business logic, agent decision state. |
| `trader_agents` | LangGraph identities, state schemas, policy routing, tool allowlists, and handoff wiring over MCP tools. | Direct platform mutation or bypassing MCP when a tool exists. |

## `trader_research` Capability Packages

`trader_research` mirrors the bounded capability style used by the core `trader` package. Stable package-level exports
are canonical public surfaces; broad top-level service modules are not compatibility shims and should not be
reintroduced.

| Package | Responsibility |
| --- | --- |
| `trader_research.data` | Data Agent discovery, inventory, quality, provider context, and explicit loading services. |
| `trader_research.methods` | Quantitative Methods contracts, registry access, fixtures, diagnostics, multiple testing, kernels, and method-package handoffs. |
| `trader_research.strategy_candidates` | Maintained strategy template catalog, source-backed candidate generation, and candidate validation. |
| `trader_research.risk_managers` | Risk-manager template catalog and source-backed candidate generation. |
| `trader_research.backtests` | Data-scoped baseline backtest execution, result lookup, and comparison reports. |
| `trader_research.evaluation` | Evaluation-owned report services over persisted research evidence. |
| `trader_research.knowledge` | Knowledge-source registration, ingestion, indexing, retrieval, method cards, and citation validation. |
| `trader_research.method_implementations` | Python method implementation registration, quarantine generation, and deterministic fixtures. |

## Control Plane And Execution Plane

The MCP server is the control plane. It starts over stdio, lists tools, exposes health/config metadata, declares
side-effect classes, and enforces coarse policy gates. It must be able to start without a valid trader runtime config,
Postgres connection, broker credential, or LLM configuration.

Tool execution is the execution plane. Tool calls lazily build or receive dependencies such as event stores, knowledge
stores, configs, backtest runners, and catalog providers. Execution failures return structured `ToolEnvelope` errors and
must not prevent MCP server startup.

## MCP And LangGraph Responsibilities

MCP is the deterministic tool boundary. MCP tools accept bounded JSON-compatible inputs, call deterministic services,
and return stable envelopes plus artifact refs.

MCP research artifact persistence is DB-first. Mutating method, strategy, risk-manager, portfolio-backtest, and
evaluation tools store canonical records in the configured Postgres research artifact store and return
`research://postgres/{artifact_type}/{artifact_id}` refs. Filesystem exports remain only for legacy direct-service
fallbacks and backtest result artifacts that have not yet moved into structured storage.

LangGraph is the agent identity and orchestration layer. Agent graphs decide which MCP tools are allowed, how state is
retained, how specialist handoffs are routed, and which artifact must be produced. Agent code should call MCP tools
rather than core platform internals when a tool exists.

## Safety Boundaries

- Research-agent tools do not submit broker orders, clear halt state, reconcile broker state, start live trading, or
  expose raw SQL.
- Backtest execution is local-mutating and policy-gated by `TRADER_MCP_ALLOW_BACKTESTS=true`.
- Data loading is local-mutating and policy-gated by `TRADER_MCP_ALLOW_DATA_LOADING=true`.
- Provider-catalog symbol discovery requires explicit provider discovery policy.
- Generated code is source-backed and validation-gated before use in later workflows.
- Supervisor state stores public artifact refs, decisions, blockers, warnings, and tool evidence, not hidden reasoning
  traces or raw scratchpads.

## Artifact Ownership

Agents are separated by the artifacts they own. Ownership lives in `src/trader_research/domain.py` and
`src/trader_research/agents.py`. The Quant Research Supervisor may coordinate workflows and consume specialist outputs,
but it must preserve specialist ownership and must not forge Data, Quantitative Methods, ML, Hypothesis, Evaluation, or
Adversarial artifacts.
