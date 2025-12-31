# Schema (Stage 0)

This document describes the DuckDB schema used as the authoritative event store.

## Tables (initial outline)

- `run_events`
- `market_data_events`
- `signal_events`
- `order_events`
- `fill_events`
- `position_snapshots`
- `config_kv`

## Conventions

- Append-only tables with explicit event timestamps.
- Primary keys and idempotency keys will be documented per table.
- Schema changes must be reviewed alongside `docs/execution.md`.
