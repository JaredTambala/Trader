# Event Store and Audit Component

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
- `metrics_snapshots` for serialized aggregate results when persisted

Backtest mode does not write `stock_bar_events` or `crypto_bar_events` during the replay loop.

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

- No migration framework beyond bootstrap/alter support in the event store.
- No table partitioning or retention policy.
- No warehouse/export pipeline beyond current result/research exports and SQL access.

For exact columns and query examples, use [../schema.md](../schema.md).
