# Schema (Stage 0)

This document describes the DuckDB schema used as the authoritative event store.

## Tables

### `run_events`
- `run_id` (TEXT, PK)
- `strategy_id` (TEXT)
- `mode` (TEXT)
- `decision_ts` (TIMESTAMP)
- `started_at` (TIMESTAMP)
- `finished_at` (TIMESTAMP)
- `status` (TEXT)
- `error_message` (TEXT, nullable)

### `market_data_events`
- `symbol` (TEXT)
- `ts` (TIMESTAMP)
- `ingested_at` (TIMESTAMP)
- `price` (DOUBLE)
- `volume` (DOUBLE, nullable)
- `source` (TEXT)

### `signal_events`
- `run_id` (TEXT)
- `symbol` (TEXT)
- `signal_value` (DOUBLE)
- `target_qty` (DOUBLE)
- `generated_at` (TIMESTAMP)

### `order_events`
- `client_order_id` (TEXT, PK)
- `run_id` (TEXT)
- `symbol` (TEXT)
- `side` (TEXT)
- `qty` (DOUBLE)
- `order_type` (TEXT)
- `status` (TEXT)
- `broker_order_id` (TEXT, nullable)
- `created_at` (TIMESTAMP)

### `fill_events`
- `client_order_id` (TEXT)
- `fill_ts` (TIMESTAMP)
- `fill_qty` (DOUBLE)
- `fill_price` (DOUBLE)

### `position_snapshots`
- `asof_ts` (TIMESTAMP)
- `symbol` (TEXT)
- `qty` (DOUBLE)
- `avg_price` (DOUBLE)

### `config_kv`
- `key` (TEXT, PK)
- `value` (TEXT)

## Constraints

- `run_events.run_id` is unique.
- `order_events.client_order_id` is unique.
- `config_kv.key` is unique.
- `market_data_events` uses a unique index on `(symbol, ts, source)` to prevent duplicates.
- Timestamps are stored in UTC.

## Event Semantics

- `run_events` is the authoritative record of each execution cycle.
- `market_data_events` stores raw ingested data before signals.
- `signal_events` stores strategy outputs tied to `run_id`.
- `order_events` stores the canonical order lifecycle events.
- `fill_events` records executions tied to `client_order_id`.
- `position_snapshots` records portfolio state over time.
- `config_kv` stores operational flags (e.g. `halt=true`).

## Recommended Query Patterns

Latest run:

```sql
SELECT *
FROM run_events
ORDER BY finished_at DESC
LIMIT 1;
```

Latest position per symbol:

```sql
SELECT symbol, qty, avg_price, asof_ts
FROM (
    SELECT
        symbol,
        qty,
        avg_price,
        asof_ts,
        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY asof_ts DESC) AS rn
    FROM position_snapshots
)
WHERE rn = 1;
```

Latest market data per symbol:

```sql
SELECT symbol, price, ts
FROM market_data_events
QUALIFY ts = MAX(ts) OVER (PARTITION BY symbol);
```

## Conventions

- Append-only tables with explicit event timestamps.
- Schema changes must be reviewed alongside `docs/execution.md`.
