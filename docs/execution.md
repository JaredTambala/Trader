# Execution (Stage 0)

This document describes the execution loop semantics, idempotency rules, and order lifecycle
expectations for Stage 0.

## Architecture (Two Processes)

Stage 0 runs as two long-lived processes:

1) **Market data streamer** (`python -m trader.market_data_stream configs/example.yaml`)
   - Connects to Alpaca websocket feeds.
   - Persists incoming bars to the event store (idempotent).
   - Emits a trigger that “new market data is available”.

2) **Trader** (`python -m trader.trader_service configs/example.yaml`)
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

The entry point is `python -m trader.cycle configs/example.yaml`, which performs a single cycle:

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

`python -m trader.backtest configs/example.yaml` replays cycles over a timestamp window using in-memory bars
loaded from the event store. It does **not** ingest or mutate bar data during the run.

1) Load bars for the requested symbols/timeframe into memory (including indicator lookback bars).
2) Optionally seed `initial_positions` into `position_snapshots` at `backtest.start`.
3) Build an in-memory market data source and signal generator.
4) For each timestamp in the window:
   - Run `run_cycle` **per symbol that has a bar at that timestamp** with `decision_ts=ts`,
     `ingest_market_data=false`, and an in-memory portfolio.
   - Fetch the bar for that symbol/timestamp from memory (not from Alpaca or Postgres).
   - Generate signals for that symbol and apply order intents in memory.
   - Persist trading events (`run_events`, `signal_events`, `order_events`, `position_snapshots`).

Errors during a cycle are captured in `run_events.error_message` and the cycle is marked `failed`.

## Backtest vs Real Trading (Key Differences)

- **Data source**: backtest uses historical bars from Postgres loaded into memory; live cycles use Alpaca (or streamer/backfill) as the source of truth.
- **Bar writes**: backtest does not write bar events; live cycles persist bar events as they arrive.
- **Portfolio state**: backtest keeps portfolio state in memory during the run; live cycles reload from snapshots each cycle.
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

## Reconciliation (Implemented)

`AlpacaPaperBroker.reconcile_orders(since_ts=...)` refreshes open orders and appends any status
transitions to `order_events`. When an order transitions to `filled` (or `partially_filled`), a
matching `fill_events` record is written as well.

The reconciliation flow:

- Fetch broker order status for recent `submitted|accepted|partially_filled|error` orders.
- Persist status transitions as append-only `order_events`.
- Record fills in `fill_events`.
- (Positions are still derived from order intents in Stage 0; fill-driven positions are a later task.)

## Status

The deterministic run lifecycle and staleness checks are implemented in `trader.cycle`.
The trader process is implemented in `trader.trader_service` (loop and realtime modes).
Task 0.6 introduces a real strategy implementation (SMA) with configurable window size.
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
- **Backtest**: `BacktestRunner` constructs one `Strategy` per symbol and reuses it across all cycles.
- **Realtime**: `TraderService` caches `Strategy` instances by `(symbol, timeframe, asset_class)` and
  reuses them per NOTIFY trigger.

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
2) Risk manager validates each order (rejects include `rejection_reason`).
3) Broker submission returns responses; `order_events` and `fill_events` are appended.

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
2) Build per‑symbol `Strategy` instances (persistent for the run).
3) For each timestamp and symbol with a bar:
   - Call `run_cycle` with `ingest_market_data=false` and the persistent `Strategy`.
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
3) Trader service calls `run_cycle` with `ingest_market_data=false` and cached `Strategy`.
4) `run_cycle` reads the latest bars from the event store and processes signals/orders.

**State**
- Strategy is cached per symbol/timeframe/asset class.
- Portfolio is loaded from snapshots each cycle (seeded once if configured).
- Bars are written by the stream process, not the trader service.

---

## Summary of modality differences

- **Triggering**: backtest is timestamp‑driven; realtime is NOTIFY‑driven.
- **Bar sourcing**: backtest uses in‑memory bars; realtime reads from Postgres after streaming writes.
- **Strategy lifetime**: both now persist strategy instances (per symbol in backtest, cached in realtime).
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
`Strategy` consumes SignalGenerator outputs (and, in future, portfolio state) to produce
broker-ready **order intents**. Strategies are responsible for:
- Choosing which signals matter (e.g., a primary signal).
- Translating signal values into order intents (side/qty/type).
- Recording `signal_events` for traceability.
- Applying risk rules (currently embedded via a RiskManager instance).

`SimpleStrategy` is the current minimal implementation:
- If the primary signal > 0 ⇒ emit a **buy** market order.
- If the primary signal < 0 ⇒ emit a **sell** market order.
- If the primary signal = 0 ⇒ emit nothing.

---

## What is Missing (Design Gaps)

1) **Portfolio context**  
   The portfolio primitive now tracks positions + cash, but strategies still lack open orders and
   realized PnL. Snapshots are currently based on order intents and latest prices.

2) **Risk model separation**  
   Risk rules are embedded in SimpleStrategy via a RiskManager instance. We need a clearer
   boundary that allows portfolio-aware risk checks (stop-loss, max drawdown, position limits).

3) **Execution orchestration**  
   The trader process and trigger mechanism (LISTEN/NOTIFY) are defined but not implemented.

4) **Fill-driven positions**  
   Order lifecycle + reconciliation are implemented, but position snapshots are still derived from
   order intents. We still need fill-driven positions and open order tracking.

5) **Signal metadata & diagnostics**  
   We currently store only `signal_value` and `target_qty`. Diagnostics like signal inputs,
   thresholds, or confidence are not captured.

---

## Proposed Next Tasks

1) **Portfolio enrichment**
   - Add open orders and realized PnL.
   - Derive positions from fills instead of order intents.

2) **Explicit RiskManager phase**
   - Move risk checks out of SimpleStrategy into a dedicated risk pipeline.
   - Add guardrails like max position size and max exposure.

3) **Trader service (event-driven)**
   - Implemented via `trader.trader_service` using `LISTEN`/`NOTIFY`.
   - Enforces single-flight execution and coalescing.

4) **Fill-driven positions**
   - Use fills (not intents) to update positions and cash.
   - Track open orders separately from positions.

5) **Signal metadata enrichment**
   - Extend `signal_events` to store signal diagnostics (optional).
