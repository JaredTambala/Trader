# Trader Console API Architecture

## Responsibility

`trader_console_api` is Trader's outward-facing HTTP application boundary. It is independently startable and is
intended to grow into the primary human-facing interface for Trader queries and commands. Its current implementation
is deliberately bounded: server-owned scope configuration, pooled PostgreSQL access, database-schema compatibility,
application lifecycle, public context, health responses, market-data discovery, and backtest evidence resources.
The current slice also exposes side-effect-free backtest definition discovery and preflight.

The current health and compatibility slice imports FastAPI, Pydantic, Psycopg, and Psycopg Pool directly and imports
no `trader` package. It does not construct `PostgresEventStore`, run producer migrations, create a broker, execute a
strategy, or reach research, MCP, Agent, or MLflow behavior. This protects the implemented slice without defining a
permanent ban on future API application services.

## Router-service-repository direction

The source tree makes the application flow explicit:

```text
application composition
  -> routers
       -> services
            -> repositories
                 -> console_read
```

- `routers/` owns FastAPI paths, dependency resolution, response status codes, and HTTP headers. It performs no
  database inspection or application orchestration.
- `services/` converts repository evidence and failures into application outcomes, including readiness and startup
  admission.
- `repositories/` owns persistence access, parameterized SQL, catalog normalization, pool protocols, and transaction
  policy.
- `application.py` is only the composition root and lifespan owner. It wires the pool, repository, service, and router.

Catalogue and preflight extend the same direction: `routers.catalogue` resolves typed HTTP contracts,
`services.catalogue` normalizes an allowlisted `trader_standard` profile selection and checks budgets/coverage, and
`repositories.resources` reads aggregate bar coverage. No arbitrary implementation import, definition write, queue
command, or worker starts from this path.

Immutable definitions use the same explicit boundary through `routers.backtest_definitions` →
`services.backtest_definitions` → `repositories.backtest_definitions`. The service requires a successful preflight
before a command transaction inserts a Console-owned JSONB revision. The additive `console_app.backtest_definitions`
table is installed and checked by an operator command; startup does not create it. Scope and IDs are supplied by
composition/server storage, fingerprints are unique per scope, and revision writes append rather than update prior
rows.

## Process and scope boundary

One API process serves one `ConsoleScope` backed by one isolated PostgreSQL database and one bounded connection pool.
Paper, backtest, and synthetic-demo scopes run as separate process deployments. A same-origin gateway may later
present several authorised deployments as one product surface without giving this process a multi-database registry.

`ConsoleScope` separates three concepts:

- the Trader principal, supplied by an authentication gateway when remote access is introduced;
- the external brokerage account represented by a paper database; and
- the safe public scope binding exposed to Console consumers.

Connection details and brokerage provider references are not members of the public scope. The current paper binding
status is `configured`, not verified. Backtest and demo scopes use `not_applicable`.

## Lifecycle and database compatibility

The FastAPI lifespan creates one pool through an injected factory, opens it with a finite timeout, checks database
compatibility, and closes it during shutdown. API startup fails before serving when the compatibility record is missing or
the catalog does not exactly match the expected allowlisted projections.

The API declares the exact producer-owned relation set required by its current resources. This includes OHLCV views,
backtest run/evidence views, lifecycle views, and risk composition/decision views. Additive producer relations remain optional until a resource actually
uses them; the contract impact report identifies which consumer requires an explicit installer run.

The current compatibility repository enters through `repositories.ConsoleDatabase.transaction()`. It acquires one
pooled connection, starts one transaction, applies `SET TRANSACTION READ ONLY`, sets a transaction-local statement
timeout, performs the query, and releases the connection. Repositories never receive client-supplied SQL identifiers.

The Console duplicates the consumer-side catalog expectation intentionally. It does not import the producer migration
module from `trader`; this keeps deployment and schema mutation outside API startup.

Superset is an independent database consumer, not an API downstream service. The API does not proxy Superset, create
Superset datasets, or require Superset-specific contract relations for its own startup. Both consumers may read
producer-owned PostgreSQL views independently, with each consumer declaring only the relations it actually needs.

## Capability growth

Read-only is a property of the currently implemented schema queries, not the API's identity. Future operational
queries and mutations belong in dedicated routers, services, and repositories. Each command path must declare its
authority, validation, idempotency, transaction, and failure semantics; it is not routed through the compatibility
repository or inferred from the current health behavior.

## IAM extension points

Local development supplies `TRADER_CONSOLE_DATABASE_URL`. The app factory accepts a pool factory so later deployment
composition can resolve credentials through a secret manager, managed identity, database proxy, or another IAM
mechanism without changing repositories. It also accepts an `AuthenticationProvider` for future Trader-principal
resolution.

The scaffold stores but does not invoke the authentication provider: local resource routes currently expose configured
evidence without a remote authorization policy. These routes are for local development. It creates
no service principal, role, grant, credential, middleware policy, or application RBAC. Remote authentication and scope
authorization become required when scoped evidence routes are exposed and a deployment threat model exists.

## Health semantics

`/health/live` means only that the HTTP process is responding. `/health/ready` means the configured PostgreSQL database
is reachable and its `console_read` metadata and relation shapes are compatible. Neither endpoint claims broker
connectivity, trading-session health, evidence freshness, broker-account attestation, or production authorization.

Both endpoints return `Cache-Control: no-store`. An incompatible contract blocks startup; loss of compatibility or
database access after startup makes readiness return HTTP 503 while liveness remains HTTP 200.

## First-screen context and contract

`GET /api/context` returns the existing `ConsoleScope` through `routers.context` → `services.ContextService`.
The composition root supplies only the public, immutable scope. This service needs no repository because it returns
configuration, not persisted evidence; database availability continues through the existing health service/repository.
The context remains available after a database outage in an already running process. Startup admission is unchanged:
if the process cannot start, the browser cannot obtain context and must report API unavailability.

The first screen uses the environment (including `synthetic_demo`), optional account display label and binding status,
plus the existing liveness/readiness responses. No account label is invented or required. Readiness failure already has
a typed response with issue codes, so this slice introduces no generic response/problem envelope or domain catalogue.

`trader_console_api.openapi` exports the registered application's schema with fixed non-secret settings and without
running its lifespan. The checked artifact is `contracts/trader-console/openapi.json`; a package contract test rejects
drift. `apps/trader-console` generates TypeScript types from this artifact and consumes them with `openapi-fetch`,
without parallel handwritten models. Its Next.js server rewrites the currently implemented browser resource paths to
the configured API origin. The browser makes independent, cancellable, timeout-bounded requests on load and manual
refresh only.

The dedicated fixture under `examples/console_demo` composes producer-owned core initialization and Console schema
installation outside this package and outside API startup. It owns a separate local PostgreSQL database and volume;
it does not make the API depend on producer or execution packages. Cross-package workflow tests own Docker/process
lifecycle, while browser assertions remain with the app. Neither fixture nor screen qualifies trading readiness.

## Current resource boundary

Backtest definition discovery is exposed through `GET /api/backtests/catalogue`; `POST /api/backtests/preflight`
returns a normalized, content-fingerprinted definition plus coverage and field-level issues. The service uses the
maintained catalogue's explicit strategy and risk resolvers, including risk manager composition metadata and reason
codes, while execution and durable command state remain a later application boundary.

The durable command record extends this boundary through `routers.backtest_executions` →
`services.backtest_executions` → `repositories.backtest_executions`. Submit uses an idempotency key and snapshots the
latest definition revision into `console_app.backtest_executions`; status/list reads are bounded and read-only. Its
explicit installer depends on definition storage, and no worker or producer event write is started by the API.

`trader_console_api.worker.BacktestExecutionWorker` is the separately composed lifecycle seam. It claims queued or
expired unstarted commands, reserves a deterministic run ID, renews leases through coarse progress callbacks, and
records terminal or explicit reconciliation-required outcomes. The injected `BacktestExecutor` owns core imports,
catalogue resolution and internal-broker enforcement; the API process does not construct that adapter.

`routers.resources` currently exposes a general resource surface rather than a permanently named experiment/comparison
API:

- `GET /api/market-data/datasets` discovers available symbol/timeframe/source slices.
- `GET /api/market-data/bars` returns bounded, ordered OHLCV observations for one asset class and time range.
- `GET /api/experiments` derives groups from `console_read.backtest_runs`. Experiment-linked runs retain their
  published experiment ID; standalone `BacktestRunner` runs appear under the stable `standalone_backtests` group.
  Experiment name, description, and tags are not currently published by the Console contract, so the response reports
  stable IDs and makes metadata availability explicit.
- `GET /api/experiments/{experiment_id}/runs` returns run summaries. `compatible_with_run_id` asks the service to mark
  scope-compatible runs; eligibility is a property of discovery, not a persisted comparison object. A missing reference
  run is an explicit exclusion, not an unfiltered comparison request.
- `GET /api/runs/{run_id}` assembles the run summary, performance, exposure, scope, equity and normalized comparison
  curves, trades, positions, assumptions, warnings, provenance, lifecycle events, typed indicator series, signal
  markers, and evidence coverage from bounded producer projections. Equity, performance and exposure are SQL-derived
  from persisted initial state, fills, fees and market bars; a metrics snapshot is optional.
- `GET /api/runs/{run_id}/risk-decisions` reads the same producer-owned risk projection as a separate bounded page.
  Manager, outcome, cycle, and client-order filters remain parameterized and the route checks run existence so an empty
  trace for a known run stays distinct from an unknown run.

The service boundary filters producer-only columns from the repository's `runs.*` selection before validating the
closed run-summary contract. Standalone runs retain their canonical `run_id`; the stable group label only supplies the
selector context required by the current UI.

No endpoint joins by matching timestamps, table names, or inferred identifiers. All cross-projection joins use the
published `run_id`/`experiment_id` keys. User-authored comparison definitions belong to the API's application schema
and never mutate canonical backtest evidence.

### Saved comparison definitions

`routers.comparison_views` → `services.ComparisonViewService` → `repositories.ComparisonViewRepository` owns
preview, create, list, load and revision-checked replacement of named view definitions within one experiment.
The required storage gap is user intent: the producer has runs and evidence, but no name, ordered selection, reference
run or display preferences for a user's saved view. One API-owned `console_app.comparison_views` table stores those
fields, definition version 1, timestamps and a revision. Its compound key binds scope, experiment and generated UUID.
Scope is supplied only by application composition; users of the same local scope share definitions.

The definition holds up to 20 unique run IDs, an explicit reference among them, and allowlisted metric and series keys.
Empty selections require a null reference. Preview and load evaluate current `console_read` evidence; response-only
eligible IDs and exclusions are never saved. A missing fingerprint, missing projection or mismatched fingerprint
excludes a run. Zero and one eligible runs are valid draft states; two or more allow comparison. Saving requires the
experiment and every selected run to exist in that experiment, but allows excluded selections to remain inspectable.
Loading a saved definition preserves IDs even if evidence was subsequently removed.

Only create and replace use `ConsoleDatabase.command_transaction()`: a bounded repeatable-read write transaction.
Validation and the single definition write share that transaction. Other queries retain enforced read-only transactions.
The adapter writes only `console_app.comparison_views`, and uses parameter values for all client content. POST creates
a new UUID each time (not retry-idempotent); PUT requires `expected_revision`, increments it atomically, and returns
409 on stale edits or serialization conflicts. No calculation, evidence copy, compatibility verdict or execution command
is stored. Names need not be unique. List pages return definitions only; detail/preview returns current eligibility.

`python -m trader_console_api.repositories.comparison_schema install` explicitly installs and validates the application
table using the configured DSN; `status` checks its shape without writes. Startup and requests never install it.
Missing or incompatible storage gives comparison routes an actionable 503 while evidence/readiness routes retain their
existing contract. This local API has no per-user authorization; deployment credentials can grant SELECT on
`console_read` and SELECT/INSERT/UPDATE on this one table, with no evidence-table writes or DDL privileges.

The current producer scope projection supplies null fingerprints. These live runs remain excluded with
`missing_scope_fingerprint`; creating a saved definition cannot establish comparability. Producer scope evidence must
be addressed before qualifying a live comparison workspace.

### Contract map

The current resource mapping is deliberately field-oriented:

| Resource | Producer projection | Identity and joins | Nullable/preserve rules | Ordering and bounds |
| --- | --- | --- | --- | --- |
| Dataset/bar | `stock_bars` or `crypto_bars` | `(symbol, timeframe, ts, source)`; no run join | OHLCV, volume, trade count, VWAP, source and ingestion timestamp are returned as published, including nulls | Dataset pages are grouped; bars are `ts ASC`, `limit` 1–50,000 with offset |
| Experiment | `backtest_runs` grouped by `experiment_id` | `experiment_id` groups experiment-linked runs; standalone runs use `standalone_backtests` | `status` values are preserved as an array; metadata availability is explicitly false | Latest `created_at` first, then ID; paged |
| Run | `backtest_runs` plus `backtest_scope` | `experiment_run_id`, `experiment_id`, and canonical `run_id`; scope joins only on `run_id` | Failed, partial and zero-evidence runs remain rows; optional fields remain null | Latest `created_at` first; paged |
| Run evidence | `backtest_performance`, `backtest_comparison_runs`, `backtest_exposure`, `backtest_equity_curve`, `backtest_comparison_curves`, `backtest_trades`, `backtest_positions`, `backtest_assumptions`, `backtest_warnings`, `backtest_provenance`, `backtest_evidence_coverage`, lifecycle views, `indicator_series`, `signal_markers`, `risk_composition`, `risk_summary`, and `risk_decisions` | Every section is selected by canonical `run_id` and retains producer IDs; risk rows retain manager order and composition fingerprint; marker timestamps join recorded cycle IDs; equity joins initial state, fills, fees and bars | Empty sections are empty arrays; scope, benchmark and unsupported accounting fields remain null; legacy risk evidence is explicitly unavailable; optional metrics snapshots are not required; no indicator is recomputed | Run detail sections use `section_limit` 1–5000; risk decisions also expose limit/offset pagination and manager/outcome/cycle/order filters |

Representative producer-side queries are:

```sql
SELECT symbol, timeframe, ts, open, high, low, close, volume, trade_count, vwap, source
FROM console_read.stock_bars
WHERE symbol = $1 AND timeframe = $2 AND ts >= $3 AND ts <= $4
ORDER BY ts ASC
LIMIT $5 OFFSET $6;

SELECT runs.run_id, runs.experiment_id, scope.scope_fingerprint,
       performance.strategy_total_return
FROM console_read.backtest_runs AS runs
LEFT JOIN console_read.backtest_scope AS scope ON scope.run_id = runs.run_id
LEFT JOIN console_read.backtest_performance AS performance ON performance.run_id = runs.run_id
WHERE runs.experiment_id = $1;
```

These examples describe the approved join keys; the repository uses Psycopg `%s` parameters and allowlisted relation
names. Pagination metadata is calculated with a window count and never exposed as a client SQL primitive. The API does
not query `public.experiments` directly because experiment metadata is not currently part of the published Console
contract; exposing names/tags is an explicit producer-contract gap for later work.
