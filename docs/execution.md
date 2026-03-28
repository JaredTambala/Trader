# Execution (Phase 1)

This document describes the execution loop semantics, idempotency rules, and order lifecycle
expectations for Phase 1.

For architecture-level review, this operational reference is complemented by:

- `docs/system_architecture.md`
- `docs/runtime_hot_path_and_reconciliation.md`

## Architecture (Two Processes)

Stage 0 runs as two long-lived processes:

1) **Market data streamer** (`uv run python run_market_data_stream.py configs/example.yaml`)
   - Connects to Alpaca websocket feeds.
   - Persists incoming bars to the event store (idempotent).
   - Emits a trigger that “new market data is available”.

2) **Trader** (`uv run python examples/run_injected_trader_service.py`)
   - Subscribes to triggers and runs the trading cycle single-flight.
   - Generates signals, applies risk checks, and submits orders (paper).
   - Persists all events (signals, orders, fills, positions, runs).

### Trigger mechanism

For Task 0.6 we use Postgres `LISTEN/NOTIFY`:

- Streamer inserts a new bar (unique on `(symbol, timeframe, ts, source)`).
- If the insert succeeds (i.e., it was not a duplicate), streamer performs `NOTIFY` with a small
  payload (`symbol`, `timeframe`, `ts`, `asset_type`).
- Backfill sends a summary `NOTIFY` per symbol once the batch completes.
- Trader `LISTEN`s and runs a coalesced single-flight cycle.

This avoids shared in-process state and supports separate container/process lifecycles.

## Real Trading Execution Loop

The lowest-level execution primitive is `run_cycle(...)`. In supported Phase 1 usage, it is called
from an injected runtime such as `TraderService`, where the strategy and risk manager are supplied
directly from user code.

A single cycle performs:

1) Ensure a `runs` session exists (`status=started`).
2) Record `run_events` cycle start (`status=started`).
3) Ingest market data (polling or streaming-lite) and persist bar events.
   - If ingestion yields no new events, the cycle loads the latest bars from the event store.
   - For streamer/backfill workflows, set `market_data.source: noop` and rely on the event store lookup.
4) Skip trading if market data is missing or stale.
5) Generate signals (Strategy).
6) Validate signals (RiskManager).
7) Submit orders (Broker).
8) Persist a portfolio snapshot (based on executed order intents).
9) Record `run_events` cycle finish (`status=success|failed`).
10) If this is a one-off run, record `runs` finish (`status=success|failed`).

## Backtest Execution Loop

`BacktestRunner` replays cycles over a timestamp window using in-memory bars loaded from the event
store. It does **not** ingest or mutate bar data during the run.

1) Load bars for the requested symbols/timeframe into memory (including indicator lookback bars).
2) Optionally seed `initial_positions` into `position_snapshots` at `backtest.start`.
3) Build an in-memory market data source.
4) For each timestamp in the window:
   - Run `run_cycle` **per symbol that has a bar at that timestamp** with `decision_ts=ts`,
     `ingest_market_data=false`, an in-memory portfolio, and the injected strategy/risk manager.
   - Fetch the bar for that symbol/timestamp from memory (not from Alpaca or Postgres).
   - Generate signals for that symbol and apply order intents in memory.
   - Persist trading events (`run_events`, `signal_events`, `order_events`, `position_snapshots`).

Errors during a cycle are captured in `run_events.error_message` and the cycle is marked `failed`.

## Backtest vs Real Trading (Key Differences)

- **Data source**: backtest uses historical bars from Postgres loaded into memory; live cycles use Alpaca (or streamer/backfill) as the source of truth.
- **Bar writes**: backtest does not write bar events; live cycles persist bar events as they arrive.
- **Portfolio state**: backtest keeps portfolio state in memory during the run; live Alpaca cycles refresh portfolio state from the broker and persist snapshots for auditability.
- **Time semantics**: backtest uses deterministic `decision_ts`; live cycles use wall-clock time for freshness checks.
- **External side effects**: backtest does not talk to brokers; live cycles submit orders to the broker.

## Idempotency & Identifiers

- `run_id` is based on wall clock: derived from `run_type` and the run session `started_at`.
- `cycle_id` is deterministic: derived from `strategy.id` and the cycle `decision_ts`.
- `client_order_id` is deterministic: derived from `cycle_id`, `symbol`, `side`, and `target_qty`.

These IDs ensure retries do not create duplicate orders. The canonical formats are documented in
`docs/schema.md`.

## Order Lifecycle (Implemented)

The canonical order state machine for Stage 0:

- `created` → `validated` → `submitted` → `accepted` → `partially_filled` → `filled`
- Terminal states: `rejected`, `canceled`, `expired`, `error`

`error` indicates an uncertain broker outcome and must trigger reconciliation before retrying.

### Alpaca status mapping

Alpaca order statuses are mapped into canonical states by `AlpacaPaperBroker`:

| Alpaca status | Canonical status |
| --- | --- |
| `new`, `pending_new`, `pending_replace`, `replaced` | `submitted` |
| `accepted`, `accepted_for_bidding` | `accepted` |
| `partially_filled` | `partially_filled` |
| `filled`, `done_for_day` | `filled` |
| `canceled`, `pending_cancel` | `canceled` |
| `expired` | `expired` |
| `rejected` | `rejected` |
| `held`, `suspended`, `stopped` | `error` |

## Startup Recovery and Reconciliation (Implemented)

The primary runtime reconciliation flow is now service startup, not an ad hoc broker method call.

`TraderService` runs startup recovery before beginning the live loop. The supported startup recovery
modes are:

- `resume`: inspect broker-open orders, repair local `order_events`, adopt in-scope broker-open
  orders into local state, and close stale local-open orders as `reconciled_missing`
- `fail_closed`: perform the same inspection but abort if broker-open orders remain in the configured universe

Startup recovery is local-state reconciliation against the broker. It is not a broker-execution mode.

The runtime behavior is:

- read local open `order_events`
- read broker open orders for the configured universe
- append status transitions to `order_events`
- append `fill_events` when reconciliation reveals fills
- adopt broker-open orders into local state when they are in scope and missing locally
- close stale local-open orders that no longer exist broker-side

`run_order_recovery.py clean-start` is a separate operator tool that closes local open orders in the
configured universe. It does not cancel broker orders.

## Live Portfolio Semantics

For Alpaca-backed live trading:

- Alpaca is the source of truth for portfolio state.
- Startup sync resets local `position_snapshots` from Alpaca before mismatch validation.
- If the broker account contains positions outside the configured symbols or asset class, the runtime
  fails closed.
- When fills occur, the runtime refreshes portfolio state from the broker rather than applying local
  intent-based portfolio mutations.

Equivalent Alpaca forms such as `BTCUSD` and enum-style asset classes like `assetclass.crypto` are
normalized into the canonical runtime model before validation.

## Status

The deterministic run lifecycle and staleness checks are implemented in `trader.cycle`.
The runtime service is implemented in `trader.trader_service` (once, loop, and realtime modes).
The supported integration model is direct strategy/risk injection from user-owned wrapper scripts.
The full broker lifecycle and reconciliation are implemented in Task 0.8 via `AlpacaPaperBroker`.

---

## Design Primitives: Signal → SignalGenerator → Strategy

### Indicator
`Indicator` computes derived values from OHLCV bars (e.g., SMA, RSI). Indicators return a series
aligned with the input bars and can be composed inside Signals.

### Signal
`Signal` is the smallest unit of decision logic. It takes a window of market data (OHLCV bars)
and computes a scalar value that can be interpreted by a Strategy. Signals are stateless and
reusable (e.g., SMA, RSI, ML model score).

---

## Architecture Review (Object/Class Level)

This section provides a clear, end‑to‑end review of the mechanisms that support market data ingestion,
strategy instantiation, indicator‑driven signals, order generation, and order filling across backtest
and realtime modalities.

### Market data ingestion

**Primary classes**
- `AlpacaMarketDataSource`: polling source for historical/latest bars (alpaca‑py).
- `MarketDataStreamRunner`: websocket consumer that writes bars to Postgres and emits NOTIFY.
- `MarketDataIngestor`: persists bar events and exposes `ingest()` / `ingest_stream()` helpers.

**Realtime flow**
1) Websocket delivers bar → `MarketDataStreamRunner._handle_bar`.
2) Bar is persisted to `stock_bar_events` / `crypto_bar_events`.
3) A minimal NOTIFY payload is emitted (`symbol`, `timeframe`, `ts`, `asset_class`, `source`).

**Polling flow**
1) `MarketDataIngestor.ingest()` calls the configured `MarketDataSource.fetch()`.
2) New bars are persisted to the event store.
3) The events are returned to the cycle for processing.

### Strategy definition & instantiation

**Primary classes**
- `Strategy` (interface): produces broker‑ready orders.
- `SimpleStrategy`: SMA crossover strategy built on a signal generator.
- `NoOpStrategy`: produces no orders.

**Instantiation**
- User code instantiates `Strategy` and `RiskManager` objects directly and injects
  them into `run_cycle`, `TraderService`, or `BacktestRunner`.

### Signal generation & indicators

**Primary classes**
- `SignalGenerator`: interface for producing signals from bars.
- `SimpleBarsSignalGenerator`: reads bars from the event store and computes signals.
- `InMemoryBarsSignalGenerator`: uses preloaded bars for backtests.
- `SmaIndicator` + `SmaCrossoverSignal`: compute the SMA crossover signal.

**Flow**
1) Strategy invokes the `SignalGenerator`.
2) Generator loads the required bar window and computes indicator values.
3) Optional `indicator_events` are persisted when logging is enabled.

### Order generation & validation

**Primary classes**
- `RiskManager`: validates candidate orders.
- `Broker`: submits orders (paper or no‑op).

**Flow**
1) Strategy emits candidate orders.
2) Risk managers filter those orders through a `RiskPipeline` (rejects include `rejection_reason`).
3) Broker submission returns responses; `order_events` and `fill_events` are appended.
4) Runtime logs make the path explicit: created, validated, rejected, submitted, broker response.

### Order filling

**Primary classes**
- `InternalPaperBroker`: paper fills with optional tunables (latency, rejection rate, fill fraction).
- `NoOpBroker`: dry‑run mode, no fills.

**Flow**
- Fills are recorded as `fill_events`; order lifecycle is append‑only in `order_events`.

---

## Execution cycle (Backtest)

**Trigger**: deterministic timestamp replay over historical bars.

**Cycle steps**
1) Load all required bars into memory (including lookback windows).
2) Reuse the injected `Strategy` and `RiskManager` for the run.
3) For each timestamp and symbol with a bar:
   - Call `run_cycle` with `ingest_market_data=false` and the injected runtime objects.
   - Signals and orders are generated against in‑memory bars.
4) Persist run/cycle events and optional trading events.

**State**
- Portfolio is in‑memory for the run.
- Strategy state persists per symbol.
- Bars are **not** written during the backtest loop.

## Execution cycle (Realtime)

**Trigger**: Postgres LISTEN/NOTIFY from the stream process.

**Cycle steps**
1) Stream writes bar → emits NOTIFY.
2) Trader service de‑duplicates NOTIFY events per symbol/timeframe/asset class.
3) Trader service calls `run_cycle` with `ingest_market_data=false` and the injected runtime objects.
4) `run_cycle` reads the latest bars from the event store and processes signals/orders.

**State**
- Strategy and risk manager are persistent injected runtime objects for the service lifetime.
- Portfolio is loaded from snapshots each cycle (seeded once if configured).
- Bars are written by the stream process, not the trader service.

---

## Summary of modality differences

- **Triggering**: backtest is timestamp‑driven; realtime is NOTIFY‑driven.
- **Bar sourcing**: backtest uses in‑memory bars; realtime reads from Postgres after streaming writes.
- **Strategy lifetime**: both backtest and realtime reuse injected runtime objects supplied by user code.
- **Portfolio state**: backtest uses in‑memory portfolio; realtime reloads snapshots each cycle.
- **Latency**: realtime includes DB write/notify/read overhead; backtest is compute‑bound.

Examples:
- `SmaIndicator(period=N)` returns the SMA series for the last N bars.
- `SmaCrossoverSignal(short, long)` compares two SMA indicators and emits `+1/-1/0`.

### SignalGenerator
`SignalGenerator` is responsible for:
1) Pulling the required data from the event store.
2) Applying one or more Signals.
3) Returning a mapping of `symbol -> {signal_name: signal_value}`.

`SimpleBarsSignalGenerator` is the current implementation. It reads recent bars from
`stock_bar_events` or `crypto_bar_events`, applies all configured Signals, and returns computed
values per symbol. It does not decide trades; it only computes signal values.

### Strategy
`Strategy` consumes SignalGenerator outputs and market context to produce broker-ready
**order intents**. Strategies are responsible for:
- Choosing which signals matter (e.g., a primary signal).
- Translating signal values into order intents (side/qty/type).
- Recording `signal_events` for traceability.
- Leaving risk filtering to the separate `RiskManager` / `RiskPipeline` layer.

`SimpleStrategy` is the current minimal implementation:
- If the primary signal > 0 ⇒ emit a **buy** market order.
- If the primary signal < 0 ⇒ emit a **sell** market order.
- If the primary signal = 0 ⇒ emit nothing.

---

## Remaining Gaps

1) **Health/status runtime surface**  
   The health/status API remains incomplete and still needs runtime-backed endpoints.

2) **Backtest execution realism**  
   Internal broker realism is present, but richer statistical fill modeling is tracked separately.

3) **Fill-driven accounting depth**  
   Fill-driven synchronization is implemented for Alpaca runtime flows, but portfolio/performance
   accounting can still be tightened further across all execution modes.

4) **Interface/deployment work**  
   UI, Superset, package split, and deployment productization are intentionally out of Phase 1.

## Follow-Up Focus

1) Keep extending the direct-injection library workflow.
2) Finish the retained execution/runtime safety work.
3) Keep deferred UI and deployment concerns out of the active Phase 1 path.
