# Event Store And Audit

The event-store/audit component persists runtime facts and makes backtests and live trading reconstructable.

## Component responsibilities

- Bootstrap the runtime schema.
- Persist lifecycle rows, event rows, snapshots, and metrics.
- Persist research experiment and experiment-run records.
- Enforce idempotency for bar ingestion.
- Provide Postgres notifications for realtime market-data triggers.
- Preserve append-only order and fill history.
- Tie records together with `run_id`, `session_id`, and `cycle_id`.
- Support direct SQL reconstruction after a run.
- Own versioned, allowlisted read views used by the separate Trader Console API.

## Backtest operation

Backtest mode uses Postgres as the source of historical bars and as the audit sink for trading events.

Backtest writes:

- `runs`
- `experiments` and `experiment_runs` when run through the research CLI
- `run_events`
- `signal_events` when enabled
- `indicator_events` when enabled
- `order_events`
- `fill_events`
- `position_snapshots`
- `risk_compositions` and `risk_decisions` for ordered risk-manager evidence
- `metrics_snapshots` for serialized aggregate results when persisted

Backtest mode does not write `stock_bar_events` or `crypto_bar_events` during the replay loop.

The event store and its typed read projections are Trader domain surfaces, not Superset integration code. Backtest,
research, Console, SQL clients, and external dashboard tools consume these database surfaces independently. The core
runtime must not call a dashboard service, publish chart metadata, or add a consumer-specific completion hook. If a
consumer needs a field that is not present, add it only through a general evidence contract or a producer-owned typed
view with semantics that remain valid outside that consumer.

## Live operation

Live mode uses Postgres as the audit source of truth and trigger bus.

Live writes:

- `runs`
- `trading_sessions`
- `run_events`
- `stock_bar_events` / `crypto_bar_events`
- `signal_events` and `indicator_events` when enabled
- `order_events`
- `fill_events`
- `position_snapshots`
- `metrics_snapshots`
- `config_kv` for operator control state such as global halt

Live Alpaca trading splits truth:

- Postgres is authoritative for audit history.
- Alpaca is authoritative for current broker account state.

Reconciliation joins those sources by appending records. It does not rewrite history.

## Configurability

Event-store config:

<!-- verified: config -->
```yaml
database:
  event_store: postgres
  pg:
    host: ${PG_HOST}
    port: ${PG_PORT}
    db: ${PG_DB}
    user: ${PG_USER}
    password: ${PG_PASSWORD}
  buffering:
    enabled: false
    flush_interval_ms: 1000
    max_batch_size: 5000
    max_queue_size: 10000
    block_on_full: true
```

Persistence flags:

<!-- verified: config -->
```yaml
logging:
  persist:
    signals: true
    indicators: true
    orders: true
    fills: true
    positions: true
```

Postgres is the runtime source of truth. DuckDB remains test/support-only.

## Console read contract

The core event-store owner publishes a versioned contract in the `console_read` schema. Installing it is an explicit deployment
step; `PostgresEventStore` construction does not install, upgrade, or repair this interface. The Console API uses a
separate connection pool and must never construct `PostgresEventStore` for reads.

The contract provides stable, ordinary `security_barrier` views for sessions, runs, cycles, stock and crypto bars, signals,
indicators, predictions, orders, fills, and position snapshots. Contract version 2 adds typed backtest evidence relations:
`backtest_runs`, `backtest_performance`, `backtest_exposure`, `backtest_equity_curve`, `backtest_trades`,
`backtest_positions`, `backtest_assumptions`, `backtest_warnings`, and `backtest_provenance`. Every view selects a fixed
column list. The backtest relations perform the producer-owned projection from the latest serialized result snapshot
once at the contract boundary; dashboard SQL consumes ordinary typed columns and never parses the metrics payload. The
exposure relation is intentionally aggregate/final-state evidence; a time-series exposure curve requires the producer
to retain those samples explicitly. The contract does not
expose `config_snapshot`, generic runtime `payload` fields, prediction `value_payload`, order `decision_evidence`,
research JSON, or `config_kv`. Those fields remain outside the reviewed read surface.

Contract version 3 adds producer-owned lifecycle projections: `signal_lifecycle`, `order_lifecycle`, and
`fill_lifecycle`. Signals receive a deterministic `signal_event_id`; orders retain their existing `order_event_id` and
may point to the originating signal; fills receive a deterministic `fill_event_id` and point to their client order.
These relations are the reviewed surface for causal signal-to-order-to-fill overlays. Older rows remain readable, but
their newly introduced identifiers or links are null and must be shown as unknown/unlinked rather than inferred.
Version 3 also adds `backtest_evidence_coverage`, which reports `recorded`, `not_recorded`, `not_applicable`, or
`unknown` for signal, order, fill, and position evidence. `recorded` includes a valid run with zero rows; it does not
mean that the stream necessarily contains a trade.

Contract version 4 adds the typed `backtest_scope` projection. It records the replay window, a content identity for the
loaded bars, benchmark identity and construction, initial cash and position count, execution and missing-data
assumptions, and separate strategy/parameter variant fingerprints. The scope fingerprint excludes intentional variant
dimensions, so runs can be compared only when the producer-owned scope matches. Legacy snapshots return null scope
fields and remain readable; they are unavailable for compatibility-gated comparison.

Contract version 5 adds `backtest_comparison_runs` and `backtest_comparison_curves`. The run projection combines scope,
variant and typed performance fields; the curve projection normalizes strategy and benchmark equity independently from
each run's first valid point and exposes drawdown. Consumers must select a single scope fingerprint before comparing
variants. Missing scope, zero starting equity, or an unavailable benchmark remains null rather than becoming a zero.
An empty selected cohort returns no rows; runs with a different scope fingerprint are outside that cohort, and legacy
runs without scope metadata are omitted from the comparison projections while remaining available through the single-run
views.

Contract version 6 adds `indicator_series` and `signal_markers` for backtest review. `indicator_series` is a typed,
producer-owned projection of persisted indicator events: each point retains run/session/cycle lineage and declares its
series identity, strategy/implementation lineage, parameter fingerprint, data-scope fingerprint, pane, scale group,
unit, and rendering kind. `signal_markers` binds signal events to the recorded
decision-cycle timestamp, preserving the causal event identity instead of using wall-clock insertion time. Missing or
unknown display metadata remains explicit; consumers do not infer scale from names or recompute indicators from bars.

Contract version 7 adds standalone `BacktestRunner` sessions to the backtest projections. They retain their canonical
`run_id` and event evidence, while the Console groups them under `standalone_backtests` when no experiment membership
exists.

Contract version 8 makes the typed backtest evidence projections read directly from persisted runtime evidence. Run
metadata comes from `runs` and `experiment_runs`; execution evidence comes from signal, order, fill and position
tables; equity is reconstructed from initial cash/positions, signed fills and fees, and the persisted market bars.
Performance and exposure are derived from that equity curve. `metrics_snapshots` remains available to other consumers,
but is no longer a Console read dependency. Missing scope fingerprints or benchmark evidence remain explicit nulls,
while a run with sufficient runtime evidence can still expose its reconstructed metrics.

Contract version 9 adds `risk_composition`, `risk_summary`, and `risk_decisions`. The producer stores one idempotent
ordered composition snapshot per run and append-only per-manager decision records scoped to run, session, cycle, and
client order. The projections expose manager identity, catalogue version, typed parameters, composition fingerprint,
approval/transformation/rejection outcomes, reason codes, and normalized before/after order quantities and fields for
approved transformations. Rejected rows retain the candidate before-order and leave the after-order absent.
Composition is retained for zero-signal and zero-trade runs; legacy runs remain explicit `unavailable`. Risk blocks are
separate from broker rejections and missing fills, and the Console reads these projections with bounded detail limits.

`console_read.contract_versions` records the installed version and the oldest admitted consumer. A consumer is
compatible when its supported version is between `minimum_consumer_version` and `contract_version`, inclusive. Missing
or malformed metadata, catalog drift, or unavailable views fails readiness. Relation and Python symbol names do not
embed the version; compatibility metadata carries evolution explicitly.

The installer does not create service principals, roles, grants, credentials, or database-wide policy. Local
development may use the existing developer connection while the API enforces short read-only transactions and bounded
queries. The API configuration is the extension point for a later deployment to supply a secret-backed DSN, managed
identity, proxy, or another IAM mechanism without changing the read contract.

The versioned implementation and rollback guard live in
`trader.event_store.console_read_contract`. Ordinary runtime schema bootstrap remains in `schema.py`; the two paths are
deliberately separate. Upgrades must remain additive while their recorded `minimum_consumer_version` admits the
deployed API. Removing or changing a column requires a new contract version and coordinated API rollout. Rollback of
the current contract drops only the `console_read` schema, refuses to run over an unknown/later version, and leaves
source evidence and externally managed database access unchanged.

### Migration impact report

Contract releases and the Console API's requirement are declared together in `trader.event_store.console_contract_status`.
The report makes the producer migration surface explicit without registering or discovering external database clients:

<!-- verified: integration:console tests/trader/event_store/test_console_contract_status.py -->
```bash
uv run python -m trader.event_store.console_read_contract status --offline
TRADER_CONSOLE_DATABASE_URL='postgresql://reader@127.0.0.1/trader' \
  uv run python -m trader.event_store.console_read_contract status --json
```

`--offline` reports known releases, affected relations, source-table owners, and the API's declared requirement without credentials.
The connected form reads only `console_read` metadata/catalog information using a bounded read-only transaction. It
reports whether the API is ready, which require a release, catalog damage, newer-producer boundaries, and a manual
installer action. It never installs, repairs, grants, refreshes external assets, reads trading rows, or falls back to
general `PG_*` credentials. The versioned backtest views therefore do not force an API migration. A database consumer
that declares those views validates that requirement in its own setup rather than being registered in Trader core.

### Typed backtest read projections

The typed backtest relations use `run_id` as their scope anchor. Experiment-linked rows use `experiment_runs`; standalone
`BacktestRunner` rows are sourced from `runs` and grouped under the Console-only `standalone_backtests` selector. The
projections read normalized runtime evidence directly: trade, position, lifecycle, indicator, signal, warning and
provenance rows retain source event identity, while equity, performance and exposure are derived from initial state,
fills, fees and bars at read time. `backtest_runs` retains the original experiment, strategy, environment, symbol,
timeframe, replay-window, status, error, and artifact identifiers. Original run IDs are never inferred from timestamps;
the standalone group label is only a UI selector context.

Optional metrics snapshots may still be written for other consumers, but they are not required for Console evidence.
External database consumers may consume these views, and the relation names and fields remain independent of any
dashboard. The initial comparison is strategy versus benchmark within one run; cross-run ranking is intentionally outside
this contract.

Source reconciliation is bounded to the selected run: compare `console_read.backtest_runs` to `runs` and
`experiment_runs` on `run_id` and `experiment_run_id`; compare fills, positions, lifecycle, indicator and signal rows to
their source event tables; and validate the reconstructed equity timeline against the selected bars and signed fills.
Empty arrays produce no detail rows and remain distinguishable from a missing or incomplete result through the run status
and evidence coverage. Missing, null, or non-object provenance produces no provenance detail rows rather than failing the
read contract.

## Persistence model

Table semantics:

| Table group | Tables | Write behavior |
| --- | --- | --- |
| Lifecycle | `runs`, `trading_sessions`, `run_events` | Start rows are inserted; finish calls update terminal fields. |
| Research | `experiments`, `experiment_runs` | Experiment names upsert groups; run start/finish calls update per-run status and summaries. |
| Market data | `stock_bar_events`, `crypto_bar_events` | Idempotent insert on `(symbol, timeframe, ts, source)`. |
| Decision history | `signal_events`, `indicator_events` | Append-oriented when enabled. |
| Execution history | `order_events`, `fill_events` | Append-oriented order/fill history. |
| State snapshots | `position_snapshots`, `metrics_snapshots` | Append-oriented observations. |
| Control state | `config_kv` | Key/value operational state. |

Operator control keys:

- `halt`: `true` or `false`.
- `halt_reason`: free-text operator reason.
- `halt_updated_at`: UTC timestamp string.

The halt state is read by `run_cycle` before live strategy execution. A halted cycle writes
`run_events.status='halted'` and `error_message='global_halt'`; no strategy orders or broker submissions are produced.
The same keys are surfaced by `run_operator.py status`, `health`, and `halt status`.

Fill audit fields:

- `raw_fill_price`: unadjusted reference price.
- `fill_price`: effective accounting price.
- `slippage_amount`: deterministic modeled slippage cost when supplied.
- `fee_amount`: modeled fee when supplied.

Old rows can have null cost fields. Readers should treat null fees/slippage as zero.

Indicator audit fields:

- `indicator_name`: stable indicator observation name.
- `value`: scalar value when the indicator output can be represented as one float.
- `payload`: JSON-encoded structured observation for component indicators or model outputs.
- `bar_ts`: timestamp of the bar/window endpoint used for the observation.
- producer metadata in `payload.metadata`: `series_id`, `series_label`, `display.pane`, `display.scale_group`,
  `display.unit`, `display.series_kind`, `signal_name`, and the deterministic `signal_event_id` used to bind the
  observation to its signal evaluation.

This allows SMA/EMA-style scalar indicators, MACD-style component indicators, and future model-backed indicators to be
observed independently from the strategy orders they influence.

Realtime notification path:

1. Streamer/replay inserts a bar.
2. Insert succeeds only if the uniqueness tuple is new.
3. Postgres emits `NOTIFY`.
4. `TraderService` parses the payload.
5. A cycle runs after duplicate suppression.

The notification is a trigger; the bar row is the durable fact.

The `experiments` and `experiment_runs` tables remain generic core event-store capabilities. Canonical agent research no
longer uses them: its specifications, runs, trials, and reports are owned by the separate Postgres research artifact
store. Detailed runtime audit remains in `runs`, `run_events`, `order_events`, `fill_events`, and `position_snapshots`.

Postgres allows separate stream, replay, backfill, service, and analysis processes to coordinate through one runtime
store. Optional buffered writes can reduce write contention, idempotent bar inserts support safe retries, and session
or run indexes support common review queries.

The event store preserves what the runtime observed and decided. It is not a market-data validator by itself; that
role belongs to data-quality tooling and future dataset/versioning work.

## Current limits

- Runtime tables still have no general migration framework beyond event-store bootstrap/alter support. The Console
  read interface has a separate explicit versioned installer and guarded rollback.
- No table partitioning or retention policy.
- No warehouse/export pipeline beyond current result/research exports and SQL access.

For exact columns and query examples, use [Schema](schema.md).
