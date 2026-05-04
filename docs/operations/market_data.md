# Market Data Component

The market-data component gets bars into the event store and supplies bars to strategy execution. It includes backfill,
streaming, replay, sample-data loading, and data-quality checks.

## Component responsibilities

- Fetch or receive bars from an external provider.
- Normalize bars into stock or crypto bar event records.
- Persist bars idempotently.
- Emit realtime notifications when new bars arrive.
- Supply stored bars to backtests and live cycles.
- Provide deterministic sample data for reproducible smoke tests.
- Check stored data for gaps and session coverage.

## Backtest operation

Backtests do not fetch live data and do not write bar data. They read historical bars that already exist in Postgres.

Flow:

1. The sample loader, backfill, or another ingestion path writes bars before the backtest starts.
2. `BacktestRunner` loads bars for the requested symbols, asset class, timeframe, and date window.
3. Lookback bars are included so indicators have enough history.
4. The in-memory bar set becomes the market-data source for `run_cycle`.
5. Missing or sparse bars can produce warnings depending on backtest data assumptions.

Reproducible sample workflow:

```bash
docker compose -f docker-compose.postgres.yml up -d
uv run python examples/load_sample_market_data.py
uv run python examples/run_reproducible_backtest.py
```

The checked-in sample uses synthetic `DEMO` stock bars under `examples/data/`.

Because the replayed bar set is loaded before the run, the backtest sees a stable input dataset. That makes the result
repeatable, but it also means the result is only as good as the stored bars, the selected timeframe, and the configured
fallback assumptions.

## Live operation

Realtime operation normally uses a separate market-data stream process:

```bash
uv run python run_market_data_stream.py configs/example.yaml
```

Flow:

1. `MarketDataStreamRunner` receives bars from Alpaca websocket data.
2. Bars are inserted into `stock_bar_events` or `crypto_bar_events`.
3. If the insert is not a duplicate, Postgres emits a `NOTIFY` payload.
4. `TraderService` receives the notification and invokes a trading cycle.
5. `run_cycle` reads recent bars from Postgres and applies staleness checks.

The inserted bar row is the durable fact. The notification is only a wake-up signal for the service. Bar tables are
idempotent on `(symbol, timeframe, ts, source)`, so retrying a loader or backfill should not create duplicate input
facts.

Historical backfill:

```bash
uv run python run_market_data_backfill.py configs/example.yaml
uv run python run_market_data_backfill.py configs/example.yaml --dry-run --json --symbols AAPL,MSFT --asset-class stocks --timeframe 1Min --since 30d
```

Replay through realtime path:

```bash
uv run python -m trader.market_data_replay configs/example.yaml
```

Data-quality checks:

```bash
uv run python run_data_quality.py configs/example.yaml
uv run python run_data_quality.py configs/example.yaml --output-json artifacts/data_quality/example.json
uv run python run_data_quality.py configs/example.yaml --output-json artifacts/data_quality/example.json --json
```

The data-quality command returns a structured report and can write JSON with a stable `report_id`, generated
timestamp, symbols, asset class, timeframe, start/end, per-symbol summaries, gap counts, and maximum gaps. Research
runs can attach an existing report with `--data-quality-report` or generate one with `--run-data-quality`.
Sprint 5 discovery also runs data quality before recommendations and treats missing reports or missing gaps as
promotion blockers under the conservative profile.

## Configurability

Shared market-data config:

```yaml
market_data:
  source: alpaca
  asset_class: crypto
  stock_feed: iex
  symbols:
    - BTC/USD
  max_age_seconds: 604800
```

Backfill config:

```yaml
backfill:
  since: 40d
  timeframe: 1Min
  symbols:
    - BTC/USD
  asset_class: crypto
  limit: null
```

Stream config:

```yaml
stream:
  symbols:
    - BTC/USD
  asset_class: crypto
  timeframe: 1Min
```

Replay config:

```yaml
replay:
  asset_class: crypto
  symbols:
    - BTC/USD
  timeframe: 1Min
  start: "2026-01-20T00:00:00Z"
  end: "2026-01-21T00:00:00Z"
  cadence_seconds: 0.2
  notify_channel: market_data
  limit: null
```

When a separate stream/backfill process owns bar writes, the trader-service YAML should usually use:

```yaml
market_data:
  source: noop
```

Backfill, streaming, replay, and trading can run as separate processes because Postgres is the boundary between data
and execution. Realtime notification avoids constant polling by the trading service.

## Current limits

- No partitioned market-data storage.
- No retention policy.
- No first-class versioned datasets.
- No distributed data ingestion coordinator.
- Provider corrections are not versioned.
- Exchange calendars are not universally enforced in the runtime.
- Corporate actions and split/dividend adjustment are not first-class yet.
