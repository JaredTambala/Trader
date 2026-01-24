# Schema (Stage 0)

This document describes the Stage 0 event schema for Postgres (TIMESTAMPTZ storage).

## Tables

### `runs`
- `run_id` (TEXT, PK)
- `run_type` (TEXT: backtest|trading)
- `started_at` (TIMESTAMP)
- `finished_at` (TIMESTAMP, nullable)
- `status` (TEXT)
- `error_message` (TEXT, nullable)
- `config_snapshot` (JSONB, nullable)
- `mode` (TEXT, nullable)
- `symbols` (TEXT[], nullable)
- `timeframe` (TEXT, nullable)
- `start_ts` (TIMESTAMP, nullable)
- `end_ts` (TIMESTAMP, nullable)

### `run_events`
- `cycle_id` (TEXT, PK)
- `run_id` (TEXT, FK)
- `strategy_id` (TEXT)
- `mode` (TEXT)
- `decision_ts` (TIMESTAMP)
- `started_at` (TIMESTAMP)
- `finished_at` (TIMESTAMP)
- `status` (TEXT)
- `error_message` (TEXT, nullable)

### `stock_bar_events`
- `symbol` (TEXT)
- `timeframe` (TEXT)
- `ts` (TIMESTAMP)
- `ingested_at` (TIMESTAMP)
- `open` (DOUBLE)
- `high` (DOUBLE)
- `low` (DOUBLE)
- `close` (DOUBLE)
- `volume` (DOUBLE)
- `trade_count` (DOUBLE, nullable)
- `vwap` (DOUBLE, nullable)
- `source` (TEXT)

### `crypto_bar_events`
- `symbol` (TEXT)
- `timeframe` (TEXT)
- `ts` (TIMESTAMP)
- `ingested_at` (TIMESTAMP)
- `open` (DOUBLE)
- `high` (DOUBLE)
- `low` (DOUBLE)
- `close` (DOUBLE)
- `volume` (DOUBLE)
- `trade_count` (DOUBLE, nullable)
- `vwap` (DOUBLE, nullable)
- `source` (TEXT)

### `signal_events`
- `run_id` (TEXT)
- `cycle_id` (TEXT, nullable)
- `symbol` (TEXT)
- `signal_value` (DOUBLE)
- `target_qty` (DOUBLE)
- `generated_at` (TIMESTAMP)

### `indicator_events`
- `run_id` (TEXT)
- `cycle_id` (TEXT, nullable)
- `symbol` (TEXT)
- `indicator_name` (TEXT)
- `value` (DOUBLE)
- `bar_ts` (TIMESTAMP)

### `order_events`
- `order_event_id` (TEXT, PK)
- `client_order_id` (TEXT)
- `run_id` (TEXT)
- `cycle_id` (TEXT, nullable)
- `symbol` (TEXT)
- `side` (TEXT)
- `qty` (DOUBLE)
- `order_type` (TEXT)
- `status` (TEXT)
- `broker_order_id` (TEXT, nullable)
- `rejection_reason` (TEXT, nullable)
- `created_at` (TIMESTAMP)

### `fill_events`
- `client_order_id` (TEXT)
- `run_id` (TEXT)
- `cycle_id` (TEXT, nullable)
- `fill_ts` (TIMESTAMP)
- `fill_qty` (DOUBLE)
- `fill_price` (DOUBLE)

Notes:
- Multiple fill rows per `client_order_id` are allowed (partial fills over time).
- Multiple order rows per `client_order_id` are allowed (append-only order lifecycle).

### `position_snapshots`
- `asof_ts` (TIMESTAMP)
- `symbol` (TEXT)
- `qty` (DOUBLE)
- `avg_price` (DOUBLE, nullable)
- `cash_balance` (DOUBLE)
- `run_id` (TEXT)
- `cycle_id` (TEXT, nullable)

### `config_kv`
- `key` (TEXT, PK)
- `value` (TEXT)

## Constraints

- `runs.run_id` is unique.
- `run_events.cycle_id` is unique.
- `order_events.order_event_id` is unique.
- `fill_events` has no uniqueness constraint; multiple rows per `client_order_id` are expected.
- `indicator_events` has no uniqueness constraint; append-only per cycle.
- `config_kv.key` is unique.
- `stock_bar_events` uses a unique index on `(symbol, timeframe, ts, source)` to prevent duplicates.
- `crypto_bar_events` uses a unique index on `(symbol, timeframe, ts, source)` to prevent duplicates.
- Timestamps are stored in UTC.

## Identifier Formats

- `run_id` is `run_<sha256>` derived from `run_type` and the run session `started_at` (UTC).
- `cycle_id` is `cycle_<sha256>` derived from `STRATEGY_ID` and `decision_ts` (UTC).
- `client_order_id` is `order_<sha256>` derived from `cycle_id`, `symbol` (uppercased),
  `side` (lowercased), and `target_qty` normalized to 8 decimal places.
- `order_event_id` is `order_evt_<uuid>` generated per order lifecycle event.

## Guarantees

- Same inputs produce the same `cycle_id` and `client_order_id`.
- Deterministic IDs enable idempotent retries without duplicate orders.

## Event Semantics

- `runs` captures backtest vs trading sessions.
- `run_events` is the authoritative record of each execution cycle.
- `stock_bar_events` stores Alpaca stock OHLCV bars.
- `crypto_bar_events` stores Alpaca crypto OHLCV bars.
- `signal_events` stores strategy outputs tied to `run_id` and `cycle_id`.
- `order_events` stores the canonical order lifecycle events.
- `fill_events` records executions tied to `client_order_id`.
- `position_snapshots` records portfolio state over time.
- `config_kv` stores operational flags (e.g. `halt=true`).

## Recommended Query Patterns

Latest run session:

```sql
SELECT *
FROM runs
ORDER BY finished_at DESC NULLS LAST
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

Latest stock bar per symbol:

```sql
SELECT symbol, close, ts
FROM stock_bar_events
WHERE timeframe = '1Min'
QUALIFY ts = MAX(ts) OVER (PARTITION BY symbol);
```

Latest crypto bar per symbol:

```sql
SELECT symbol, close, ts
FROM crypto_bar_events
WHERE timeframe = '1Min'
QUALIFY ts = MAX(ts) OVER (PARTITION BY symbol);
```

## Conventions

- Append-only tables with explicit event timestamps.
- Schema changes must be reviewed alongside `docs/execution.md`.
