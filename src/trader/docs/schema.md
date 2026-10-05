# Schema

This document describes the current Postgres runtime schema. Postgres is the authoritative runtime store.
DuckDB remains a test/support backend only.

## Table Semantics

### Upserted lifecycle tables

These tables use insert-or-update behavior through helper methods in `EventStore`:

- `runs`
- `trading_sessions`
- `run_events`
- `experiments`
- `experiment_runs`

`record_run_session_start(...)` and `record_cycle_start(...)` create initial rows.
`record_run_session_finish(...)` and `record_cycle_finish(...)` update terminal status fields.
`upsert_experiment(...)`, `record_experiment_run_start(...)`, and `record_experiment_run_finish(...)` maintain the
research grouping and run-summary records.

### Append-oriented event tables

These tables are append-oriented at the application level:

- `signal_events`
- `indicator_events`
- `prediction_events`
- `order_events`
- `fill_events`
- `position_snapshots`
- `metrics_snapshots`

`order_events` is the canonical append-only order lifecycle history.
`fill_events` allows multiple rows per `client_order_id`.

### Idempotent market-data tables

These tables accept inserts with a unique constraint on `(symbol, timeframe, ts, source)`:

- `stock_bar_events`
- `crypto_bar_events`

Duplicate inserts with the same uniqueness tuple are ignored.

## Tables

### `runs`

- `run_id` (TEXT, PK)
- `run_type` (TEXT: `backtest|trading`)
- `started_at` (TIMESTAMPTZ)
- `finished_at` (TIMESTAMPTZ, nullable)
- `status` (TEXT)
- `error_message` (TEXT, nullable)
- `config_snapshot` (JSONB, nullable)
- `mode` (TEXT, nullable)
- `symbols` (TEXT[], nullable)
- `timeframe` (TEXT, nullable)
- `start_ts` (TIMESTAMPTZ, nullable)
- `end_ts` (TIMESTAMPTZ, nullable)

### `trading_sessions`

- `session_id` (TEXT, PK)
- `strategy_id` (TEXT, nullable)
- `started_at` (TIMESTAMPTZ)
- `finished_at` (TIMESTAMPTZ, nullable)
- `status` (TEXT)
- `error_message` (TEXT, nullable)
- `config_snapshot` (JSONB, nullable)
- `mode` (TEXT, nullable)
- `symbols` (TEXT[], nullable)
- `timeframe` (TEXT, nullable)
- `start_ts` (TIMESTAMPTZ, nullable)
- `end_ts` (TIMESTAMPTZ, nullable)

### `experiments`

- `experiment_id` (TEXT, PK)
- `name` (TEXT, unique)
- `description` (TEXT, nullable)
- `tags` (TEXT[], nullable)
- `created_at` (TIMESTAMPTZ)
- `updated_at` (TIMESTAMPTZ)
- `metadata` (JSONB, nullable)

`experiments` groups research runs by a stable name-derived identifier. Re-running the same experiment name updates
description, tags, timestamp, and metadata without creating a second group.

### `experiment_runs`

- `experiment_run_id` (TEXT, PK)
- `experiment_id` (TEXT)
- `run_id` (TEXT)
- `status` (TEXT)
- `created_at` (TIMESTAMPTZ)
- `finished_at` (TIMESTAMPTZ, nullable)
- `strategy_id` (TEXT, nullable)
- `strategy_name` (TEXT, nullable)
- `strategy_version` (TEXT, nullable)
- `symbols` (TEXT[], nullable)
- `asset_class` (TEXT, nullable)
- `timeframe` (TEXT, nullable)
- `start_ts` (TIMESTAMPTZ, nullable)
- `end_ts` (TIMESTAMPTZ, nullable)
- `parameters` (JSONB, nullable)
- `assumptions` (JSONB, nullable)
- `provenance` (JSONB, nullable)
- `data_quality` (JSONB, nullable)
- `result_summary` (JSONB, nullable)
- `artifact_dir` (TEXT, nullable)
- `error_message` (TEXT, nullable)

`experiment_runs` stores queryable comparison fields plus full JSON provenance. It links one research member to its
runtime `runs.run_id`; failed sweep members can still be recorded even when no complete backtest result was produced.

### `run_events`

- `cycle_id` (TEXT, PK)
- `run_id` (TEXT)
- `session_id` (TEXT, nullable)
- `strategy_id` (TEXT)
- `mode` (TEXT)
- `decision_ts` (TIMESTAMPTZ)
- `started_at` (TIMESTAMPTZ)
- `finished_at` (TIMESTAMPTZ, nullable)
- `status` (TEXT)
- `error_message` (TEXT, nullable)

### `stock_bar_events`

- `symbol` (TEXT)
- `timeframe` (TEXT)
- `ts` (TIMESTAMPTZ)
- `ingested_at` (TIMESTAMPTZ)
- `open` (DOUBLE PRECISION)
- `high` (DOUBLE PRECISION)
- `low` (DOUBLE PRECISION)
- `close` (DOUBLE PRECISION)
- `volume` (DOUBLE PRECISION)
- `trade_count` (DOUBLE PRECISION, nullable)
- `vwap` (DOUBLE PRECISION, nullable)
- `source` (TEXT)

### `crypto_bar_events`

- `symbol` (TEXT)
- `timeframe` (TEXT)
- `ts` (TIMESTAMPTZ)
- `ingested_at` (TIMESTAMPTZ)
- `open` (DOUBLE PRECISION)
- `high` (DOUBLE PRECISION)
- `low` (DOUBLE PRECISION)
- `close` (DOUBLE PRECISION)
- `volume` (DOUBLE PRECISION)
- `trade_count` (DOUBLE PRECISION, nullable)
- `vwap` (DOUBLE PRECISION, nullable)
- `source` (TEXT)

### `signal_events`

- `signal_event_id` (TEXT, nullable for legacy rows)
- `run_id` (TEXT)
- `session_id` (TEXT, nullable)
- `cycle_id` (TEXT, nullable)
- `symbol` (TEXT)
- `signal_name` (TEXT, nullable)
- `signal_value` (DOUBLE PRECISION)
- `target_qty` (DOUBLE PRECISION)
- `generated_at` (TIMESTAMPTZ)
- `prediction_event_refs` (TEXT, nullable)
- `mapper_id` (TEXT, nullable)
- `payload` (TEXT, JSON-encoded, nullable)

### `indicator_events`

- `run_id` (TEXT)
- `session_id` (TEXT, nullable)
- `cycle_id` (TEXT, nullable)
- `symbol` (TEXT)
- `indicator_name` (TEXT)
- `value` (DOUBLE PRECISION, nullable)
- `bar_ts` (TIMESTAMPTZ)
- `payload` (TEXT, JSON-encoded, nullable)

`value` preserves the scalar audit path for simple indicators. `payload` stores structured indicator observations,
including components such as MACD line/signal/histogram or future model-classifier metadata. This keeps richer
indicators independently observable without forcing every output into one float.

### `prediction_events`

- `prediction_event_id` (TEXT, PK)
- `run_id` (TEXT)
- `session_id` (TEXT, nullable)
- `cycle_id` (TEXT, nullable)
- `deployment_id` (TEXT)
- `deployment_validation_id` (TEXT)
- `model_version_id` (TEXT)
- `feature_set_id` (TEXT)
- `feature_batch_hash` (TEXT)
- `decision_ts` (TIMESTAMPTZ)
- `symbol` (TEXT)
- `output_name` (TEXT)
- `semantics` (TEXT)
- `horizon` (TEXT)
- `value_payload` (TEXT)
- `latency_ms` (DOUBLE PRECISION, nullable)
- `status` (TEXT)
- `error_message` (TEXT, nullable)
- `payload` (TEXT, JSON-encoded, nullable)

### `order_events`

- `order_event_id` (TEXT, PK)
- `client_order_id` (TEXT)
- `signal_event_id` (TEXT, nullable)
- `run_id` (TEXT)
- `session_id` (TEXT, nullable)
- `cycle_id` (TEXT, nullable)
- `symbol` (TEXT)
- `side` (TEXT)
- `qty` (DOUBLE PRECISION)
- `order_type` (TEXT)
- `status` (TEXT)
- `broker_order_id` (TEXT, nullable)
- `rejection_reason` (TEXT, nullable)
- `decision_evidence` (TEXT, JSON-encoded, nullable)
- `created_at` (TIMESTAMPTZ)

### `fill_events`

- `fill_event_id` (TEXT, nullable for legacy rows)
- `client_order_id` (TEXT)
- `run_id` (TEXT)
- `session_id` (TEXT, nullable)
- `cycle_id` (TEXT, nullable)
- `fill_ts` (TIMESTAMPTZ)
- `fill_qty` (DOUBLE PRECISION)
- `raw_fill_price` (DOUBLE PRECISION, nullable)
- `fill_price` (DOUBLE PRECISION)
- `slippage_amount` (DOUBLE PRECISION, nullable)
- `fee_amount` (DOUBLE PRECISION, nullable)

`fill_price` is the effective execution price used for accounting. When cost modeling is enabled, `raw_fill_price`
preserves the unadjusted bar-close reference while `slippage_amount` and `fee_amount` expose the explicit execution
costs applied to the fill. Older rows may leave these fields null.

`signal_event_id`, `order_event_id`, and `fill_event_id` are stable lifecycle identities. New strategy emissions derive
signal identities from the run/cycle/symbol/signal name, and fills derive identities from the client order and fill
evidence. The event-store bootstrap adds indexes for signal-to-order and fill lookups. These identifiers are additive:
legacy rows remain valid, but consumers must treat missing IDs or links as unknown rather than reconstructing causality
from timestamps.

The `console_read.signal_lifecycle`, `console_read.order_lifecycle`, and `console_read.fill_lifecycle` views expose the
typed causal chain without raw payloads. `console_read.backtest_evidence_coverage` exposes whether each optional event
stream was recorded for a persisted backtest result.

The `console_read.backtest_scope` view exposes the typed replay window, content-based data identity, benchmark
construction, initial cash and position count, execution assumptions, and separate strategy/parameter variant
fingerprints. Legacy result snapshots return null comparison fields and are not eligible for compatibility-gated cohorts.
The `console_read.backtest_comparison_runs` and `console_read.backtest_comparison_curves` views expose the bounded
cohort rows and independently normalized strategy/benchmark curves used by comparison consumers.

### `position_snapshots`

- `asof_ts` (TIMESTAMPTZ)
- `symbol` (TEXT)
- `qty` (DOUBLE PRECISION)
- `avg_price` (DOUBLE PRECISION, nullable)
- `cash_balance` (DOUBLE PRECISION)
- `run_id` (TEXT)
- `session_id` (TEXT, nullable)
- `cycle_id` (TEXT, nullable)

### `metrics_snapshots`

- `ts` (TIMESTAMPTZ)
- `run_id` (TEXT, nullable)
- `session_id` (TEXT, nullable)
- `cycle_id` (TEXT, nullable)
- `payload` (TEXT, JSON-encoded)

### `config_kv`

- `key` (TEXT, PK)
- `value` (TEXT)

Current operator keys:

- `halt`: `true` or `false`.
- `halt_reason`: operator-supplied text.
- `halt_updated_at`: UTC timestamp string.

### `paper_operator_commands`

The Console installs this additive ledger explicitly when paper command routes are enabled. The core event-store
bootstrap creates the same relation for a runtime-owned database. Rows retain the authenticated request and the
runtime outcome:

- `command_id` (UUID, PK)
- `scope_id`, `command`, `admission_id`, `idempotency_key`, `request_digest`, `requested_by` (TEXT)
- `reason`, `outcome_code`, `outcome_message` (TEXT, nullable)
- `status` (`requested`, `accepted`, `completed`, `rejected`, `ambiguous`, or `failed`)
- `requested_at`, `accepted_at`, `completed_at` (TIMESTAMPTZ)

`(scope_id, idempotency_key)` is unique. The Console writes only `requested` rows after admission and scope
validation; `TraderService` claims them between cycles and records terminal or ambiguous outcomes. A reconciliation
failure is intentionally ambiguous because the broker's remote state cannot be inferred from a timeout.

## Constraints and Indexes

- `runs.run_id` is unique.
- `trading_sessions.session_id` is unique.
- `run_events.cycle_id` is unique.
- `experiments.experiment_id` is unique.
- `experiments.name` is unique.
- `experiment_runs.experiment_run_id` is unique.
- `experiment_runs.run_id` is indexed.
- `experiment_runs.experiment_id`, `status`, and `created_at` are indexed for comparison queries.
- `order_events.order_event_id` is unique.
- `config_kv.key` is unique.
- `stock_bar_events` has a unique index on `(symbol, timeframe, ts, source)`.
- `crypto_bar_events` has a unique index on `(symbol, timeframe, ts, source)`.
- Session and run indexes exist on the major runtime event tables.
- Timestamps are stored in UTC.

## `console_read` contract schema

`console_read` is a producer-owned, versioned projection boundary for the read-only Trader Console. It is not part of
runtime bootstrap and is installed explicitly. The current contract contains stable relation names:

| Relation | Source | Deliberate exclusions |
| --- | --- | --- |
| `contract_versions` | migration metadata | No runtime configuration or secrets. |
| `sessions` | `trading_sessions` | `config_snapshot` |
| `runs` | `runs` | `config_snapshot` |
| `cycles` | `run_events` | None; every current scalar column is allowlisted. |
| `stock_bars` | `stock_bar_events` | None; every current scalar column is allowlisted. |
| `crypto_bars` | `crypto_bar_events` | None; every current scalar column is allowlisted. |
| `signals` | `signal_events` | `payload`, `prediction_event_refs` |
| `indicators` | `indicator_events` | `payload` |
| `predictions` | `prediction_events` | `value_payload`, `payload` |
| `orders` | `order_events` | `decision_evidence` |
| `fills` | `fill_events` | None; identity limitations still apply. |
| `positions` | `position_snapshots` | None; retention limitations still apply. |
| `signal_lifecycle` | `signal_events` | `payload`, `prediction_event_refs` |
| `order_lifecycle` | `order_events` | `decision_evidence` |
| `fill_lifecycle` | `fill_events` | None; legacy identity fields may be null. |
| `backtest_evidence_coverage` | `metrics_snapshots` + `experiment_runs` | Result payload details. |
| `backtest_scope` | `metrics_snapshots` + `experiment_runs` | Untyped result payload and raw parameter values. |
| `backtest_comparison_runs` | typed `console_read` projections | Raw result payload and mixed-scope aggregation. |
| `backtest_comparison_curves` | typed `console_read` projections | Raw result payload and unnormalized cross-run curves. |
| `data_scope_evidence` | `research_artifacts` (`dataset_manifest` + `data_quality_report`) | Unbounded artifact-store rows; only exact scope, bounded payloads and qualification evidence are exposed. |
| `backtest_scope` (contract 11) | `runs` + `metrics_snapshots` | Producer-carries the exact Console data-scope fingerprint/saved-scope ID, benchmark identity, and persisted assumptions. |

The exact ordered column lists are declared by `CONSOLE_READ_COLUMNS` in
`trader.event_store.console_read_contract` and checked against the PostgreSQL catalog during deployment verification.
Database identities and grants are deployment concerns outside this migration. Consumers must issue bounded,
parameterized queries against these views and preserve explicit session/data-source scope.

## Identifier Guarantees

- `run_id` is `run_<sha256>` derived from `run_type` and the run session `started_at` (UTC).
- `cycle_id` is `cycle_<sha256>` derived from strategy identity and `decision_ts` (UTC).
- `experiment_id` is `exp_<normalized-name-slug>` derived from the normalized experiment name.
- `experiment_run_id` is `exp_run_<sha256-prefix>` derived from `experiment_id` and `run_id`.
- `client_order_id` is `order_<sha256>` derived from `cycle_id`, normalized `symbol`, normalized `side`, and normalized `target_qty`.
- `order_event_id` is `order_evt_<uuid>` generated per order lifecycle row.
- `signal_event_id` is deterministic for a run/cycle/symbol/signal identity; legacy signal rows may not have one.
- `fill_event_id` is deterministic for a client order and fill evidence; legacy fill rows may not have one.

## Query Patterns

Latest run session:

```sql
SELECT *
FROM runs
ORDER BY finished_at DESC NULLS LAST, started_at DESC
LIMIT 1;
```

Latest position per symbol:

```sql
SELECT symbol, qty, avg_price, cash_balance, asof_ts
FROM (
    SELECT
        symbol,
        qty,
        avg_price,
        cash_balance,
        asof_ts,
        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY asof_ts DESC) AS rn
    FROM position_snapshots
) ranked
WHERE rn = 1;
```

Latest stock bar per symbol and timeframe:

```sql
SELECT DISTINCT ON (symbol) symbol, close, ts
FROM stock_bar_events
WHERE timeframe = '1Min'
ORDER BY symbol, ts DESC;
```

Latest crypto bar per symbol and timeframe:

```sql
SELECT DISTINCT ON (symbol) symbol, close, ts
FROM crypto_bar_events
WHERE timeframe = '1Min'
ORDER BY symbol, ts DESC;
```

Latest order state per `client_order_id`:

```sql
SELECT DISTINCT ON (client_order_id)
    client_order_id,
    status,
    broker_order_id,
    rejection_reason,
    created_at
FROM order_events
ORDER BY client_order_id, created_at DESC, order_event_id DESC;
```

Latest research runs for comparison:

```sql
SELECT
    experiment_run_id,
    run_id,
    status,
    strategy_id,
    symbols,
    timeframe,
    result_summary,
    artifact_dir,
    finished_at
FROM experiment_runs
WHERE experiment_id = 'experiment_...'
ORDER BY created_at DESC
LIMIT 20;
```

## Conventions

- Review schema changes alongside the owning `src/trader/` module, this package documentation, and Postgres integration tests.
- Keep docs aligned with the runtime schema rather than historical DuckDB-first descriptions.
