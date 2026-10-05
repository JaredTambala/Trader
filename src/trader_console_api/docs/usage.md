# Trader Console API Usage Reference

## Entry point

`trader-console-api [--host HOST] [--port PORT]` launches Uvicorn with the `create_app` factory. It binds to
`127.0.0.1:8001` by default. Binding remotely does not add authentication or authorization.

## Required environment

| Variable | Meaning |
| --- | --- |
| `TRADER_CONSOLE_DATABASE_URL` | Local DSN baseline consumed by the default pool factory. |
| `TRADER_CONSOLE_SCOPE_ID` | Stable, server-owned scope identifier. |
| `TRADER_CONSOLE_SCOPE_ENVIRONMENT` | One of `paper`, `backtest`, or `synthetic_demo`. |

Optional values are `TRADER_CONSOLE_SCOPE_DISPLAY_NAME`, `TRADER_CONSOLE_BROKER_ACCOUNT_DISPLAY_LABEL`, and
`TRADER_CONSOLE_PRESENTATION_TIMEZONE`. The brokerage label applies only to paper scopes and is safe display text, not
a provider account reference.

Pool and query bounds may be adjusted server-side with:

| Variable | Default | Accepted bound |
| --- | ---: | ---: |
| `TRADER_CONSOLE_POOL_MIN_SIZE` | 1 | 1–16 |
| `TRADER_CONSOLE_POOL_MAX_SIZE` | 4 | 1–32 and not below the minimum |
| `TRADER_CONSOLE_POOL_TIMEOUT_SECONDS` | 3 | greater than 0, at most 60 |
| `TRADER_CONSOLE_POOL_OPEN_TIMEOUT_SECONDS` | 10 | greater than 0, at most 120 |
| `TRADER_CONSOLE_POOL_CLOSE_TIMEOUT_SECONDS` | 5 | greater than 0, at most 60 |
| `TRADER_CONSOLE_STATEMENT_TIMEOUT_MS` | 10000 | 100–60000 |

## Application factory

`create_app(settings=None, *, pool_factory=create_connection_pool, authentication_provider=None)` returns the FastAPI
application. Passing settings avoids process-environment access in tests and alternate composition roots. A custom pool
factory owns later connection authentication; an `AuthenticationProvider` will supply Trader principals to future
scoped routes. The current health and public-context routes intentionally do not invoke it and are local-development
surfaces, not authenticated remote deployment.

The composition root wires routers to application services and repositories. HTTP code does not execute SQL, and
repository code does not construct HTTP responses.

## First-screen contract

The initial journey identifies configured context and connection availability; it does not show sessions, positions
or charts. Fetch `GET /api/context` for the existing `ConsoleScope`, and use the health endpoints below for availability.
All three responses use `Cache-Control: no-store`; context performs no database or broker query.

| Screen value | Response field or condition | Meaning |
| --- | --- | --- |
| Environment / synthetic indicator | `ConsoleScope.environment` | `paper`, `backtest`, or explicitly `synthetic_demo`. |
| Account | `broker_account_display_label`, `broker_account_binding` | Optional configured display text, never verified broker identity. A missing paper label stays unspecified; non-paper binding is not applicable. |
| API available | Successful response, or `/health/live` | Only process reachability. A network failure has no API JSON body. |
| Database schema available | `/health/ready` HTTP 200 | The configured database is reachable and compatible, not that trading is healthy. |
| Database unavailable/incompatible | `/health/ready` HTTP 503 with `issues` | Keep context visible and show the reason; Retry repeats the check. |

The context response includes `scope_id`, `display_name`, `environment`, `data_source_kind`, `isolation_kind`,
`broker_account_display_label`, `broker_account_binding`, and `presentation_timezone`. It contains no connection URL,
provider account reference, credentials or Trader principal. The environment itself is the synthetic indicator; there
is no redundant boolean. Configuration fields are not broker attestation.

For example, a synthetic context has `environment: "synthetic_demo"`, `broker_account_display_label: null` and
`broker_account_binding: "not_applicable"`. A database outage returns the existing `ReadinessResponse`:

```json
{"status":"unavailable","scope_id":"demo","contract_version":null,"issues":["database_unavailable"]}
```

Incompatibility uses the same HTTP 503 shape with compatibility issue codes such as `database_schema_too_old`.
The client should retain and display an unknown issue code safely rather than treat it as success. Loading and network
errors are client states; they are not fabricated API responses. If startup fails, no context is available to fetch.

## OpenAPI export

Run from the repository root. Neither command requires a database, environment settings or external credentials.
The second command fails without modifying the artifact if it is missing or stale; the package test runs this drift
assertion as part of the normal test suite. The [frontend](../../../apps/trader-console/README.md) owns TypeScript
generation and its non-mutating drift check against this artifact.

<!-- verified: integration:console tests/trader_console_api/contracts/test_openapi.py -->
```bash
uv run python -m trader_console_api.openapi --output contracts/trader-console/openapi.json
uv run python -m trader_console_api.openapi --output contracts/trader-console/openapi.json --check
```

## Health endpoints

| Endpoint | Success | Failure meaning |
| --- | --- | --- |
| `GET /health/live` | HTTP 200, process is responding | No database or trading check is performed. |
| `GET /health/ready` | HTTP 200, database schema is reachable and compatible | HTTP 503 for database loss or incompatible metadata/catalog after startup. |

Responses are non-cacheable. No endpoint accepts a DSN, schema, table name, scope override, account mapping,
environment, or capability from the client.

## Startup behavior

The lifespan creates and opens exactly one bounded pool, then inspects the compatibility row and exact stable relation
columns in one short read-only transaction. Missing metadata, an older incompatible contract, or column drift aborts
startup. The API never installs or repairs `console_read`.

That transaction policy belongs to the currently implemented query resources. It does not define the whole API as
read-only; future command services will have their own explicit authority and transaction contracts.

## Paper operator commands

The paper-operations workspace submits only commands that carry an approved immutable paper-candidate admission. The
request is authenticated through the injected `AuthenticationProvider`; the resulting principal must use the explicit
`human:` or `operator:` namespace. Agents, MCP identities, unauthenticated requests, non-paper scopes, missing or
expired admissions, revoked candidates, and broker/account or scope mismatches fail closed.

`POST /api/paper/commands` accepts `command` (`start`, `pause`, `stop`, `set_halt`, `clear_halt`, or `reconcile`),
`admission_id`, `idempotency_key`, and an optional `reason`. The response is an audited receipt. A repeated key with
the same request returns the original receipt; a material replay returns HTTP 409. Commands are initially
`requested`, then the running core service records `completed`, `failed`, or `ambiguous` as it consumes the queue.
`ambiguous` is reserved for reconciliation outcomes that cannot establish remote broker state. The bounded audit
routes are `GET /api/paper/commands` and `GET /api/paper/commands/{command_id}`.

Install the command ledger explicitly before using these routes:

<!-- verified: integration:console tests/trader_console_api/repositories/test_paper_operator_commands_schema.py -->
```bash
TRADER_CONSOLE_DATABASE_URL="$TRADER_CONSOLE_DATABASE_URL" \
  uv run python -m trader_console_api.repositories.paper_operator_commands_schema install
```

## Data resources

The current resource slice is deliberately bounded and consumes only the producer-owned `console_read` views. Every
collection returns `items` plus `page {limit, offset, total, has_more}`. General collection limits are server-validated
(1–5000); the market-data bars endpoint accepts up to 50,000 rows per window. All resource responses are
`Cache-Control: no-store`.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/market-data/datasets?limit=&offset=` | Discover available stock/crypto symbol, timeframe and source slices. The response also carries `discovery` capability evidence. |
| `GET /api/market-data/bars?asset_class=&symbol=&timeframe=&source=&start=&end=&limit=&offset=` | Return ordered OHLCV bars; `start` and `end` are ISO timestamps. |
| `GET /api/market-data/evidence?asset_class=&symbols=&timeframe=&interval=&bar_type=&provider=&source_policy=&start=&end=` | Resolve Data-owned manifest and quality evidence for one exact scope with explicit qualification state. |
| `POST /api/data-scopes` | Save one exact scope and matching manifest/quality references with an idempotency key. |
| `GET /api/data-scopes?limit=&offset=` | List saved exact scopes in the configured Console scope. |
| `GET /api/data-scopes/{saved_scope_id}` | Reopen an exact scope without widening or refreshing it. |
| `POST /api/data-scopes/{saved_scope_id}/revalidate` | Re-read producer evidence and persist `active`, `stale`, or `unavailable`. |
| `GET /api/experiments?limit=&offset=` | Discover experiment IDs by published backtest-run membership. |
| `GET /api/experiments/{experiment_id}/runs?compatible_with_run_id=&limit=&offset=` | List runs and scope-fingerprint comparison eligibility. |
| `GET /api/runs/{run_id}?section_limit=` | Return one run and bounded performance/evidence sections. |
| `GET /api/runs/{run_id}/risk-decisions?manager_id=&outcome=&cycle_id=&client_order_id=&limit=&offset=` | Return a bounded, filterable ordered manager-decision trace. |

The dataset response includes a `discovery` object with `catalogue_completeness`
(`complete`, `partial`, `stale`, or `unavailable`), `catalogue_freshness`, `can_discover`, and a separate
`load_capability` (`load_capable`, `discover_only`, or `unavailable`). Existing `console_read` rows prove stored
coverage only, so the default response is `partial` and `discover_only` until Data evidence supplies provider
catalogue and loading receipts. The Console never treats a visible symbol as proof of a complete provider universe.

### Saved exact data scopes

The saved-scope boundary persists an immutable handoff containing normalized symbols or universe, asset class, timeframe
and interval, UTC window, source/provider policy, research role, creator, and exact Data manifest and quality artifact
references. It stores references rather than recalculating Data quality. Install the additive table explicitly:

<!-- verified: integration:console tests/trader_console_api/repositories/test_saved_data_scopes_schema.py -->
```bash
TRADER_CONSOLE_DATABASE_URL="$TRADER_CONSOLE_DATABASE_URL" \
  uv run python -m trader_console_api.repositories.saved_data_scopes_schema install
```

Reopening returns the original scope and current evidence state. Missing or superseded producer evidence remains
`unavailable` or `stale`; it is never silently refreshed or widened. A missing `console_read.data_scope_evidence`
projection fails closed as `unavailable`.

The evidence endpoint binds the complete asset class, symbol set, timeframe/interval/bar type, UTC window, provider
and source-policy scope before returning manifest/quality artifact identity, coverage, findings, warnings and
provenance. An absent exact pair is `unavailable`; `complete`, `partial`, `stale`, `warning`, and `empty` remain
distinct producer states.

The run detail response keeps sections separate (`performance`, `comparison_summary`, `exposure`, `scope`, `equity_curve`, `comparison_curves`, `trades`,
`positions`, `assumptions`, `warnings`, `provenance`, `indicator_series`, `signal_markers`, `risk_composition`, `risk_summary`,
`risk_decisions`, `review_evidence`, `signals`, `orders`, `fills`, and `evidence_coverage`).
`indicator_series` is the exact persisted observation stream for the run. Each point carries producer-declared `pane`,
`scale_group`, `unit`, and `series_kind` fields: `price` series are eligible for the OHLC pane, while secondary panes
use their declared scale group. `signal_markers.event_ts` comes from the recorded decision cycle, so markers bind to
the event timestamp rather than wall-clock insertion time. Missing or unknown display metadata stays explicit; the API
does not recompute indicators from market bars.

Risk sections are producer-owned evidence. `risk_composition` is the ordered manager chain with catalogue version,
fingerprint, manager identity, and typed parameters. `risk_summary` reports whether risk evidence was recorded and
counts approved, transformed, rejected, and blocked decisions. `risk_decisions` is bounded and ordered by decision
time, cycle, and manager position; each row retains the manager reason and normalized before/after order fields. The
dedicated risk-decision route accepts manager, outcome, cycle, and client-order filters with limit/offset pagination, so
the review can inspect a long trace without loading it into one run-detail payload.
`unavailable` means the run predates the risk evidence contract or did not publish it. The API does not infer a risk
block from a broker rejection or an absent fill.

### Human next-decision record

The review workspace records a human research decision only after the run exposes a qualified scope and at least one
available review artifact. `POST /api/runs/{run_id}/next-decisions` accepts a strict `NextResearchDecisionRequest`
with `reject`, `refine`, or `continue`, rationale, exact canonical references for the run/Data/implementation/review
chain, assumptions, and limitations. `refine` and `continue` additionally require a bounded successor experiment
with exact Data and implementation references, an evaluation window, a maximum run count, and success criteria.

The request's `source_run_ref` must identify the route's run. The service resolves every reference from the research
artifact store, compares pinned payload/source hashes, checks the published run scope, and rejects missing, stale,
incompatible, or cross-run review evidence with a typed blocker. Only an authenticated `human:` or `operator:`
principal can record a decision; an agent or MCP identity receives HTTP 403. The complete immutable artifact is stored
in `research_artifacts` and its query projection in `research_next_decisions`.

`GET /api/runs/{run_id}/next-decisions` returns the latest revision for each decision stream, while
`GET /api/runs/{run_id}/next-decisions/{decision_id}` reopens the latest or an exact `revision`. Revision numbers are
contiguous and later records must name the immediately preceding `supersedes_artifact_id`; the original revision is
never edited. The response carries operator/time, rationale, exact references, limitations, and any bounded successor.
These records guide research only and never imply deployment, paper admission, or profitability.

`review_evidence` is a fixed three-part projection of Evaluation, multiple-testing, and Adversarial/robustness
artifacts. Each item carries its producer identity, artifact digest, claim scope, data roles, limitations, blockers,
and an explicit `available`, `missing`, `incompatible`, or `blocked` status. Optimisation-derived Evaluation and
robustness artifacts remain labelled as optimisation context and cannot set `independent_confirmation`; the Console
never recomputes producer statistics or turns exploratory selection into confirmation. Multiple-testing reports that
are not persisted and linked to the run stay `missing` with an actionable reason.

The API does not invent experiment metadata that is absent from the current contract. Saved comparison views contain
only user-authored intent; their selected run IDs, metric keys and series keys are reread against current evidence on
each load. Excluded selections remain visible with a reason such as `missing_scope_fingerprint`,
`no_comparison_projection`, or `scope_mismatch`.
An absent run is `404 {"code":"run_not_found","message":"..."}`; a database loss is
`503 {"code":"database_unavailable","message":"Console database is unavailable"}`.

## Backtest definition and preflight

The Console exposes the maintained strategy and risk choices before a definition is persisted or queued. The catalogue
is an explicit, versioned allowlist; callers cannot provide import paths or arbitrary classes. Each profile advertises
typed parameters, bounds, supported asset classes/timeframes, lookback requirements, and (for risk) manager IDs and
reason codes.

Every authoring draft also carries `strategy_implementation_lineage` and `risk_implementation_lineage`. Each lineage
must identify the selected catalogue profile, exact research implementation version, source SHA-256, validation-report
ID and payload, specification ID, and whether the selection was exact reuse, adaptation, or new authorship. Preflight
checks that nested IDs, kinds, and hashes agree and rejects missing or blocked evidence. A deployment may compose a
research-owned resolver for another source-hash/admission check; that resolver remains outside the Console package's
allowlist. The normalized immutable definition retains both lineages for review and execution. An import path,
serialized callable, or arbitrary class is rejected by the extra-forbid contracts and is never passed to a worker.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/backtests/catalogue` | Return the current strategy/risk profile catalogue and its version. |
| `POST /api/backtests/preflight` | Validate the exact saved data-scope handoff, profile versions, admitted implementation/admission lineage, parameters, coverage/warmup and resource budgets, then return a definition fingerprint. |

Preflight requires `data_scope` with the saved scope ID, fingerprint, symbols or universe, asset class, timeframe,
UTC window, provider/source policy, and manifest/quality artifact references. It resolves that ID in the server-owned
Console scope and rejects client drift, stale evidence, unavailable evidence, and missing scopes with actionable
`data_scope_mismatch`, `data_scope_stale`, or `data_scope_unavailable` issues. Coverage remains a bounded check on the
selected symbols; it never replaces the selected manifest or quality evidence with a new aggregate scope. A valid
response includes an immutable `normalized_definition` retaining the handoff, per-symbol `coverage` checks, and a
SHA-256 `definition_fingerprint`; it has no persistence, command, worker, or producer side effect.

To persist a valid preflight draft, install the additive definition table explicitly; API startup and requests never
run DDL:

<!-- verified: integration:console tests/trader_console_api/repositories/test_backtest_definitions_schema.py -->
```bash
TRADER_CONSOLE_DATABASE_URL="$TRADER_CONSOLE_DATABASE_URL" \
  uv run python -m trader_console_api.repositories.backtest_definitions_schema install
```

The definition routes store only normalized Console intent and keep earlier revisions immutable:

| Endpoint | Purpose |
| --- | --- |
| `POST /api/backtests/definitions` | Preflight and create a first revision. |
| `GET /api/backtests/definitions?limit=&offset=` | List the latest revision for each definition in the server-owned scope. |
| `GET /api/backtests/definitions/{definition_id}` | Fetch the latest revision. |
| `POST /api/backtests/definitions/{definition_id}/revisions` | Preflight and append a new revision. |

Create and revision requests return HTTP 422 with the typed preflight response when validation fails, 409 when the
content fingerprint conflicts in this scope, and 503 when the explicitly installed table or database is unavailable.
The definition ID and scope are server-owned; clients cannot choose a database or write producer evidence. Durable
execution commands are a separate follow-on boundary.

The first durable command boundary records a submit request and makes it observable across API restarts. Install its
additive table after definition storage:

<!-- verified: integration:console tests/trader_console_api/repositories/test_backtest_executions_schema.py -->
```bash
TRADER_CONSOLE_DATABASE_URL="$TRADER_CONSOLE_DATABASE_URL" \
  uv run python -m trader_console_api.repositories.backtest_executions_schema install
```

| Endpoint | Purpose |
| --- | --- |
| `POST /api/backtests/executions` | Idempotently create one `queued` command for a persisted definition. |
| `GET /api/backtests/executions/{execution_id}` | Read durable command status and progress fields. |
| `GET /api/backtests/executions?limit=&offset=` | List bounded command history. |

The submit body contains a server-owned `definition_id` and caller-provided `idempotency_key`. A duplicate key in the
same scope returns the existing command. The current slice records `queued` state only; a separately started worker,
lease/heartbeat updates, canonical `BacktestRunner` invocation, and terminal reconciliation operate through the
separate worker process described below.

The repository also provides `BacktestExecutionWorker`, which claims one command with a bounded lease, reserves a
deterministic run ID, accepts progress heartbeats, and records `completed`, `partial`, `failed`, or
`reconciliation_required` outcomes through an injected executor port. The worker does not substitute a fake executor:
the deployment composition must provide the adapter that resolves the exact catalogue versions and invokes the
internal-broker `BacktestRunner`. The maintained adapter writes a canonical producer configuration snapshot
(`strategy`, `market_data`, `logging.persist`, and `backtest`) and, for a PostgreSQL worker, persists the typed
`BacktestResult` metrics snapshot after the runner completes. This keeps scope identity, benchmark and assumptions,
performance, curves, fills, positions, and warning evidence available when the review is reopened after worker
completion.

For a local worker process, set `TRADER_CONSOLE_BACKTEST_CONFIG_PATH` to the core Trader YAML configuration and run:

<!-- verified: integration:console tests/trader_console_api/application/test_worker_entrypoint.py -->
```bash
TRADER_CONSOLE_BACKTEST_CONFIG_PATH=./config/local.yaml \
  uv run trader-console-worker
```

Use `--once` to claim at most one queued command. The worker requires the definition and execution tables to have been
installed explicitly; it does not run DDL at startup. `TRADER_CONSOLE_WORKER_ID`,
`TRADER_CONSOLE_WORKER_LEASE_SECONDS`, `TRADER_CONSOLE_WORKER_MAX_ATTEMPTS`, and
`TRADER_CONSOLE_WORKER_POLL_SECONDS` are bounded worker settings. An expired lease with a reserved run is marked
`reconciliation_required`; an unreserved command is requeued until its bounded retry count is exhausted.

### Complete data-to-backtest qualification

The qualified Console journey is deliberately ordered: select a bounded dataset in `/data`, inspect its Data-owned
manifest and quality evidence, save the exact scope, follow **Author backtest with this scope**, run authoring
preflight, persist the immutable definition, submit its durable execution command, and open the published run review.
The browser qualification captures the POST bodies and checks that the saved scope fingerprint, provider/source
policy, UTC window, manifest reference, and quality reference are unchanged in both preflight and definition
persistence. The review fixture carries the same scope ID and fingerprint into the published run context.

The journey fails closed when the saved scope cannot be reopened, evidence is stale or unavailable, or authoring
changes any scope field. These blockers are shown as actionable preflight issues; a failed preflight cannot create a
definition or execution command. Replay/bar-content identity remains producer-owned by GAP-06-03 and is consumed by
the backtest execution boundary rather than recomputed by the Console.

## Saved comparison views

Comparison definitions are scoped to the configured process scope and one experiment. Install the additive Console
table explicitly before using save/load commands; API startup and requests never create it:

<!-- verified: integration:console tests/trader_console_api/repositories/test_comparison_schema.py -->
```bash
TRADER_CONSOLE_DATABASE_URL='postgresql://developer:secret@127.0.0.1:5432/trader' \
  uv run python -m trader_console_api.repositories.comparison_schema install
TRADER_CONSOLE_DATABASE_URL='postgresql://developer:secret@127.0.0.1:5432/trader' \
  uv run python -m trader_console_api.repositories.comparison_schema status
```

The command uses only the explicit DSN and creates `console_app.comparison_views` when installing. It does not alter
producer-owned `console_read` objects. The bounded API surface is:

| Endpoint | Purpose |
| --- | --- |
| `POST /api/experiments/{experiment_id}/comparison-views/preview` | Evaluate a draft without saving it. |
| `GET /api/experiments/{experiment_id}/comparison-views?limit=&offset=` | List saved definitions. |
| `POST /api/experiments/{experiment_id}/comparison-views` | Save a new definition and return its live evaluation. |
| `GET /api/experiments/{experiment_id}/comparison-views/{view_id}` | Load a definition and reevaluate its evidence. |
| `PUT /api/experiments/{experiment_id}/comparison-views/{view_id}` | Replace a definition with `expected_revision`. |

Save rejects run IDs that are not members of the experiment. Empty and one-run definitions are valid drafts. A replace
whose revision is stale returns HTTP 409. Missing application storage returns HTTP 503 with
`comparison_storage_unavailable`; no request performs schema installation.

## Dedicated local demo

The [demo walkthrough](../../../examples/console_demo/README.md) runs PostgreSQL on loopback port 55432 and the API
on 8001, independently of the existing Trader database. Bootstrap and compatibility repairs are explicit producer
commands outside API startup. Its `console-demo` scope is `synthetic_demo`, without a brokerage-account label or
trading rows. The frontend proxies `/api/context`, `/api/market-data/datasets`, `/api/market-data/bars`,
`/health/live` and `/health/ready`; CORS is not needed.

## Existing local Trader database

For real local market-data exploration, install the current producer-owned `console_read` contract explicitly against
the existing Trader database before starting the API. Configure `TRADER_CONSOLE_DATABASE_URL` with the local Trader
DSN, use scope `trader-local` with environment `backtest`, and start the API with `uv run trader-console-api`.
The `/data` workflow then reads the published stock/crypto views and returns bounded OHLCV rows from the existing
database. The API does not connect to raw Trader tables, copy data into the demo database, or repair the contract at
startup. Keep the dedicated demo for synthetic and failure-state checks.

Backtest review reads the producer-owned projections for both experiment-linked runs and standalone `BacktestRunner`
runs. Standalone runs are grouped under `standalone_backtests`; their lifecycle, indicator, signal, order, fill, and
position evidence remains visible even when no aggregate metrics snapshot or replay scope was published. Equity,
performance and exposure are reconstructed from persisted initial state, fills, fees and market bars; missing scope or
benchmark identity remains explicitly unavailable.

## Paper operations

The paper operations workspace is read-only. It calls `GET /api/paper/runtime` and renders the latest published
session, market-data freshness, portfolio positions, open orders, fills, risk outcomes, incidents, and account
binding. Every section includes an evidence status and timestamp. `configured` account binding is configuration only;
it is not a verified broker identity. Missing producer projections for reconciliation attempts and halt state are
returned as `unavailable` with an explanation rather than inferred from `/health/ready`.

The endpoint uses the server-owned scope and a bounded read-only transaction. It accepts no broker, database, session,
or mutation selector. A database outage returns HTTP 503 with `database_unavailable`; stale or partial runtime evidence
remains HTTP 200 so the Console can show the operational limitation.
