# Trader System Architecture

Trader is one Python distribution currently containing seven bounded packages and repository-level application
entrypoints. The Console API scaffold is implemented; its separate frontend application remains approved but
unimplemented.

## Dependency map

```text
trader_standard -----> trader <----- trader_mlflow
       ^                 ^                 ^
       |                 |                 |
       +------ trader_research ------------+
                       ^
                       |
                   trader_mcp
                       ^
                       |
                  trader_agents

trader --publishes current query schema--> console_read <-- trader_console_api
trader_console_api -. future application commands .-> trader
```

`trader` is the core dependency root. `trader_standard` implements its extension contracts. `trader_research` composes
core and maintained behavior into deterministic evidence-producing services. `trader_mcp` adapts those services to a
policy-aware protocol boundary. `trader_agents` reaches platform capabilities only through MCP. `trader_mlflow` bridges
MLflow pyfunc inference into core prediction contracts and may be composed by research infrastructure. Its adapter
profile is also core-owned, so `trader_mlflow` never imports `trader_research` merely to describe itself.
The implemented `trader_console_api` health and schema-compatibility slice has no Python dependency on `trader`; its
current seam is the producer-owned PostgreSQL schema. Future API capabilities may depend on stable Trader application
interfaces through explicit services rather than direct transport-to-runtime coupling.

The one deliberate outer dependency exception is `trader_mcp.runtime.composition`: it constructs the MCP process's
concrete stores, providers, optional adapters, and maintained implementations. Protocol registration and capability
adapters consume its typed dependency bundle and cannot import those concrete surfaces directly.

## Console Application Boundary

The Console architecture contains `trader_console_api` as a seventh bounded package under `src/` and reserves
`apps/trader-console/` for a separate Next.js application. They run as separate processes behind a same-origin gateway.
The Python API scaffold is current behavior; the frontend is still a target boundary.

`trader_console_api` owns the outward-facing HTTP application boundary: request and response contracts, scope and
authorization policy, application services, repositories, OpenAPI, and lifecycle. It is intended to become the
primary human-facing mechanism for querying and commanding Trader. One process currently serves one server-configured
scope and owns one lifespan-managed bounded connection pool. The implemented health and schema-compatibility slice
reads approved database surfaces directly and imports no Trader execution, research, MCP, Agent, MLflow, or broker
dependency. Tests enforce that current slice without imposing the same dependency or mutation policy on future API
features.

Inside the package, dependency direction is `routers` → `services` → `repositories`. The composition root wires those
layers and owns lifespan resources; routers contain HTTP translation only, services orchestrate outcomes, and
repositories own persistence access and transaction policy. Current compatibility queries use PostgreSQL read-only
transactions. Future mutation paths require dedicated command services, explicit authority, and operation-specific
tests; read-only is not the identity of the package.

The core event-store owner publishes those approved surfaces as versioned ordinary views in the `console_read` schema.
Their relation names remain stable while compatibility metadata carries the version. An explicit producer migration
process owns installation and rollback but does not provision roles, credentials, grants, or database-wide policy.
Runtime and API startup never install or repair this schema. API configuration and the deployment boundary expose the
later IAM integration point; current local schema queries rely on bounded read-only transactions rather than premature RBAC.
The app factory accepts a pool factory and request-principal provider. The current health-only scaffold invokes neither
authorization policy nor broker access.

The frontend owns routes, presentation, accessibility, interaction state, polling, and authenticated cache
partitioning. Its approved baseline is Node 24.20.0 LTS, npm 11.19.0, Next.js 16 App Router, TypeScript, ESLint, and
Turbopack. It owns an app-local `package-lock.json`; CI installs with `npm ci`. The repository does not gain a
JavaScript workspace until more than one JavaScript package requires shared workspace management.

The API owns the checked OpenAPI artifact at `contracts/trader-console/openapi.json`. The frontend owns generated code
under `apps/trader-console/src/generated/`; generated files are not hand-edited, and CI rejects regeneration drift.
The existing mutating `trader.web` backtest compatibility API and the Reflex/Plotly optional dependencies remain
independent and are neither imported, wrapped, aliased, replaced, nor removed by the Console.

## State authorities

| State | Authority |
| --- | --- |
| Runtime bars, runs, cycles, orders, fills, positions, metrics, and halts | Trader Postgres event store and broker truth where explicitly defined |
| Research artifacts, sessions, evidence, and accepted public decisions | canonical research Postgres store |
| In-progress agent execution position | separate LangGraph Postgres checkpoint store |
| Model and agent observation/evaluation projections | MLflow, non-authoritative unless a specific artifact contract says otherwise |
| Candidate source under construction | isolated disposable coding workspace until packaged/admitted |

An agent checkpoint is not research evidence. An MLflow trace is not a canonical decision. A filesystem export is not
the canonical backtest record. Every transition between these stores uses a typed identity and validation boundary.

## Execution paths

The trading hot path is market data to strategy, risk, broker, portfolio, and event evidence. It contains no LLM or
research agent. The research capability path may invoke deterministic backtests but cannot mutate a live/paper broker.
The agent path adds model interpretation and routing above role-scoped MCP tools; it never imports runtime internals.

## Safety and evidence principles

- Normalize configuration, provider payloads, database rows, MCP envelopes, and model JSON at their boundary.
- Keep deterministic decisions separate from effects such as clocks, persistence, network calls, Docker, and models.
- Preserve immutable input/output identity and append-only lineage.
- Fail closed on missing authority, evidence, state reconciliation, model validity, or budget.
- Keep protected evaluation data out of authoring and tuning context.
- Require operator action for scope expansion, approvals, and any future paper-candidate promotion.

For internal topology, use the owning package's architecture page. For what is currently implemented and qualified, use
[Product State](product_state.md).

## Repository And Test Ownership

Source directories follow package ownership, then bounded context or control responsibility, then cohesive component.
Tests follow the package and context whose behavior they assert; execution requirements such as Postgres and local
models are markers rather than directory axes. Genuine dependency seams, system workflows, documentation validation,
and release qualification live under the cross-package test boundary.

The complete placement rules, narrative contract, dependency exceptions, and staged migration protocol are defined in
[Repository and Test Architecture](test_architecture.md).
