# Trading ER Model (Phase 1)

## Overview

The runtime tracks two related lifecycle concepts:

- `runs`: backtest and trading run records
- `trading_sessions`: trading-only session records keyed by `session_id`

Most runtime event tables carry both `run_id` and `session_id` so trading activity can be grouped either by the
generic run lifecycle or by a long-lived trading session.

## Core Relationships

```text
runs (run_id PK)
  ├─< run_events.run_id
  ├─< signal_events.run_id
  ├─< indicator_events.run_id
  ├─< order_events.run_id
  ├─< fill_events.run_id
  ├─< position_snapshots.run_id
  └─< metrics_snapshots.run_id

trading_sessions (session_id PK)
  ├─< run_events.session_id
  ├─< signal_events.session_id
  ├─< indicator_events.session_id
  ├─< order_events.session_id
  ├─< fill_events.session_id
  ├─< position_snapshots.session_id
  └─< metrics_snapshots.session_id
```

## Notes

- `run_events` represents per-cycle execution state and is upserted by `cycle_id`.
- `order_events` is append-only application history for order lifecycle transitions.
- `fill_events` allows multiple rows per `client_order_id`.
- `stock_bar_events` and `crypto_bar_events` are idempotent on `(symbol, timeframe, ts, source)`.
- `config_kv` stores operational flags such as a future global halt flag.

For current column definitions and query examples, use [schema.md](schema.md).
