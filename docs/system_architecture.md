# Trader System Architecture

Trader is one Python distribution currently containing seven bounded packages and repository-level application
entrypoints. The Console API and its separate frontend now implement a minimal local connection/context journey.

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

The Console architecture contains `trader_console_api` as a seventh bounded package under `src/` and
`apps/trader-console/` as a separate Next.js application. They run as separate processes; the local frontend rewrites
the context, health, market-dataset and market-bars paths to a server-configured origin. A deployment gateway and
remote IAM remain later work.

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
The app factory accepts a pool factory and request-principal provider. The current local scaffold invokes neither
authorization policy nor broker access.

The current contract also publishes typed backtest evidence relations (`backtest_runs`, performance, exposure, equity-curve,
trade, position, assumption, warning, provenance, lifecycle, comparison, `indicator_series`, `signal_markers`, and
ordered risk composition/summary/decision projections). They retain original
experiment/run identifiers for the external observational layer. Consumer SQL does not parse serialized metrics payloads;
the producer contract performs that projection. The Console API maps these views to bounded dataset, bar, experiment/run
discovery and run-detail resources; this does not imply that backtest evidence is trading advice.

The Console also exposes a versioned, allowlisted strategy/risk catalogue and a side-effect-free backtest preflight
surface. Preflight normalizes typed parameters and UTC timestamps, checks published bar coverage, strategy warmup and
resource budgets, and returns a content fingerprint plus field-level warnings/errors. It does not persist a definition
or enqueue execution; those command boundaries are planned separately.

The first Console-owned command boundary is now immutable backtest definition storage. An explicit installer creates
`console_app.backtest_definitions`; API create/revision requests require successful preflight, append JSONB revisions,
and return server-owned IDs plus content fingerprints. The table is separate from producer evidence and from the
future durable execution command record; startup performs no DDL.

The command record now has its own additive `console_app.backtest_executions` table, scoped idempotency key, immutable
definition revision/fingerprint snapshot, and bounded status/list routes. It is deliberately a queue record at this
stage; the worker lifecycle is implemented separately from API startup, while concrete runner invocation and terminal
reconciliation qualification remain a separate implementation step.

The worker lifecycle seam is now implemented as an injected `BacktestExecutor` port: claims are lease-owned,
run identity is deterministic from execution content, heartbeats are coarse and durable, and ambiguous adapter
outcomes become `reconciliation_required`; unreserved lease retries are bounded before the same terminal state is
used. A concrete deployment adapter still has to bind this port to the canonical
`BacktestRunner` and internal broker.

The packaged `trader-console-worker` entrypoint is the local composition root for this adapter. It loads an explicit
core Trader YAML configuration, opens the Console database pool, and polls the durable command repository; API startup
does not own worker threads or runtime configuration.

Contract release 4 adds `backtest_scope`, a typed projection for replay-data identity, benchmark construction, initial
state, execution assumptions, and separate strategy/parameter variant fingerprints. Release 5 adds typed cohort rows and
per-run normalized comparison curves. Comparison consumers must match the scope fingerprint and select variant
dimensions explicitly; legacy snapshots remain readable but unavailable for cohort admission.

Contract release 6 adds producer-declared indicator series and decision-cycle-bound signal markers. Price overlays,
secondary pane groups, units, and rendering kinds are carried as typed evidence; the frontend does not infer them from
names or recompute them from OHLCV bars.

Contract release 9 adds typed risk composition, summary and ordered per-manager decision evidence. The producer records
the configured manager chain and deterministic fingerprint for every run, then records approvals, transformations and
rejections with reason codes and normalized before/after order fields. The Console keeps risk blocks distinct from
broker rejections, no-signal/no-fill outcomes, and legacy runs where risk evidence is unavailable.

Release impact is declared in the producer package and exposed through a non-mutating contract status report. The
Console API keeps consumer compatibility version `1` but declares its complete current relation manifest across producer
releases 1–9; historical databases without the resources required by current API routes fail closed. External database
consumers keep their own relation manifests and validate them during their setup, so a future additive producer release
does not automatically make every consumer migrate.

The frontend owns routes, presentation, accessibility, interaction state, polling, and authenticated cache
partitioning. Its approved baseline is Node 24.20.0 LTS, npm 11.19.0, Next.js 16 App Router, TypeScript, ESLint, and
Turbopack. It owns an app-local `package-lock.json`; CI installs with `npm ci`. The repository does not gain a
JavaScript workspace until more than one JavaScript package requires shared workspace management.

The API owns the checked OpenAPI artifact at `contracts/trader-console/openapi.json`. The frontend owns generated code
under `apps/trader-console/src/generated/`; generated files are not hand-edited. Offline API schema export and artifact
drift tests, generated frontend types and full-stack CI checks are implemented. The first screen's API contract uses
configured `/api/context` plus the existing health responses. The current `/data` workflow additionally consumes
typed OHLCV dataset/bar resources through the same database boundary, without expanding IAM responsibilities; the
frontend renders those bars with a generic ECharts adapter and does not add chart semantics to Trader core.
The existing mutating `trader.web` backtest compatibility API and the Reflex/Plotly optional dependencies remain
independent and are neither imported, wrapped, aliased, replaced, nor removed by the Console.

## Superset Observation Boundary

The Apache Superset evaluation is a separate local application, not another Console package. `examples/superset_demo/`
owns only its Compose topology, pinned image, private local credentials, isolated fixtures, database reader grants, and
Superset asset setup. Its writable metadata PostgreSQL store is separate from the Trader PostgreSQL store. Superset
connects directly to producer-owned PostgreSQL tables and typed `console_read` views through a dedicated database role;
the Superset UI's read-only settings are not treated as authorization.

This is a strict integration boundary:

- Trader core, backtesting, research, MCP, and the Console API do not import Superset, call Superset MCP, emit
  dashboard metadata, or add Superset-specific publication callbacks.
- PostgreSQL tables and producer-owned, allowlisted views are the sole integration contract. A new view is justified by
  a general Trader evidence/query need and must remain useful to database consumers other than Superset; it is not a
  dashboard-shaped escape hatch.
- The Superset demo may seed an isolated database, register datasets, and create charts or dashboards. Those actions are
  demo/deployment setup, not Trader runtime behavior and not a new backtest execution path.
- If a run is absent from a Superset view, the fix belongs in the domain evidence persistence contract, the database
  projection, or the external demo configuration. It must not be fixed by coupling `BacktestRunner` or another Trader
  hot-path component to Superset.

The current demo holds a synthetic fixture and typed `backtest_*` projections, then creates a single-run review
dashboard through the pinned Superset 6.1.0 built-in MCP service. That demonstrates direct database consumption only; it
does not make Superset a source of truth, a Trader service, or a required dependency. Shared run and observation-time
filters are applied through Superset's dashboard REST contract because the pinned MCP dashboard schema does not expose
native filter metadata. The user-reviewed decision is limited adoption: Superset remains useful for broad database
exploration and summary dashboards, but it is not the primary OHLCV/candlestick or backtest-review surface. The stack
remains local and disposable; dedicated workflow work belongs to the separate Console API and frontend.

## Trader Console workflow boundary

The current workflow tranche builds workflow-led visibility in `trader_console_api` and `apps/trader-console`, which
remain separate packages and processes. The API maps producer-owned PostgreSQL projections into bounded HTTP resources
and OpenAPI; the frontend consumes generated types and owns chart interaction and presentation. Console-owned comparison
definitions persist only view intent and are evaluated against producer evidence when read. The `/data` OHLCV
exploration workflow is delivered with generic candlestick/volume rendering, UTC navigation and bounded source-row
windows. The `/comparisons` workspace now builds views within one `experiments.experiment_id` grouping. An experiment groups related `experiment_runs`; each
run points to a canonical `runs.run_id`. Comparison views select compatible runs and never mutate canonical evidence.

The frontend must not infer joins from timestamps or table names, and it must not query PostgreSQL directly. Missing
producer evidence is a contract gap to be resolved at the data/projection boundary. High-cardinality bars are served
through explicit time-window and row limits, with downsampling/windowing treated as a query contract rather than a
chart-side workaround. Superset remains outside this workflow boundary.

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
research agent. Backtest replay loads its requested bars once and passes a typed `RecentBarReader` through the core
strategy boundary; ordinary runtime cycles leave that reader unset and retain event-store history reads. The research
capability path may invoke deterministic backtests but cannot mutate a live/paper broker.
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
