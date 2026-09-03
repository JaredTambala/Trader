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

- `run_id` (TEXT)
- `session_id` (TEXT, nullable)
- `cycle_id` (TEXT, nullable)
- `symbol` (TEXT)
- `signal_value` (DOUBLE PRECISION)
- `target_qty` (DOUBLE PRECISION)
- `generated_at` (TIMESTAMPTZ)

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

### `order_events`

- `order_event_id` (TEXT, PK)
- `client_order_id` (TEXT)
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
- `created_at` (TIMESTAMPTZ)

### `fill_events`

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

## Identifier Guarantees

- `run_id` is `run_<sha256>` derived from `run_type` and the run session `started_at` (UTC).
- `cycle_id` is `cycle_<sha256>` derived from strategy identity and `decision_ts` (UTC).
- `experiment_id` is `exp_<normalized-name-slug>` derived from the normalized experiment name.
- `experiment_run_id` is `exp_run_<sha256-prefix>` derived from `experiment_id` and `run_id`.
- `client_order_id` is `order_<sha256>` derived from `cycle_id`, normalized `symbol`, normalized `side`, and normalized `target_qty`.
- `order_event_id` is `order_evt_<uuid>` generated per order lifecycle row.

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
