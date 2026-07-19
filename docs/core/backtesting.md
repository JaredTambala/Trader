# Backtesting Guide

This guide explains how backtesting works in this system, what data it uses, and how to interpret the output summary.

## What a backtest does

A backtest replays the trading cycle over historical bar timestamps that already exist in the event store. It does
not call Alpaca during the run and it does not write new bar data. Backtests force the internal broker path, even if
the input YAML references Alpaca. Bars are loaded once into memory and treated as immutable inputs for the strategy
and signal generator.

## Preconditions

- Historical bars must already exist in Postgres (`stock_bar_events` or `crypto_bar_events`).
- Your YAML config must include a `backtest` section with `start`, `end`, and `timeframe`.
- Symbols and asset class must match the stored data.

## Config basics

```yaml
backtest:
  start: "2026-01-21T00:00:00Z"
  end: "2026-01-21T00:30:00Z"
  timeframe: 1Min
  symbols:
    - BTC/USD
  asset_class: crypto
  max_runs: null
  log_cycle_details: false
  initial_cash: 100000
  initial_positions:
    - symbol: BTC/USD
      qty: 0.5
      avg_price: 40000
  assumptions:
    fill_model: full_fill
    latency_ms: 0
    fees:
      fixed_per_order: 0.10
      bps: 0
      minimum_fee: 0.10
    slippage:
      bps: 10
    data:
      allow_latest_prior_bar: true
      allow_price_carry_forward: true
```
Timeframes are normalized, so `1h`, `1Hour`, and `1H` are treated the same.
If `avg_price` is omitted, the backtest uses the first bar close in the window for that symbol.
`initial_cash` seeds the portfolio cash balance for the backtest.
If `backtest.assumptions` is omitted, the defaults preserve the earlier behavior: full fills, zero fees, zero
slippage, no effective latency, latest-prior-bar fallback allowed, and last-known-price carry-forward enabled.

## Execution flow

1) Load YAML config and connect to the Postgres event store.
2) Load bars for the requested symbols/timeframe into memory (including lookback bars for indicators).
3) Optionally seed `initial_positions` and `initial_cash` into `position_snapshots` at `backtest.start`.
4) Build an in-memory market data source and signal generator.
5) For each timestamp in the backtest window:
   - Run a cycle **per symbol that has a bar at that timestamp**.
   - Each cycle uses `decision_ts=ts` and `ingest_market_data=false`.
   - Fetch the bar for that symbol/timestamp from the in-memory bar set.
   - Generate signals for that symbol and execute them through a deterministic internal paper broker.
   - Apply adjusted fill prices, slippage, and fees to the shared in-memory portfolio.
   - Persist `runs` (session), `run_events` (cycles), `signal_events`, `order_events`,
     `fill_events`, and `position_snapshots`.
6) Compute a summary from the in-memory portfolio and the latest bar prices.

## Output summary fields

The backtest returns and logs a summary with portfolio context:

- `total_runs`: Number of cycle executions.
- `success_runs` / `failed_runs`: Cycle outcomes.
- `duration_seconds`: Wall-clock runtime of the backtest.
- `position_count`: Number of open positions at the end.
- `long_positions` / `short_positions`: Count of long and short positions.
- `net_qty`: Sum of position quantities (long minus short).
- `gross_qty`: Sum of absolute position quantities.
- `net_notional`: Sum of `qty * last_price` (or `avg_price` if no last price).
- `gross_notional`: Sum of `abs(qty * last_price)` (or `avg_price` fallback).
- `assumptions`: The explicit fill, fee, slippage, latency, and data assumptions used.
- `warnings`: Non-fatal data/execution warnings gathered during the run.
- `trades`: Per-fill trade records with effective fill price, raw fill price, fees, slippage, and realized PnL.
- `realized_pnl`: Net realized PnL from closed trades.
- `total_fees` / `total_slippage`: Aggregate execution-cost totals across the run.

Per-position details:

- `qty`: Final position quantity.
- `avg_price`: Average entry price (if known).
- `last_price`: Latest bar close for the symbol/timeframe (if available).
- `last_ts`: Timestamp of the latest bar used for the price.
- `market_value`: `qty * last_price`.
- `unrealized_pnl`:
  - Long: `(last_price - avg_price) * qty`
  - Short: `(avg_price - last_price) * abs(qty)`

If a `last_price` is missing, `market_value` and `unrealized_pnl` will show as `<unset>`.

## Performance metric definitions

These metrics are computed from an **equity curve** built at each backtest timestamp:

```
equity = cash_balance + sum(position_qty * last_price)
```

If a symbol has no bar at a given timestamp, the last known price is carried forward.

### Buy-and-hold baseline

The buy-and-hold benchmark is constructed at `backtest.start`:

- Start with any `initial_positions`.
- Invest `initial_cash` equally across configured symbols using the first available bar at or after `start`.
- Hold those quantities for the full window (no trades).

### Return series

Per-period return series:

```
r_t = (equity_t / equity_{t-1}) - 1
```

Annualization uses a calendar year (365 days) and the configured `timeframe`.

### Portfolio-level metrics

- **Total return**: `(end_equity / start_equity) - 1`
- **CAGR**: `(end_equity / start_equity)^(1/years) - 1`
- **Volatility**: `std(r_t) * sqrt(periods_per_year)`
- **Sharpe**: `mean(r_t) / vol * sqrt(periods_per_year)` (risk-free rate = 0)
- **Sortino**: `mean(r_t) / downside_vol * sqrt(periods_per_year)`
- **Max drawdown**: `max((peak - equity)/peak)`
- **Drawdown duration**: longest consecutive periods below the prior peak
- **Calmar**: `CAGR / max_drawdown`
- **Ulcer index**: `sqrt(mean(drawdown^2))`
- **Avg net exposure**: mean of `sum(qty * price)` across timestamps
- **Avg gross exposure**: mean of `sum(abs(qty * price))` across timestamps
- **Avg invested %**: mean of `gross_exposure / equity`

### Relative metrics vs buy-and-hold

- **Tracking error**: `std(r_strategy - r_benchmark) * sqrt(periods_per_year)`
- **Information ratio**: `mean(excess) / tracking_error * sqrt(periods_per_year)`
- **Beta**: `cov(r_strategy, r_benchmark) / var(r_benchmark)`
- **Alpha**: `(mean(r_strategy) - beta * mean(r_benchmark)) * periods_per_year`

## How to interpret the results

- Use `total_runs` as a proxy for how many bars were processed.
- A non-zero `failed_runs` means at least one cycle raised an exception.
- `net_qty` and `gross_qty` help you understand exposure and position sizing.
- `net_notional` is directional exposure; `gross_notional` is total exposure.
- `unrealized_pnl` reflects mark-to-market based on the latest bar close, not fills.

## Important limitations

- Backtests use the internal broker, not live venue execution.
- The benchmark remains frictionless even when strategy fills include fees or slippage.
- Fill behavior is deterministic and audit-friendly; stochastic slippage remains out of scope.
- Results depend on the stored bars and timeframe; mismatched timeframes yield sparse signals.
- Bar data is read-only during a backtest; only trading events are persisted.

## Running a backtest

```bash
uv run python examples/run_injected_backtest.py
uv run python examples/run_library_backtest.py
```

To exercise the checked-in deterministic sample workflow:

```bash
docker compose -f docker-compose.postgres.yml up -d
uv run python examples/load_sample_market_data.py
uv run python examples/run_reproducible_backtest.py
```

The reproducible runner exports:

- `artifacts/reproducible_backtest/result.json`
- `artifacts/reproducible_backtest/equity_curve.csv`
- `artifacts/reproducible_backtest/trades.csv`

## Canonical research backtests

The research layer uses the same `BacktestRunner`, but admission and evidence are Postgres-first. A canonical run starts
from validated implementation and strategy/risk specifications, binds one Data Agent manifest through an immutable
backtest specification, and writes a `backtest_run` research artifact plus typed Postgres projection. Parameter studies
use the provider-neutral optimization ledger rather than event-store experiment tables or filesystem bundles.

See [Research Agent Workflows](../research_agents/workflows.md) for the MCP execution graph.

To see per-cycle logs, set:

```yaml
backtest:
  log_cycle_details: true
```
Timeframes are normalized, so `1h`, `1Hour`, and `1H` are treated the same.

## Runtime contract

- `python -m trader.backtest configs/example.yaml` is not a supported strategy-bearing entrypoint.
- Use an injected wrapper such as `examples/run_injected_backtest.py`.
- Use `examples/run_library_backtest.py` if you want the maintained `trader_standard` trend-following,
  mean-reversion, or Bollinger Band compositions.
- API/UI-triggered backtests exist as a compatibility path and use the shared serializer, but the primary research
  workflow is either injected Python wrappers or the `trader_standard` research CLI. The API request shape does not
  expose the full backtest assumptions surface yet, so API-triggered backtests use default assumptions.
