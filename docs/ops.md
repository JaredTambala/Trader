# Operations (Stage 0)

## Deployment (skeleton)

- Single-node deployment.
- One container or VM process running the trading loop.

## Runbook (skeleton)

- Start service: `python -m trader.cycle` for one-shot mode.
- Stop service: terminate process safely.
- Halt trading: set global halt flag (to be implemented).

## Incidents (skeleton)

- If risk checks fail, the system must not trade.
- On errors, inspect DuckDB event logs for traceability.
