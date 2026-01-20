# Operations (Stage 0)

## Deployment (skeleton)

- Single-node deployment.
- One container or VM process running the trading loop.

## Runbook (skeleton)

- Start service: `python -m trader.cycle` for one-shot mode.
- Stop service: terminate process safely.
- Halt trading: set global halt flag (to be implemented).

## Configuration (market data)

- `MARKET_DATA_SOURCE`: `noop` (default) or `alpaca`.
- `MARKET_DATA_ASSET_CLASS`: `stocks` (default) or `crypto`.
- `MARKET_DATA_STOCK_FEED`: `iex` (default) or `sip` (requires Algo Trader Plus).
- `MARKET_DATA_SYMBOLS`: comma-separated symbols (e.g. `AAPL,MSFT`).
- `MARKET_DATA_MAX_AGE_SECONDS`: staleness cutoff before skipping trading (default `60`).
- `ALPACA_DATA_BASE_URL`: Alpaca data endpoint (default `https://data.alpaca.markets`).

## Incidents (skeleton)

- If risk checks fail, the system must not trade.
- On errors, inspect DuckDB event logs for traceability.
