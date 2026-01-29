# Trader

Stage 0 skeleton for a remote paper trading system.

## Setup (uv)

```bash
uv venv
uv sync --dev
```

## Configuration (YAML)

Every command now takes a single argument: the path to a YAML configuration file.
Use `configs/example.yaml` as a starting point.

The YAML supports environment variable expansion (e.g. `${ALPACA_API_KEY}`), so you can
keep secrets in `.env` and load them into the shell if desired.

Broker selection is configured in YAML:

```yaml
broker:
  type: internal  # noop|internal|alpaca
  time_in_force: day
  internal:
    reject_probability: 0.0
    fill_delay_ms_mean: 0
    fill_delay_ms_stddev: 0
    fill_qty_fraction_mean: 1.0
    fill_qty_fraction_stddev: 0.0
    rng_seed: null
```

To use Alpaca paper trading, set:

```yaml
broker:
  type: alpaca

alpaca:
  api_key: ${ALPACA_API_KEY}
  secret_key: ${ALPACA_SECRET_KEY}
  base_url: ${ALPACA_BASE_URL}  # defaults to paper if omitted
```

Use `broker.time_in_force` to control order TIF (e.g., `day`, `gtc`, `ioc`). Crypto requires
`gtc`/`ioc`/`fok`, so `day` will be rejected.

### Random smoke-test strategy (paper only)

If you just want to validate the broker pipeline without indicators, use the random strategy:

```yaml
strategy:
  type: random  # or smoke
  random:
    seed: 123
    order_qty: 0.001
    buy_probability: 0.45
    sell_probability: 0.45
```

This strategy emits small buy/sell orders based purely on RNG. Use it only with paper trading.

### Toggle unit strategy (paper only)

For a deterministic connectivity test, use the toggle strategy:

```yaml
strategy:
  type: toggle  # or flip/pingpong
  toggle:
    order_qty: 1.0
```

This emits a buy for one unit when flat, and a sell for one unit when long. Use it with a single
symbol to avoid conflicting orders.

## Run a no-op cycle

```bash
uv run python -m trader.cycle configs/example.yaml
```

## Ingest real market data (Alpaca)

Update `market_data` and `alpaca` in your YAML, then run:

```bash
uv run python -m trader.cycle configs/example.yaml
```

Market data is persisted to the configured event store (`database.event_store: postgres` recommended).

## Continuous market data (websocket)

Set `stream.symbols`/`stream.asset_class` in YAML, then:

```bash
uv run python -m trader.market_data_stream configs/example.yaml
```

## Historical market data backfill (REST)

Set `backfill.since` (or `backfill.start`/`backfill.end`), `backfill.timeframe`, and symbols:

```bash
uv run python -m trader.market_data_backfill configs/example.yaml
```
`backfill.since` supports `m`/`h`/`d`/`mo` with calendar month subtraction.
`backfill.timeframe` follows Alpaca formats like `5Min`, `15T`, `1Hour`, `1Day`, `1Week`, `3Month`.
Timeframes are normalized across the app, so `1h`, `1Hour`, and `1H` resolve to the same stored value.

## Backtest (historical cycle replay)

Define `backtest.start`, `backtest.end`, and `backtest.timeframe`, then:

```bash
uv run python -m trader.backtest configs/example.yaml
```
Set `backtest.log_cycle_details: true` if you want per-cycle logs; otherwise only the summary is logged.
The summary includes aggregated portfolio metrics plus per-position qty/price/market value/PnL if available.
You can seed starting positions with `backtest.initial_positions` to make the summary meaningful before any trades.
If `avg_price` is omitted on an initial position, it defaults to the first bar close in the backtest window.
Set `backtest.initial_cash` to seed starting cash for the portfolio.

## Data quality checks (gap detection)

Configure `data_quality.symbols`, `data_quality.timeframe`, and optional start/end, then:

```bash
uv run python -m trader.data_quality configs/example.yaml
```
The checker flags missing gaps and separates expected session gaps for stocks.
Use `data_quality.sessions` to define per-symbol trading windows (symbol/timeframe/timezone).
Weekday-only session logic is used; market holidays may appear as gaps.

## Buffered event store (performance)

Enable asynchronous, buffered writes to reduce cycle latency. The writer uses its own Postgres connection.

```yaml
database:
  buffering:
    enabled: true
    flush_interval_ms: 250
    max_batch_size: 500
    max_queue_size: 10000
    block_on_full: true
```

## Selective event logging

You can reduce write volume for throwaway runs by disabling specific event types.
Run sessions and per-cycle `run_events` are always recorded.

```yaml
logging:
  persist:
    signals: true
    indicators: true
    orders: true
    fills: true
    positions: false
```

## Trader service (loop/realtime)

Set `trader_service.mode` to `loop` or `realtime`, then:

```bash
uv run python -m trader.trader_service configs/example.yaml
```

## UI Backtest Runner

The Reflex UI now ships with a UI backtest runner (Task 0.8b). It consists of:

- A `/backtest` form that accepts symbols, timeframe, start/end, initial cash, and strategy JSON before POSTing to the backend.
- A FastAPI worker (`src/trader/api.py`) that launches `BacktestRunner`, tracks progress, and persists metrics to `metrics_snapshots`.
- Manual progress refresh and result loading (use the buttons on the form).
- A `/backtest/result` page showing return, Sharpe, max drawdown, an equity vs benchmark chart, and final positions.
- Asset class selector on the backtest form (stocks/crypto).

Note: `strategy_params` is stored with the run for auditability but does not yet override strategy behavior.

### Running the backend

The FastAPI service requires the same YAML config as the rest of the system:

```bash
uv run python -m trader.api configs/example.yaml --port 8100
```

Set the UI environment variable `BACKEND_BASE_URL` (e.g., in `.env`) so the Reflex UI knows where to POST/poll:

```
BACKEND_BASE_URL=http://localhost:8100
```

The UI form will display run IDs, status, and progress. Use “Refresh progress” and “Load results” to pull updates,
then click “View results” to open the results page.

### Testing

The API is covered by `tests/test_backtest_api.py`:

```bash
uv run pytest tests/test_backtest_api.py
```

### Realtime replay (DB-driven)

To simulate the realtime pipeline without Alpaca, replay stored bars and emit NOTIFY events:

```bash
uv run python -m trader.market_data_replay configs/example.yaml
```

This reads bars from Postgres and emits the same NOTIFY payloads the websocket streamer
produces, so the trader service runs the real realtime path deterministically.

### Metrics snapshots

Enable schema-less metrics snapshots (JSON payloads) during runs:

```yaml
metrics:
  enable_snapshots: true
  interval_seconds: 30
  window_seconds: null
```

To seed an initial in-memory paper trading portfolio for realtime runs, add
`initial_cash` and optional `initial_positions` under `trader_service`:

```yaml
trader_service:
  mode: real_time
  initial_cash: 100000
  initial_positions:
    - symbol: BTC/USD
      qty: 0.5
      avg_price: 90000
```

For Alpaca paper trading, you can sync the starting portfolio directly from
Alpaca by setting `trader_service.portfolio_source: alpaca` (this is the default
when `broker.type` is `alpaca`). To use the latest DB snapshots instead, set
`trader_service.portfolio_source: db`.

Example: run backfill while the trader service executes (two terminals):

```bash
# Terminal A
uv run python -m trader.trader_service configs/example.yaml

# Terminal B
uv run python -m trader.market_data_backfill configs/example.yaml
```

## Tests

```bash
uv run pytest
```

## Postgres (local dev via Docker)

Start a local Postgres instance for Task 0.5:

```bash
docker compose -f docker-compose.postgres.yml up -d
```

Stop and remove the container:

```bash
docker compose -f docker-compose.postgres.yml down
```

Restart:

```bash
docker compose -f docker-compose.postgres.yml restart
```

Defaults (configure in YAML under `database.pg`):
- `db: trader`
- `user: trader`
- `password: traderpass`
- `host: localhost`
- `port: 5432`

Enable the Postgres-backed event store by setting:

```yaml
database:
  event_store: postgres
  pg:
    host: localhost
    port: 5432
    db: trader
    user: trader
    password: traderpass
```

## UI (Reflex data viewer)

Install UI dependencies (includes Plotly for candlesticks) and run the viewer from `src/ui`:

```bash
uv sync --group ui
cd src/ui
uv run reflex run
```

The UI connects to Postgres. Set `PG_HOST`, `PG_PORT`, `PG_DB`, `PG_USER`, and `PG_PASSWORD` (or `PG_DSN`).
Use the date/time range inputs to filter precisely by timestamp.

## Strategy (Task 0.6)

Set a strategy implementation and parameters in YAML:

```yaml
strategy:
  type: noop # or sma
  timeframe: 1Min
  sma_short_window: 5
  sma_long_window: 20
```

The SMA strategy interprets a short/long SMA crossover as buy/sell signals.
