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

## Purpose and system principles

The MCP package is an adapter boundary, not a second research application. Its job is to make a bounded research
operation discoverable and callable over MCP while preserving the owning service's meaning and evidence rules.

The boundary follows four principles:

- **Transport neutrality:** application services return `ApplicationResult`; only the adapter adds MCP metadata.
- **Policy before dispatch:** environment gates decide what can register, and role/session policy decides what a caller
  may use after discovery.
- **Explicit side effects:** each operation declares read-only, local-mutating, external-research-mutating, broker-read,
  or broker-mutating behavior. A successful response never hides that classification.
- **Protocol hygiene:** JSON-RPC owns `stdout`; bounded lifecycle records use diagnostic `stderr` and contain no
  prompts, hidden reasoning, credentials, source text, or raw payloads.

MCP registration does not authenticate a caller or grant approval. A role-scoped agent must still satisfy its own
allowlist, session, scope, budget, and state policy before dispatch.

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

The dependency bundle is lazy where possible. An absent trader config, provider, or optional runtime becomes an explicit
unavailable capability; the adapter does not silently substitute an in-memory success. Test and controlled-embedding
callers can inject providers through `create_server`, while production composition remains centralized in the runtime
composition module.

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

## Call lifecycle

One tool call crosses these stages:

1. The client initializes the stdio session and discovers the currently registered tools.
2. The client validates its JSON arguments against the published schema and the agent's role policy.
3. FastMCP dispatches to the capability adapter; the adapter normalizes boundary values and selects the declared
   service operation.
4. The deterministic service validates scope, authority, and injected dependencies, then returns an
   `ApplicationResult`.
5. The adapter maps the result to a `ToolEnvelope` and MCP `CallToolResult`, preserving data, artifacts, warnings, and
   structured errors.
6. The client checks both the MCP `isError` flag and envelope `ok`, then re-reads canonical artifact references before
   using them for a later mutation or conclusion.

Discovery is part of the contract. A tool absent from this process's catalogue is unavailable; a tool present in the
server catalogue may still be outside the caller's role or current approval envelope.

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

Capability flags are registration policy, not a bypass around service validation. Enabling backtests does not approve a
data scope, enabling data loading does not approve an arbitrary provider request, and enabling coding workspace does
not permit filesystem escape or unbounded execution.

## Recovery

Read-only calls can be retried within deadlines. Mutating services own stable operation identities and canonical
prepared/terminal evidence. If transport ends after dispatch, the agent reconciles through a read capability; it does
not assume failure and does not automatically repeat the mutation.

The transport process itself is replaceable. A restarted server reconstructs its runtime dependencies from the same
environment and the caller re-discovers the catalogue. Durable truth remains in the research artifact or service store;
stderr logs and MCP envelopes are observations of a call, not the canonical research record.

## Extension process

To add a capability, first implement and test the deterministic behavior in the owning `trader_research` context. Then
define the tool name, description, input normalization, owner, side effect, and capability flag in `catalogue`, add a
thin adapter under `tools`, register it from the runtime, and update [Tools](tools.md) and [Contracts](contracts.md).
Exercise direct service behavior, envelope mapping, registration policy, stdio transport, and role allowlists where the
tool is exposed to an agent. Keep composition-only imports in `runtime.composition`; protocol and capability modules
must not manufacture concrete providers.
