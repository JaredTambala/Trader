# Operations (Phase 1)

For the current component-oriented operating manual, start with `docs/operations/README.md`.

## Deployment (Phase 1 baseline)

- Single-node development/runtime baseline.
- Postgres-backed services run as separate processes.
- Deployment packaging and VPS productization are deferred beyond Phase 1.

## Runbook (skeleton)

- Start service: `uv run python examples/run_injected_trader_service.py`.
- Operator status: `uv run python run_operator.py configs/example.yaml status --json`.
- Operator health: `uv run python run_operator.py configs/example.yaml health --json`.
- Inspect positions: `uv run python run_operator.py configs/example.yaml positions --json`.
- Inspect local open orders: `uv run python run_operator.py configs/example.yaml open-orders --json`.
- Halt trading: `uv run python run_operator.py configs/example.yaml halt set --reason "manual safety stop"`.
- Clear halt: `uv run python run_operator.py configs/example.yaml halt clear`.
- Reconcile local order state from broker reality: `uv run python run_operator.py configs/example.yaml reconcile --json`.
- Inspect order recovery state: `uv run python run_order_recovery.py configs/example.yaml report`.
- Reconcile local order state from broker reality: `uv run python run_order_recovery.py configs/example.yaml reconcile`.
- Clean local open order state only: `uv run python run_order_recovery.py configs/example.yaml clean-start`.
- Start streaming market data: `uv run python run_market_data_stream.py configs/example.yaml` (set `stream.symbols`/`stream.asset_class`).
- Backfill historical bars: `uv run python run_market_data_backfill.py configs/example.yaml` (set `backfill.since` or `backfill.start/end`).
- Run a backtest: `uv run python examples/run_injected_backtest.py`.
- Run a research experiment: `uv run python run_research_experiment.py configs/reproducible_backtest.yaml --experiment demo_research --run-data-quality`.
- Compare research results: `uv run python run_compare_results.py configs/reproducible_backtest.yaml --experiment demo_research --format table`.
- Plan an AI/tool discovery workflow: `uv run python run_research_discovery.py configs/reproducible_backtest.yaml --symbols DEMO --strategies trend_following --data-mode plan --json`.
- Run AI/tool research discovery: `uv run python run_research_discovery.py configs/reproducible_backtest.yaml --symbols DEMO --strategies trend_following,mean_reversion --data-mode existing --json`.
- Build recommendations: `uv run python run_research_recommendations.py configs/reproducible_backtest.yaml --experiment demo_discovery --json`.
- Build a dry-run promotion packet: `uv run python run_prepare_paper_promotion.py configs/reproducible_backtest.yaml --recommendation-json artifacts/recommendations/demo_discovery.json --recommendation-id rec_... --dry-run --json`.
- Run data quality checks: `uv run python run_data_quality.py configs/example.yaml` (set `data_quality.symbols/timeframe`, optionally `data_quality.sessions`).
- Write data quality JSON: `uv run python run_data_quality.py configs/example.yaml --output-json artifacts/data_quality/example.json`.
- Start Postgres (Docker): `docker compose -f docker-compose.postgres.yml up -d`.
- Restart Postgres (Docker): `docker compose -f docker-compose.postgres.yml restart`.
- Stop Postgres (Docker): `docker compose -f docker-compose.postgres.yml down`.
- Stop service: terminate process safely.
- Halt trading: use `run_operator.py ... halt set`. The global halt is stored in Postgres `config_kv` and is enforced
  by `run_cycle` before strategy execution or order submission.

When running the streamer/backfill alongside the trader service:
- Set `market_data.source: noop` in the YAML used for the trader service (data already arrives via streaming/backfill).
- Use `runtime.mode: realtime` to react to Postgres `NOTIFY` events, or `loop` for a polling cadence.

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
runtime:
  mode: loop
```

```yaml
trader_service:
  cadence_seconds: 1.0
  min_trigger_interval_ms: 200
  notify_channel: market_data
  startup_recovery_mode: resume # or fail_closed
  portfolio_source: alpaca
  order_reconciliation_interval_seconds: 60
```

## Incidents (skeleton)

- If risk checks fail, the system must not trade.
- If `run_operator.py ... health` returns `1`, treat the service as degraded or safe-stopped and inspect the JSON
  reasons before continuing.
- If it returns `2`, treat the runtime as unhealthy; latest run/cycle failure or stale market data needs operator
  action before trading resumes.
- On errors, inspect Postgres event store logs for traceability.
- AI/tool discovery commands are research-only. They may read operator JSON and write local research artifacts, but they
  must not be used to start trading, clear halt, or reconcile broker state.

## Order Recovery Runbook

For the architectural rationale behind these procedures, see `docs/runtime_hot_path_and_reconciliation.md`.

- `report`
  - Use when you want to inspect local open orders, broker open orders, and scope mismatches without mutating anything.
- `reconcile`
  - Use when stale local `order_events` are blocking trading or local state appears out of sync with Alpaca.
  - This reads broker state and repairs local order history.
  - `run_operator.py ... reconcile` runs the same resume-style repair from the main operator CLI.
- `clean-start`
  - Use when you want to close local open orders in the configured universe before a fresh runtime start.
  - This is local event-store cleanup only. It does not cancel broker orders and it does not start trading.

## Broker Universe Mismatch

The service fails closed when Alpaca reports positions outside the configured symbols or asset class.

This is intentional safety behavior. It prevents the runtime from trading against an account whose
state does not match the configured strategy universe.

To resolve a mismatch:

- inspect the live Alpaca account positions and open orders
- decide whether the broker-side state is intentional
- either flatten or otherwise resolve the broker-side mismatch manually
- then restart the trader service

## Portfolio Reset on Startup

When `trader_service.portfolio_source: alpaca` is enabled:

- startup reads account cash and positions from Alpaca
- local `position_snapshots` are overwritten with the broker portfolio
- mismatch validation happens after that reset

This means local portfolio state reflects the broker even when startup later aborts.

## Global Halt Runbook

Global halt state lives in `config_kv`:

- `halt`: `true` or `false`
- `halt_reason`: operator-supplied text
- `halt_updated_at`: UTC timestamp

Set a halt before maintenance, suspected broker mismatch, or any manual safety stop:

```bash
uv run python run_operator.py configs/example.yaml halt set --reason "manual safety test"
uv run python run_operator.py configs/example.yaml health --json
```

While halted, live `run_cycle` records `run_events.status='halted'` with `error_message='global_halt'` and submits no
orders. Clear the halt only after the event store, broker account, and open-order state are understood:

```bash
uv run python run_operator.py configs/example.yaml halt clear
uv run python run_operator.py configs/example.yaml status --json
```

## Recovery Decision Tree

1. Run `status --json` and `health --json`.
2. If halted, inspect `halt.reason` and confirm whether the stop is still intended.
3. If market data is missing or stale, restart stream/backfill/replay before clearing operational blockers.
4. If local open orders are stale, run `open-orders --json`, then `reconcile --json`.
5. If Alpaca reports positions or orders outside the configured universe, resolve the broker-side state manually and
   restart the service.
6. If latest run or cycle failed, inspect `run_events.error_message`, service logs, and the corresponding order/fill
   events before restarting.

## Expected Live Logs

For a healthy live startup, the important milestones are:

- startup recovery summary
- broker account summary with `reason=startup_portfolio_sync`
- local portfolio reset from Alpaca
- trader service start / LISTEN on market-data notifications
- cycle order summary

For order-level diagnosis, expect explicit logs for:

- risk rejections
- order created
- order validated
- order submitted
- broker response
- periodic order reconciliation summary when enabled

## Verification

- Trader service logs show `Trader service start` and `Cycle start`.
- Backfill/stream logs show `Market data ...` entries and (for Postgres) `NOTIFY` events.
- Event store tables populate: `stock_bar_events`/`crypto_bar_events`, `signal_events`, `position_snapshots`.

## Notes

- `run_trader_service.py`, `python -m trader.backtest`, and `python -m trader.cycle` are not supported strategy-bearing entrypoints.
- Use user-owned injected wrapper scripts such as `examples/run_injected_trader_service.py` and `examples/run_injected_backtest.py`.
- API/UI backtest flows are compatibility surfaces, not the primary operations path. They do not yet expose the full
  assumptions and strategy/risk injection surface available through wrapper scripts.
