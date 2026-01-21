# Operations (Stage 0)

## Deployment (skeleton)

- Single-node deployment.
- One container or VM process running the trading loop.

## Runbook (skeleton)

- Start service: `python -m trader.cycle` for one-shot mode.
- Start streaming market data: `python -m trader.market_data_stream --symbols AAPL,MSFT`.
- Backfill historical bars: `python -m trader.market_data_backfill --symbols AAPL,MSFT --since 120m --timeframe 1Min` (use `m`/`h`/`d`/`mo`; months are calendar months). Omit `--limit` to fetch all pages.
- Run UI viewer: `cd src/ui && reflex run` (uses `EVENT_STORE`, `PG_*`, or `DB_PATH`).
- Start Postgres (Docker): `docker compose -f docker-compose.postgres.yml up -d`.
- Restart Postgres (Docker): `docker compose -f docker-compose.postgres.yml restart`.
- Stop Postgres (Docker): `docker compose -f docker-compose.postgres.yml down`.
- Stop service: terminate process safely.
- Halt trading: set global halt flag (to be implemented).

## Configuration (market data)

- `MARKET_DATA_SOURCE`: `noop` (default) or `alpaca`.
- `MARKET_DATA_ASSET_CLASS`: `stocks` (default) or `crypto`.
- `MARKET_DATA_STOCK_FEED`: `iex` (default) or `sip` (requires Algo Trader Plus).
- `MARKET_DATA_SYMBOLS`: comma-separated symbols (e.g. `AAPL,MSFT`).
- `MARKET_DATA_MAX_AGE_SECONDS`: staleness cutoff before skipping trading (default `60`).
- `ALPACA_DATA_BASE_URL`: Alpaca data endpoint (default `https://data.alpaca.markets`).

## Configuration (event store)

- `EVENT_STORE`: `duckdb` (default) or `postgres`.
- `DB_PATH`: DuckDB file path when using DuckDB (default `events.duckdb`).
- `PG_DSN`: optional Postgres DSN (overrides host/user/password).
- `PG_HOST`: Postgres host (default `localhost` for docker compose).
- `PG_PORT`: Postgres port (default `5432`).
- `PG_DB`: Postgres database name (default `trader`).
- `PG_USER`: Postgres user (default `trader`).
- `PG_PASSWORD`: Postgres password (default `traderpass`).

## Incidents (skeleton)

- If risk checks fail, the system must not trade.
- On errors, inspect event store logs (DuckDB or Postgres) for traceability.
