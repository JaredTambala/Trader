# Broker, Execution, and Portfolio Component

The broker/execution/portfolio component turns approved orders into broker responses or simulated fills, then updates
cash and positions.

## Component responsibilities

- Normalize order submission across internal, noop, and Alpaca paper brokers.
- Preserve deterministic order IDs and lifecycle records.
- Apply backtest fee/slippage assumptions.
- Record fills with effective execution prices.
- Update portfolio cash and positions.
- Refresh live portfolio truth from the broker when configured.
- Support startup reconciliation for broker-open orders.
- Support periodic open-order reconciliation in live loop/realtime service modes.

## Backtest operation

Backtests always use a deterministic `InternalPaperBroker` constructed by `BacktestRunner`, even if the base YAML says
`broker.type: alpaca`.

Backtest fill model:

- Defaults preserve historical behavior: full fills, zero fees, zero slippage, no effective latency.
- `raw_fill_price` is the unadjusted bar-close reference.
- `fill_price` is the adjusted accounting price after slippage.
- Buy slippage: `adjusted_price = raw_price * (1 + bps / 10000)`.
- Sell slippage: `adjusted_price = raw_price * (1 - bps / 10000)`.
- Slippage amount: `abs(adjusted_price - raw_price) * fill_qty`.
- Fee amount: `max(minimum_fee, fixed_per_order + abs(fill_qty * adjusted_price) * bps / 10000)`.

Portfolio accounting:

- Buys reduce cash by notional plus fees.
- Sells increase cash by proceeds minus fees.
- Average prices update across multiple buys.
- Realized PnL uses adjusted fill prices and fees.
- The benchmark remains frictionless.

Latency is recorded as an assumption. It does not sleep the process or change bar selection.

Backtest fills are written with enough fields to reconstruct modeled execution: `raw_fill_price`, `fill_price`,
`slippage_amount`, and `fee_amount`. The accounting is deterministic and cost-aware, but it remains bar-based rather
than exchange-microstructure simulation.

## Live operation

Live paper trading uses the broker selected by the wrapper/config. Alpaca-backed operation is the main live path.

Live broker flow:

1. Risk-approved orders are submitted to the broker adapter.
2. Broker-specific statuses are normalized into canonical states.
3. `order_events` records lifecycle transitions.
4. `fill_events` records observed fills.
5. Alpaca-backed portfolio mode refreshes account cash and positions from the broker.
6. Local `position_snapshots` records the refreshed state.

Startup recovery:

- `resume` repairs stale local-open orders, adopts in-scope broker-open orders, and allows startup when acceptable.
- `fail_closed` aborts startup if unresolved broker-open orders remain in scope.
- `run_order_recovery.py clean-start` closes local open order records only and does not cancel broker orders.
- `run_operator.py CONFIG reconcile` runs resume-style reconciliation from the unified operator CLI.
- `TraderService` can poll broker order state periodically via `trader_service.order_reconciliation_interval_seconds`.

Broker-backed live portfolio truth:

- Alpaca account state is authoritative for current cash and positions when `portfolio_source: alpaca`.
- Local snapshots are audit records and runtime context, not the source of current broker truth.
- Positions outside the configured universe cause startup failure.
- `portfolio_source: db` avoids per-cycle broker account/position reads and uses local snapshots as runtime state.
- Metrics sampling defaults to local snapshots to avoid duplicate broker account reads.

Live order history is append-only. Broker responses are normalized into local `order_events`; observed fills are
recorded in `fill_events`; refreshed cash and holdings are recorded in `position_snapshots`. Reconciliation appends new
order/fill facts; it never edits or deletes prior lifecycle records. Alpaca paper state is the best available live
account truth in this system, but paper fills are not proof of live venue fill quality.

Broker contracts:

- Required capability: `submit_orders`.
- Optional account capability: `get_account`, `get_positions`.
- Optional order lookup capability: `list_orders`, `get_order_by_id`.
- Optional order action capability: `cancel_order`.
- Optional reconciliation capability: `reconcile_orders`.

Canonical broker response fields are `client_order_id`, `status`, `broker_order_id`, `symbol`, `asset_class`, `side`,
`qty`, `order_type`, `created_at`, `fill_qty`, `fill_price`, `fill_ts`, and `rejection_reason`.

## Configurability

Broker config:

```yaml
broker:
  type: alpaca
  time_in_force: gtc
  internal:
    reject_probability: 0.0
    fill_delay_ms_mean: 0
    fill_delay_ms_stddev: 0
    fill_qty_fraction_mean: 1.0
    fill_qty_fraction_stddev: 0.0
    rng_seed: null
```

Alpaca config:

```yaml
alpaca:
  api_key: ${ALPACA_API_KEY}
  secret_key: ${ALPACA_SECRET_KEY}
  base_url: ${ALPACA_BASE_URL}
  data_base_url: https://data.alpaca.markets
```

Live portfolio config:

```yaml
trader_service:
  startup_recovery_mode: resume
  portfolio_source: alpaca
  order_reconciliation_interval_seconds: 60
  initial_cash: 100000
  initial_positions:
    - symbol: BTC/USD
      qty: 0
```

Backtest execution-cost config:

```yaml
backtest:
  assumptions:
    fill_model: full_fill
    latency_ms: 0
    fees:
      fixed_per_order: 0.10
      bps: 0
      minimum_fee: 0.10
    slippage:
      bps: 10
```

`TraderService` keeps one persistent broker instance. Startup recovery owns initial order-state reconciliation, periodic
reconciliation owns conservative open-order polling, broker-backed portfolio mode refreshes positions at startup,
per-cycle when configured, and after confirmed Alpaca fills. Refresh logs include reason labels such as
`startup_portfolio_sync`, `cycle_portfolio_source_alpaca`, `post_fill_sync`, and `periodic_order_reconciliation`.

## Current limits

- Broker interactions are synchronous in the cycle path.
- No multi-broker router.
- No order management service separated from the strategy process.
- Paper Alpaca behavior is not a substitute for production venue execution.
- Backtests do not simulate queue position, intrabar liquidity, stochastic slippage, borrow costs, or exchange
  microstructure.
