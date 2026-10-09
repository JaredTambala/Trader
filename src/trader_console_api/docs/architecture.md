# Trader Console API Architecture

## Responsibility

`trader_console_api` is Trader's outward-facing HTTP application boundary. It is independently startable and is
intended to grow into the primary human-facing interface for Trader queries and commands. Its current implementation
is deliberately bounded: server-owned scope configuration, pooled PostgreSQL access, database-schema compatibility,
application lifecycle, public context, health responses, market-data discovery, and backtest evidence resources.
The current slice also exposes side-effect-free backtest definition discovery and preflight.

The health, compatibility, and evidence-read slices import FastAPI, Pydantic, Psycopg, and Psycopg Pool directly and
do not construct `PostgresEventStore`, run producer migrations, create a broker, execute a strategy, or reach research,
MCP, Agent, or MLflow behavior. The paper-command adapter is the deliberate exception: it imports only the typed core
operator-control boundary so the running service can consume an already-authorized receipt; it never constructs a
broker or bypasses the runtime.

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
`services.catalogue` requires and qualifies a typed `BacktestDataScopeHandoff`, normalizes an allowlisted
`trader_standard` profile selection and checks budgets/coverage, and `repositories.resources` reads bounded bar
coverage. The composition root injects `SavedDataScopeService` as the server-owned handoff lookup. A mismatch, stale
or unavailable saved scope blocks preflight before coverage is queried; no aggregate coverage result replaces the
selected manifest/quality evidence. The same service validates the typed implementation-lineage projection (version
ID, source digest, validation report, specification identity and authoring decision). A deployment can inject an
`ImplementationLineageResolver` adapter that re-reads research-owned admission evidence; registration and admission
never move into the Console package. No arbitrary implementation import, definition write, queue command, or worker
starts from this path.

Immutable definitions use the same explicit boundary through `routers.backtest_definitions` →
`services.backtest_definitions` → `repositories.backtest_definitions`. The service requires a successful preflight
before a command transaction inserts a Console-owned JSONB revision. The additive `console_app.backtest_definitions`
table is installed and checked by an operator command; startup does not create it. Scope and IDs are supplied by
composition/server storage, fingerprints are unique per scope, and revision writes append rather than update prior
rows. Each JSONB revision includes the complete strategy and risk lineage, so a later review can inspect the exact
admitted source hash and validation blockers that governed submission.

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

## Paper operations read model

`routers.paper_runtime` → `services.paper_runtime` → `repositories.paper_runtime` maps the producer-owned
`console_read` session, bars, positions, orders, fills, and risk-decision projections into one bounded read-only
response. Every subsection carries a `RuntimeEvidence` qualifier and an observation timestamp. The service filters
freshness to the published session scope when one exists and never treats API readiness, configured account labels, or
visible rows as proof of broker identity. Reconciliation attempts and halt state remain explicit `unavailable` until
the producer publishes those projections; the API does not query raw runtime tables or infer them from health.

The route is `GET /api/paper/runtime` and uses the same enforced `READ ONLY` transaction as other Console resources.
Its response is safe to render during partial startup, stale feed, missing session, empty portfolio, bounded fill
history, and database outage cases.

## Paper operator command boundary

`routers.paper_operator_commands` → `services.paper_operator_commands` → `repositories.paper_operator_commands`
owns the separate mutation boundary for paper operation. `POST /api/paper/commands` accepts only a typed command,
an approved immutable `admission_id`, an idempotency key, and an optional human reason. The server binds the request
to its configured paper scope; it never accepts a client scope, account, broker, or database override. Every command
is checked against the projected human paper admission, including approval, expiry, revocation, paper environment,
and any supplied scope/account identity, before it is written to the explicit `paper_operator_commands` ledger.

The request ledger is an audited queue. Duplicate idempotency keys replay the original receipt, while material
replays are rejected. The core runtime consumes queued receipts at safe loop boundaries and applies `start`, `pause`,
`stop`, `set_halt`, `clear_halt`, and `reconcile` through existing runtime primitives. A failed broker reconciliation
is recorded as `ambiguous`; the API never guesses broker state. `GET /api/paper/commands` and
`GET /api/paper/commands/{command_id}` expose bounded receipts for an authenticated human operator. Missing
authentication, agent/MCP principals, missing storage, stale admissions, and scope mismatches fail closed.

Install the additive command ledger explicitly with:

<!-- verified: integration:console tests/trader_console_api/repositories/test_paper_operator_commands_schema.py -->
```bash
TRADER_CONSOLE_DATABASE_URL="$TRADER_CONSOLE_DATABASE_URL" \
  uv run python -m trader_console_api.repositories.paper_operator_commands_schema install
```

The Console never constructs a broker and no MCP or research tool is registered for these commands. The browser
paper-operations workspace provides admission/reason inputs and renders the queued or terminal receipt; it does not
claim that a queued command has already changed runtime state.

## Agent session workspace boundary

`routers.agent_sessions` → `services.AgentSessionService` → `repositories.AgentSessionRepository` exposes the
human-facing projection of one model-backed research session. The repository reads the research-owned
`research_agent_sessions` and `research_agent_decision_receipts` projections and never reads LangGraph checkpoint blobs
or model-provider messages. The service converts the canonical session payload and accepted public receipts into a
closed `AgentSessionProjection`: identity, objective, allowlisted Data scope facts, budget ceilings and use, specialist
progress, exact evidence references, public transition summaries, pending operator input, and terminal decision lineage.
The service verifies the session row against its payload and pins each decision receipt to the same session, admitted
program, and model profile before projecting it. Unknown lifecycle states fail closed. Only coordinator terminal
receipts can close the session; a specialist's terminal branch is still specialist progress.

The projection is deliberately lossy. Prompts, completions, hidden reasoning, raw tool payloads, credentials, source
code, and arbitrary receipt metadata have no response fields and are dropped at the repository/service boundary.
Missing or incompatible producer projections fail closed with `agent_session_storage_unavailable`; the Console never
invents agenda, checkpoint, or completion state from a missing row. The event list is a public decision trajectory,
not a replacement for retained observability evidence.

Each delegation also carries a typed specialist outcome (`running`, `complete`, `partial`, `failed`, `blocked`,
`stale`, or `unavailable`) and, when a receipt identifies an attempt, a bounded handoff containing its owner, digest,
blockers, and artifact references. References include an optional positive revision and an explicit availability state
(`available`, `stale`, `missing`, `unavailable`, or `incompatible`). The browser renders these fields per branch so a
human can distinguish concurrent progress from a failed or stale handoff and can inspect the exact URI, revision, and
source hash that was retained. Missing revision evidence remains visible as unavailable rather than being inferred.

`POST /api/agent-sessions/{session_id}/commands` records an explicit human command intent (`inspect`, `interrupt`,
`resume`, or `cancel`) in `console_app.agent_session_commands`. The endpoint requires an authenticated human principal
who owns the immutable session; agents and MCP identities are rejected. Commands are append-only and idempotent by
scope plus key. A separately composed agent runtime consumes these intents and applies its own checkpoint-backed
`resume`/`cancel` authority; the Console neither invokes LangGraph nor grants model/tool authority. `GET` routes expose
the projection and bounded command receipts with `no-store` headers.
The projected `available_commands` is the service's admission policy for `POST`, so the browser and API use the same
state decision. Without an inspected public runtime state only `inspect` is admitted. Running states admit pause and
cancel; a pending operator boundary admits resume and cancel; blocked and terminal states admit inspect only. The
runtime revalidates the checkpoint when applying an admitted intent, covering state changes after the Console read.

Install the Console command and public-state tables explicitly after the research artifact store has installed its
producer projections:

<!-- verified: integration:console tests/trader_console_api/repositories/test_agent_sessions_schema.py -->
```bash
TRADER_CONSOLE_DATABASE_URL="$TRADER_CONSOLE_DATABASE_URL" \
  uv run python -m trader_console_api.repositories.agent_sessions_schema install
```

The browser workspace at `/agents/{session_id}` renders these typed summaries and asks for a reason or bounded answer
when an interrupt is pending. A separate `trader-agent-session-worker` process claims each intent with a lease, loads
the exact `ResearchSession`, calls the agent-owned runtime command boundary, and stores a fresh `agent_public_state`
snapshot. It marks a lost runtime response `ambiguous` and never replays an accepted side effect automatically. The
Console still labels a queued receipt as an intent until the worker records `completed`.

## Capability growth

Read-only is a property of the currently implemented schema queries, not the API's identity. Future operational
queries and mutations belong in dedicated routers, services, and repositories. Each command path must declare its
authority, validation, idempotency, transaction, and failure semantics; it is not routed through the compatibility
repository or inferred from the current health behavior.

## Human next-decision boundary

The reviewed-run decision path is composed as `routers.next_research_decisions` →
`services.NextResearchDecisionService` → `repositories.NextResearchDecisionRepository`. The Console service accepts
only a human/operator principal for writes, converts the request into the research-owned `NextResearchDecision` value,
and asks the repository to resolve every canonical reference in the same repeatable-read command transaction. The route
run ID must match the cited `backtest_run`; the run's published scope fingerprint is compared with the cited Data
artifact, and review artifacts must be available and belong to that run. Missing, stale, cross-run, or incompatible
evidence produces a typed blocker before either table is written.

The research artifact store remains authoritative. A successful command writes the immutable payload to
`research_artifacts` and the query identity/payload projection to `research_next_decisions` atomically. The repository
does not install that schema; the research package owns its explicit schema statements and the Console only checks the
catalog shape. Revision lineage is contiguous and append-only, with `supersedes_artifact_id` pointing to the prior
revision. The read routes return the latest stream revision or an exact revision and never infer a decision from a
model conclusion. No route starts execution, mutates a broker, admits paper trading, or makes a profitability claim.
When the caller cites a session review, the typed request carries the retained graph digest and exact review-node
revisions into the canonical decision identity. The command requires pinned hashes on the whole evidence chain and
the repository additionally requires matching
canonical session/revision metadata on each cited review record. It does not read the local graph qualification file;
the separate graph composition must verify that digest before submitting the command.

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
accepts an exact saved Data scope handoff and returns a normalized, content-fingerprinted definition plus coverage
and field-level issues. The normalized definition retains the saved scope ID, fingerprint, provider/source policy,
manifest and quality references, and evidence state. The service uses the maintained catalogue's explicit strategy
and risk resolvers, including risk manager composition metadata and reason codes, while execution and durable command
state remain a later application boundary.

The durable command record extends this boundary through `routers.backtest_executions` →
`services.backtest_executions` → `repositories.backtest_executions`. Submit uses an idempotency key and snapshots the
latest definition revision into `console_app.backtest_executions`; status/list reads are bounded and read-only. Its
explicit installer depends on definition storage, and no worker or producer event write is started by the API.

`trader_console_api.worker.BacktestExecutionWorker` is the separately composed lifecycle seam. It claims queued or
expired unstarted commands, reserves a deterministic run ID, renews leases through coarse progress callbacks, and
records terminal or explicit reconciliation-required outcomes. The injected `BacktestExecutor` owns core imports,
catalogue resolution and internal-broker enforcement; the API process does not construct that adapter.
Lease-renewal and terminal-write rejection cannot be reported as success. Once the producer may have written events,
runner or result-persistence failure becomes reconciliation-required rather than an invented clean failure; an expired
reserved run is never replayed by the next worker process.

The completed execution-to-review path keeps that process boundary explicit. The demo/bootstrap owner installs the
core event tables, the producer research-artifact projection, the `console_read` contract, and the three Console
command tables in one fresh database. A worker process reads the immutable definition, translates it into the canonical
core configuration snapshot, runs `BacktestRunner` against the configured PostgreSQL event store, and persists one
typed aggregate metrics snapshot. The standalone `console_read` projections then derive scope identity, assumptions,
performance, fills, warnings, and provenance from the run and its persisted evidence. The API process remains a read
and command boundary: it does not run the worker, migrate schemas, or infer missing producer evidence.

The end-to-end qualification uses a disposable Compose database and separate API, worker, and browser processes. It
replays the same execution idempotency key and restarts the worker to prove one durable run, checks the published review
after completion, and records a human next-decision against canonical artifacts. The same database fixture forces an
expired reserved command and proves a fresh worker marks it reconciliation-required without creating a producer run.
Focused worker tests own partial, failed, ambiguous, and lost-lease outcomes; this fixture does not turn a deterministic local run into a live or
profitability claim.

`routers.resources` currently exposes a general resource surface rather than a permanently named experiment/comparison
API:

- `GET /api/market-data/datasets` discovers available symbol/timeframe/source slices.
- `GET /api/market-data/bars` returns bounded, ordered OHLCV observations for one asset class and time range.
- `GET /api/market-data/evidence` resolves the exact Data manifest/quality pair through the producer-owned
  `console_read.data_scope_evidence` projection. The service returns artifact identity, coverage, findings, warnings,
  provenance, and producer qualification state without recalculating Data quality.
- `POST/GET /api/data-scopes` and `GET/POST /api/data-scopes/{saved_scope_id}` persist and reopen exact Data scope
  handoffs. `SavedDataScopeService` owns fingerprinting and evidence-state transitions; its repository writes only the
  additive `console_app.saved_data_scopes` table and reads the optional producer-owned
  `console_read.data_scope_evidence` projection. Missing, stale, superseded, or unavailable evidence is explicit and
  never replaced with a broader query.
- `POST /api/data-scope-comparisons` reads two or more saved scopes through
  `DataScopeComparisonRepository` → `DataScopeComparisonService`. It compares every unordered pair only after checking
  exact non-source/window dimensions, retains each scope's independent Data evidence, and reports explicit exclusion
  reasons for mismatches or unavailable evidence. It has no preferred-source, bar-merge, or producer-write behavior.
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
- The run detail also returns `review_evidence`, a fixed projection of the producer-owned Evaluation,
  multiple-testing, and Adversarial/robustness artifacts. The producer view joins only exact run references and exposes
  claim scope, data roles, limitations, blockers, identity, digest, and the retained session/graph/node revision when
  one is published. Statuses are explicit (`complete`, `partial`, `negative`, `missing`, `incompatible`, `stale`, or
  `blocked`); the service never calculates statistics or promotes optimisation output to independent confirmation.

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
