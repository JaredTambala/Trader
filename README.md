# Trader

Stage 0 skeleton for a remote paper trading system.

## Setup (uv)

```bash
uv venv
uv sync --dev
```

## Configure environment (Alpaca ingestion)

Create/edit `.env` with your Alpaca data credentials and symbols:

```bash
cat .env
```

Example values are provided in `.env` (replace the placeholders).
Set `MARKET_DATA_ASSET_CLASS=stocks` (default) or `crypto` depending on the symbols.
For stock data on the Basic plan, use `MARKET_DATA_STOCK_FEED=iex`.

Load the environment before running:

```bash
set -a
. .env
set +a
```

## Run a no-op cycle

```bash
uv run python -m trader.cycle
```

## Ingest real market data (Alpaca)

```bash
export MARKET_DATA_SOURCE=alpaca
export MARKET_DATA_ASSET_CLASS=stocks
export MARKET_DATA_STOCK_FEED=iex
export MARKET_DATA_SYMBOLS=AAPL,MSFT
uv run python -m trader.cycle
```

Market data is persisted to DuckDB at `DB_PATH` (default: `events.duckdb`).

Crypto example (REST crypto endpoints do not require keys; websocket streaming still uses your keys):

```bash
export MARKET_DATA_SOURCE=alpaca
export MARKET_DATA_ASSET_CLASS=crypto
export MARKET_DATA_SYMBOLS=BTC/USD,ETH/USD
uv run python -m trader.cycle
```

## Continuous market data (websocket)

Run a long-lived process that writes bars as they arrive:

```bash
export MARKET_DATA_SOURCE=alpaca
export MARKET_DATA_ASSET_CLASS=stocks
export MARKET_DATA_STOCK_FEED=iex
uv run python -m trader.market_data_stream --symbols AAPL,MSFT
```

Crypto streaming example:

```bash
export MARKET_DATA_SOURCE=alpaca
export MARKET_DATA_ASSET_CLASS=crypto
uv run python -m trader.market_data_stream --symbols BTC/USD,ETH/USD
```

## Historical market data backfill (REST)

Backfill a window of bars from a time delta in the past:

```bash
export MARKET_DATA_SOURCE=alpaca
export MARKET_DATA_ASSET_CLASS=stocks
export MARKET_DATA_STOCK_FEED=iex
uv run python -m trader.market_data_backfill --symbols AAPL,MSFT --since 120m --timeframe 1Min
uv run python -m trader.market_data_backfill --symbols AAPL,MSFT --since 30d --timeframe 1Hour
uv run python -m trader.market_data_backfill --symbols AAPL,MSFT --since 6mo --timeframe 1Day
```
`--since` supports `m`/`h`/`d`/`mo` with calendar month subtraction (e.g., Mar 31 -> Feb 29).
`--timeframe` follows Alpaca formats like `5Min`, `15T`, `1Hour`, `1Day`, `1Week`, `3Month`.
Omit `--limit` to fetch all pages; set it to cap total bars returned.
Backfill uses a staging table plus `MERGE`, so reruns dedupe cleanly.

Crypto backfill example:

```bash
export MARKET_DATA_SOURCE=alpaca
export MARKET_DATA_ASSET_CLASS=crypto
uv run python -m trader.market_data_backfill --symbols BTC/USD,ETH/USD --since 6h --timeframe 1Min
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

Defaults (override with env vars):
- `PG_DB=trader`
- `PG_USER=trader`
- `PG_PASSWORD=traderpass`
- `PG_HOST=localhost`
- `PG_PORT=5432`

Enable the Postgres-backed event store:

```bash
export EVENT_STORE=postgres
export PG_HOST=localhost
export PG_PORT=5432
export PG_DB=trader
export PG_USER=trader
export PG_PASSWORD=traderpass
```

## UI (Reflex data viewer)

Install UI dependencies (includes Plotly for candlesticks) and run the viewer from `src/ui`:

```bash
uv sync --group ui
cd src/ui
uv run reflex run
```

The UI reads `EVENT_STORE` to decide the backend. For Postgres, set `PG_HOST`, `PG_PORT`, `PG_DB`, `PG_USER`, and `PG_PASSWORD` (or `PG_DSN`). For DuckDB, it reads `DB_PATH`.
