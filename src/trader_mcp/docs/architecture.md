# MCP Architecture

## Position in the system

```text
model-backed role -> role-scoped MCP client -> stdio FastMCP server
                    -> transport validation and policy
                    -> trader_research public service
                    -> canonical store / bounded provider adapter / trader core
```

The stdio process is a separate trust boundary. Agent code sends only tool name plus JSON-safe arguments and receives a
public tool envelope. It cannot import an event store, provider adapter, or research service to bypass this boundary.
Human or JSON lifecycle records are written only to `stderr`, labelled with the assigned agent role and a unique server
process identity. Nothing diagnostic is written to protocol `stdout`.

## Composition

`create_server` receives a resolved `McpEnvironment` and optional dependency overrides for tests or controlled
embedding. It asks `trader_mcp.runtime.composition.compose_runtime_dependencies` for one typed `McpRuntimeDependencies` bundle,
then protocol registration passes those resolved ports, policies, registries, and factories to capability adapters.

`trader_mcp.runtime.composition` is the sole trusted composition module. It may import concrete Postgres stores, provider
adapters, the optional MLflow package, the maintained prediction-mapper catalogue, the Docker-backed Coding Workspace,
and core event-store/configuration builders. These imports select process dependencies; they do not grant a tool new
authority. `server.py`, protocol adapters, and capability modules must not import those concrete surfaces. In
particular, optimization tools receive an injected trial-executor factory rather than constructing the Postgres
executor themselves.

The package may depend on `trader_research` application ports and selected `trader` runtime interfaces, but it must
never import `trader_agents`. MCP adapters do not construct model clients or prompts; model-controlled planning and tool
selection belong to the calling agent process.
The parent agent runtime supplies `TRADER_MCP_LOG_LEVEL`, `TRADER_MCP_LOG_FORMAT`, and
`TRADER_MCP_SERVER_ROLE` independently to each role-scoped child process.

## Source responsibilities

| Area | Owned modules | Responsibility |
| --- | --- | --- |
| `protocol` | `contracts`, `adapters` | Stable public envelopes and MCP result conversion |
| `catalogue` | `definitions`, `policy` | Tool names/descriptions and environment-derived registration gates |
| `tools` | `coordination`, `coding`, `methodology`, `experiments`, `experiment_design`, `ml`, `evaluation`, `adversarial` | Capability-owned request normalization and tool registration |
| `runtime` | `composition`, `server` | Concrete dependency selection, complete registration, and stdio lifecycle |
| `observability` | `console` | Bounded human/JSON lifecycle records on diagnostic `stderr` |

Only `trader_mcp.__init__` remains at the package root. It is the intentional public result-conversion facade, not a
compatibility path for the removed flat modules. Responsibility packages do not re-export those former module paths.

## Verification ownership

Package tests mirror those same responsibilities:

- `tests/trader_mcp/protocol/` owns envelope and MCP-result conversion contracts;
- `tests/trader_mcp/catalogue_policy/` owns environment defaults, registration metadata, and safety gates;
- `tests/trader_mcp/runtime/` owns lazy dependency composition and real stdio process lifecycle;
- `tests/trader_mcp/observability/` owns bounded, labelled, protocol-safe diagnostic output; and
- `tests/trader_mcp/tools/<capability>/` owns request normalization and service-envelope behavior for that capability.

A generic historical filename does not determine ownership. In particular, Data inventory, provider-policy, and
sample-result tests belong to `tools/data`, even when they reach the adapter through a fully composed FastMCP server.
Conversely, a test that calls MCP is not automatically MCP-owned. Evidence graphs spanning optimization, Evaluation,
Adversarial review, or prediction-driven backtesting belong under `tests/cross_package/workflows/`; their asserted
subject is multi-package composition rather than one transport adapter.

## Envelope

Every research result is wrapped as `ToolEnvelope` with `ok`, command, agent owner, side-effect classification, schema
version, generated timestamp, data, artifact references, warnings, and structured errors. The adapter does not reinterpret
the application result. Model-facing clients must treat `ok=false`, unknown fields, and schema mismatch explicitly.

## Side effects

Operations are classified as read-only, local mutating, external research mutating, broker read, or broker mutating.
The active research server registers no live broker mutation surface. Environment flags gate optional mutation, but a
flag alone does not grant an agent access: the agent package independently narrows the discovered catalogue by role,
session authority, budgets, and current state.

## Recovery

Read-only calls can be retried within deadlines. Mutating services own stable operation identities and canonical
prepared/terminal evidence. If transport ends after dispatch, the agent reconciles through a read capability; it does
not assume failure and does not automatically repeat the mutation.
