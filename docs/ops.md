# Operations (Stage 0)

## Deployment (skeleton)

- Single-node deployment.
- One container or VM process running the trading loop.

## Runbook (skeleton)

- Start service: `python -m trader.trader_service configs/example.yaml` (set `trader_service.mode` to `once|loop|realtime`).
- Start streaming market data: `python -m trader.market_data_stream configs/example.yaml` (set `stream.symbols`/`stream.asset_class`).
- Backfill historical bars: `python -m trader.market_data_backfill configs/example.yaml` (set `backfill.since` or `backfill.start/end`).
- Run a backtest: `python -m trader.backtest configs/example.yaml` (set `backtest.start/end/timeframe`).
- Run data quality checks: `python -m trader.data_quality configs/example.yaml` (set `data_quality.symbols/timeframe`, optionally `data_quality.sessions`).
- Run UI viewer: `cd src/ui && reflex run` (uses Postgres `PG_*` or `PG_DSN`).
- Start Postgres (Docker): `docker compose -f docker-compose.postgres.yml up -d`.
- Restart Postgres (Docker): `docker compose -f docker-compose.postgres.yml restart`.
- Stop Postgres (Docker): `docker compose -f docker-compose.postgres.yml down`.
- Stop service: terminate process safely.
- Halt trading: set global halt flag (to be implemented).

When running the streamer/backfill alongside the trader service:
- Set `market_data.source: noop` in the YAML used for the trader service (data already arrives via streaming/backfill).
- Use `trader_service.mode: realtime` to react to Postgres `NOTIFY` events, or `loop` for a polling cadence.

## Configuration (market data)

```yaml
market_data:
  source: alpaca # or noop
  asset_class: stocks # or crypto
  stock_feed: iex # or sip
  symbols: [AAPL, MSFT]
  max_age_seconds: 60
```

```yaml
alpaca:
  api_key: ${ALPACA_API_KEY}
  secret_key: ${ALPACA_SECRET_KEY}
  data_base_url: https://data.alpaca.markets
```

## Configuration (event store)

```yaml
database:
  event_store: postgres # or noop
  pg:
    host: localhost
    port: 5432
    db: trader
    user: trader
    password: traderpass
  buffering:
    enabled: true
    flush_interval_ms: 250
    max_batch_size: 500
    max_queue_size: 10000
    block_on_full: true
```
The buffered writer uses a dedicated Postgres connection to avoid read/write contention.

```yaml
logging:
  level: INFO
```

```yaml
trader_service:
  mode: loop
  cadence_seconds: 1.0
  min_trigger_interval_ms: 200
  notify_channel: market_data
```

## Incidents (skeleton)

- If risk checks fail, the system must not trade.
- On errors, inspect Postgres event store logs for traceability.

## Verification

- Trader service logs show `Trader service start` and `Cycle start`.
- Backfill/stream logs show `Market data ...` entries and (for Postgres) `NOTIFY` events.
- Event store tables populate: `stock_bar_events`/`crypto_bar_events`, `signal_events`, `position_snapshots`.

## UI Backtest Runner Ops

- **Backend service:** `uv run python -m trader.api configs/example.yaml`
  - Exposes `POST /backtest`, `GET /backtest/progress`, and `GET /backtest/result`.
  - The same YAML config as the rest of the system is used for event store and runner settings.
- **UI:** Run `uv run python -m src.ui.ui` (Reflex) after setting `BACKEND_BASE_URL=http://localhost:8000` in `.env`.
  - Fill the `/backtest` form, submit, and monitor the status banner/progress label.
  - The UI polls the progress endpoint every 5 s, updates `backtest_progress`, and auto-fetches `/backtest/result` when the run completes.
- **Result persistence:** `BacktestResult` summaries are serialized to `metrics_snapshots` with `run_id`, making them queryable via the API or directly in Postgres.
- **Errors:** Backend errors mark the run `failed`, and the UI displays `Backtest {run_id} failed` along with the failure message.
