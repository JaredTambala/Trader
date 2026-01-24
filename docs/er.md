% Trading ER Model (Stage 0 Refactor)

## Overview

We use a single `run_id` plus a `run_type` field to distinguish **backtest** runs
from **trading** runs. Every event table links to the `runs` table via `run_id`,
so we can query by `run_id` or by `run_type` without nullable foreign keys.

## Entities and relationships

```
runs (run_id PK, run_type)
  ├─< run_events.run_id (FK)          # per-cycle execution log
  ├─< signal_events.run_id (FK)
  ├─< order_events.run_id (FK)
  ├─< fill_events.run_id (FK)
  └─< position_snapshots.run_id (FK)
```

## Table definitions (proposed)

### `runs`

- `run_id` (TEXT, PK) — deterministic UUID or `run_<sha256>`
- `run_type` (TEXT) — `backtest` | `trading`
- `started_at` (TIMESTAMPTZ)
- `finished_at` (TIMESTAMPTZ, nullable)
- `status` (TEXT: started|success|failed)
- `config_snapshot` (JSONB) — YAML config captured at start
- `mode` (TEXT, nullable) — `once|loop|realtime` (trading runs)
- `symbols` (TEXT[]) — symbols used in the run
- `timeframe` (TEXT)
- `start_ts` (TIMESTAMPTZ, nullable) — backtest window start
- `end_ts` (TIMESTAMPTZ, nullable) — backtest window end

### `run_events`

Per-cycle execution log. Each backtest run creates many `run_events`.

- `cycle_id` (TEXT, PK) — deterministic per-cycle ID
- `run_id` (TEXT, FK)
- `strategy_id` (TEXT)
- `decision_ts` (TIMESTAMPTZ)
- `started_at` (TIMESTAMPTZ)
- `finished_at` (TIMESTAMPTZ, nullable)
- `status` (TEXT)
- `error_message` (TEXT, nullable)

### `signal_events`

- `run_id` (TEXT, FK)
- `cycle_id` (TEXT, nullable) — optional link to `run_events`
- `symbol` (TEXT)
- `signal_value` (DOUBLE)
- `target_qty` (DOUBLE)
- `generated_at` (TIMESTAMPTZ)

### `indicator_events`

- `run_id` (TEXT, FK)
- `cycle_id` (TEXT, nullable)
- `symbol` (TEXT)
- `indicator_name` (TEXT)
- `value` (DOUBLE)
- `bar_ts` (TIMESTAMPTZ)

### `order_events`

- `order_event_id` (TEXT, PK)
- `client_order_id` (TEXT)
- `run_id` (TEXT, FK)
- `cycle_id` (TEXT, nullable)
- `symbol` (TEXT)
- `side` (TEXT)
- `qty` (DOUBLE)
- `order_type` (TEXT)
- `status` (TEXT)
- `broker_order_id` (TEXT, nullable)
- `rejection_reason` (TEXT, nullable)
- `created_at` (TIMESTAMPTZ)

### `fill_events`

- `client_order_id` (TEXT)
- `run_id` (TEXT, FK)
- `cycle_id` (TEXT, nullable)
- `fill_ts` (TIMESTAMPTZ)
- `fill_qty` (DOUBLE)
- `fill_price` (DOUBLE)

### `position_snapshots`

- `asof_ts` (TIMESTAMPTZ)
- `symbol` (TEXT)
- `qty` (DOUBLE)
- `avg_price` (DOUBLE, nullable)
- `cash_balance` (DOUBLE)
- `run_id` (TEXT, FK)
- `cycle_id` (TEXT, nullable)

## Constraints and indexes

- `runs.run_type` must be `backtest` or `trading`.
- Index `run_id` on all event tables.
- Optional composite index `(run_id, cycle_id)` where `cycle_id` is used.
- Keep existing unique indexes for bar events.

## Query examples

Backtest positions:

```sql
SELECT ps.*
FROM position_snapshots ps
JOIN runs r ON r.run_id = ps.run_id
WHERE r.run_type = 'backtest' AND r.run_id = :run_id
ORDER BY ps.asof_ts ASC;
```

Live trading orders:

```sql
SELECT oe.*
FROM order_events oe
JOIN runs r ON r.run_id = oe.run_id
WHERE r.run_type = 'trading' AND r.run_id = :run_id
ORDER BY oe.created_at ASC;
```

## Validation against current needs

- A single `run_id` groups all events for a backtest or trading session.
- `run_type` cleanly separates backtest vs trading without nullable columns.
- `cycle_id` preserves per-cycle traceability while keeping events tied to the parent run.
