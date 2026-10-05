# Backtesting

This guide explains how backtesting works in this system, what data it uses, and how to interpret the output summary.

## What a backtest does

A backtest replays the trading cycle over historical bar timestamps that already exist in the event store. It does
not call Alpaca during the run and it does not write new bar data. Backtests force the internal broker path, even if
the input YAML references Alpaca. Bars are loaded once into memory and treated as immutable inputs for the strategy
and signal generator. Bar-backed strategies receive a typed replay reader over those loaded bars, so strategy history
does not issue a database query for every decision.

## Preconditions

- Historical bars must already exist in Postgres (`stock_bar_events` or `crypto_bar_events`).
- Your YAML config must include a `backtest` section with `start`, `end`, and `timeframe`.
- Symbols and asset class must match the stored data.

## Config basics

<!-- verified: config -->
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
      latest_prior_max_age_seconds: 86400
      decision_clock: observed_bar
      valuation_clock: observed_or_carry
      indicator_window: observed_bars
      fill_eligibility: priced_observed_bar
      zero_activity_bar_policy: signal_eligible
      performance_clock: elapsed_time
```
Timeframes are normalized, so `1h`, `1Hour`, and `1H` are treated the same.
If `avg_price` is omitted, the backtest uses the first bar close in the window for that symbol.
`initial_cash` seeds the portfolio cash balance for the backtest.
If `backtest.assumptions` is omitted, the defaults use full fills, zero fees, zero slippage, no effective latency,
latest-prior-bar fallback up to 24 hours, and last-known-price carry-forward enabled. These defaults are recorded in
the run assumptions and review scope so a comparison cannot silently mix data-clock or execution policies.

The data policy is explicit. Decisions and indicator windows use observed provider bars; a missing exact bar may use a
prior bar only within `latest_prior_max_age_seconds`; valuation may carry a known price when enabled; and a priced
observed bar is required for a fill. Provider-emitted zero-volume or zero-trade bars remain observations and are
signal-eligible. An absent provider bar is not synthesized from a wall-clock interval.

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
     `fill_events`, `position_snapshots`, the ordered `risk_compositions` snapshot, and
     per-manager `risk_decisions` when order evidence is enabled.
6) Compute a summary from the in-memory portfolio and the latest bar prices.

## Replay bar-read boundary

`BacktestRunner` builds one `InMemoryRecentBarReader` from the already-loaded bar window and passes it through the
cycle strategy boundary. Each request is typed with the symbol, asset class, timeframe, decision timestamp, and
positive lookback limit. Reads are inclusive of the decision timestamp, latest-first, and cannot expose future bars;
warmup bars remain available without creating extra decision cycles. The reader reuses the loaded `Bar` objects and
records request and returned-row counts for qualification logs.

Ordinary runtime cycles leave this reader unset. Maintained strategies then use their existing event-store query path,
so the replay optimization does not alter production market-data behavior.

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
- `evidence_coverage`: Whether signal, order, fill, and position evidence was `recorded`, `not_recorded`, or
  `not_applicable`. A recorded stream may legitimately contain zero rows.
- `review_scope`: Producer-owned comparison identity covering the replay bars, benchmark construction, initial
  portfolio state, and execution/data assumptions.
- `variant`: Explicit strategy and parameter identity that may vary inside a matching review scope.

## Risk evidence

Each run publishes the ordered risk-manager composition with stable manager IDs, manager types, catalogue version,
typed parameters, and a deterministic composition fingerprint. For every candidate order, the runtime records one
decision row per manager that actually evaluated it. Rows preserve run/session/cycle/order identity, decision time,
manager position, an allowlisted reason code, the outcome (`approved`, `transformed`, or `rejected`), and normalized
before/after order fields when an approved order is changed. A rejected row keeps the candidate in `before_order` and
leaves `after_order` absent while recording the manager's block reason. Later managers are absent when an earlier
manager short-circuits an order, preserving the actual chain semantics.

The Console summary counts evaluations, approvals, transformations, rejections, and risk blocks, and the review page
renders the composition and a bounded ordered trace. A broker rejection is represented by broker/order lifecycle
evidence rather than a risk decision. A no-signal or zero-trade run can still show its composition with zero decision
rows. Legacy runs without these tables are labelled `risk_evidence_status=unavailable`; the Console never infers a
risk block from a missing fill.

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

Annualization uses the observed equity timestamps. CAGR uses the full elapsed replay window; volatility, Sharpe,
Sortino, and relative metrics use the median positive observation interval. The configured `timeframe` remains part of
data identity and query selection, but it is not treated as proof of a regular observation cadence.

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
- Results depend on the stored bars, their provider semantics, and the declared data policy; mismatched timeframes
  yield sparse signals.
- Sparse observations, provider-wide gaps, and zero-activity bars remain distinguishable in warnings and provenance;
  a backtest must not describe every absent wall-clock minute as ingestion loss.
- Bar data is read-only during a backtest; only trading events are persisted.
- Lifecycle IDs and signal-to-order links are deterministic when the relevant evidence exists. Historical rows created
  before those fields were added remain unlinked and are surfaced as unknown by the Console read contract.
- `review_scope.scope_fingerprint` is the admission key for cross-run comparison. It excludes strategy and parameter
  variants, which are represented separately. Legacy persisted results without this scope are readable but unavailable
  for compatibility-gated cohorts.

## Running a backtest

Backtest execution produces Trader domain results and event-store evidence. It has no Superset dependency, dashboard
callback, or publication step. External database consumers may inspect the persisted tables and producer-owned typed
views when those surfaces have been explicitly populated; any consumer-specific connection, dataset registration, or
visualisation setup belongs outside the backtest runtime.

<!-- verified: integration:postgres tests/trader/backtest/test_backtest.py tests/trader/backtest/test_backtest_api.py -->
```bash
uv run python examples/run_injected_backtest.py
uv run python examples/run_library_backtest.py
```

To exercise the checked-in deterministic sample workflow:

<!-- verified: integration:postgres tests/trader/backtest/test_backtest.py tests/trader/backtest/test_backtest_api.py -->
```bash
docker compose -f docker-compose.postgres.yml up -d
uv run python examples/load_sample_market_data.py
uv run python examples/run_reproducible_backtest.py
```

The reproducible runner exports:

- `artifacts/reproducible_backtest/result.json`
- `artifacts/reproducible_backtest/equity_curve.csv`
- `artifacts/reproducible_backtest/trades.csv`

The reproducible runner also persists one aggregate `metrics_snapshots` record for the completed run. The snapshot
contains the serialized result, including the declared review scope, variant, assumptions, evidence coverage, summary
metrics, and curve/trade exports. Per-cycle execution evidence remains in the dedicated event tables; the aggregate
snapshot is the producer-owned summary used by the Console read contract.

Backtest cycle identifiers include the owning run ID and the decision symbol universe. This keeps overlapping replays
isolated while preserving deterministic retry IDs within one run. Ordinary trading cycle identifiers retain their
existing strategy-and-timestamp identity.

## Canonical research backtests

The research layer uses the same `BacktestRunner`, but admission and evidence are Postgres-first. A canonical run starts
from validated implementation and strategy/risk specifications, binds one Data Agent manifest through an immutable
backtest specification, and writes a `backtest_run` research artifact plus typed Postgres projection. Parameter studies
use the provider-neutral optimization ledger rather than event-store experiment tables or filesystem bundles.

See [Research Workflows](../../../docs/workflows/research.md) for the MCP execution graph.

To see per-cycle logs, set:

<!-- verified: config -->
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
