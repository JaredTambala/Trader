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

Crypto example (no keys required by Alpaca for crypto data):

```bash
export MARKET_DATA_SOURCE=alpaca
export MARKET_DATA_ASSET_CLASS=crypto
export MARKET_DATA_SYMBOLS=BTC/USD,ETH/USD
uv run python -m trader.cycle
```

## Tests

```bash
uv run pytest
```
