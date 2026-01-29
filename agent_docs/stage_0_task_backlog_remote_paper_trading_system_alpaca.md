# Stage 0 Task Backlog — Remote Paper Trading System (Alpaca)

## Stage 0 Goal

> A remotely deployed, unattended **paper trading bot** that ingests live market data, generates signals, executes trades via **Alpaca paper**, and records **every action** in a transactional DuckDB event store — with full idempotency, risk controls, and observability.

---

## Global Stage 0 Constraints

- **Single node**, single container
- **DuckDB is the authoritative store**
- **Alpaca paper brokerage** is the default execution target
- **Alpaca integrations must use the official Alpaca Python SDK (`alpaca-py`)** (avoid raw HTTP unless the SDK is missing an endpoint)
- All execution must be **idempotent**
- Failures default to **no trading**
- No distributed systems, no Airflow, no Spark, no MLflow

---

## Definition of Done (applies to every Stage 0 task)

A task is complete only when:
- The change is implemented and **covered by tests** (where applicable)
- `pytest` passes
- **Documentation is updated** to reflect the change, including:
  - *what was built*
  - *how to run it*
  - *how to verify it*
  - any new config/env vars
- Any schema or contract changes include an update to the relevant docs (see below)

**Stage 0 documentation set (to be created and maintained):**
- `docs/schema.md` — DuckDB tables, keys, event semantics, query patterns
- `docs/testing.md` — testing standards (unit/integration), mocking, CI expectations
- `docs/ops.md` — deployment, runbooks, incident procedures, halt/rollback
- `docs/execution.md` — execution loop semantics, order lifecycle, idempotency & reconciliation rules

---

## Environment Contract (Stage 0)

Required environment variables:

- `BROKER=alpaca|internal`
- `DB_PATH=/data/events.duckdb`
- `STRATEGY_ID=<string version tag>`
- `ALPACA_API_KEY=...`
- `ALPACA_SECRET_KEY=...`
- `ALPACA_BASE_URL=https://paper-api.alpaca.markets`
- `HEALTH_MAX_AGE_SECONDS=...`

Optional (recommended):
- `MODE=realtime|loop|once` (realtime: event-driven; loop: fixed cadence; once: one-shot)
- `MIN_TRIGGER_INTERVAL_MS=200` (coalescing window for real-time mode)
- `CADENCE_SECONDS=1` (used only in `MODE=loop`)

---

## Execution Cadence (Stage 0)

**Target:** real-time, event-driven execution.

Definition:
- On ingestion of **new market data**, the system should **immediately**:
  1) persist the market data event
  2) generate signals
  3) apply risk checks
  4) submit orders (paper)
  5) persist order/fill/position events

Implementation implications:
- Prefer `MODE=realtime` with a long-running service.
- Maintain **single-flight execution** (no overlapping runs):
  - if new market data arrives while a run is in progress, set a `pending` flag and run again immediately after completion.
- Apply a small coalescing window to avoid thrashing (configurable):
  - `MIN_TRIGGER_INTERVAL_MS` (e.g. 200–1000ms)
- Enforce a **staleness check** before trading.

---

## Order Execution Lifecycle (Stage 0)

**Goal:** a clear, idempotent, auditable lifecycle that works for both `InternalPaperBroker` and `AlpacaPaperBroker`.

### Canonical order state machine
- `created` — order intent generated and recorded
- `validated` — passed risk checks
- `submitted` — submission attempted to broker
- `accepted` — broker acknowledged order (if available)
- `partially_filled` — partial fill recorded
- `filled` — fully filled
- `rejected` — broker rejected order
- `canceled` — canceled by system/operator
- `expired` — expired by broker/session rules
- `error` — internal error/unknown outcome (must trigger reconciliation)

### Required invariants
- `client_order_id` is deterministic per order intent; `order_event_id` is unique per event.
- A given `client_order_id` may transition states forward, but must never create a second broker order.
- `order_events` are append-only; multiple rows per `client_order_id` are allowed.
- If submission outcome is uncertain, state becomes `error` and the system must reconcile before retrying.

### Reconciliation (Stage 0)
- On each trigger (or in a dedicated reconciliation step), the system must:
  - fetch order status for recent `submitted|accepted|partially_filled|error` orders
  - persist status transitions as append-only `order_events`
  - record fills when available
  - update positions via snapshots

### Documentation requirement
- `docs/execution.md` must describe:
  - the state machine
  - Alpaca status mapping
  - idempotency rules
  - reconciliation logic

---

## Task 0.1 — Repository Skeleton & Core Interfaces

**Purpose**  
Establish the project shape and contracts.

**Scope**
- Create repo structure:
  ```
  trader/
    src/trader/
      cycle.py        # one execution cycle
      data.py         # DuckDB access layer
      strategy.py     # Strategy interface + impl
      broker.py       # Broker interface
      risk.py         # Risk checks
      config.py       # Env/config loading
      web.py          # Health/status API
    tests/
    docs/
      schema.md
      testing.md
      ops.md
    README.md
    pyproject.toml
  ```
- Define interfaces only:
  - `Strategy`
  - `Broker`
  - `RiskManager`
  - `EventStore`

**Acceptance Criteria**
- Project installs cleanly
- `python -m trader.cycle` runs a no-op cycle
- `pytest` passes
- Docs created:
  - `docs/schema.md` (initial outline)
  - `docs/testing.md` (initial standards)
  - `docs/ops.md` (initial runbook skeleton)

---

## Task 0.2 — DuckDB Event Store & Schema

**Purpose**  
Create the authoritative execution/event log with a schema that supports **high-frequency (1s) operation**, idempotency, and traceability.

**Scope**
- Initialise DuckDB on startup
- Create append-only tables:
  - `run_events`
  - `market_data_events`
  - `signal_events`
  - `order_events`
  - `fill_events`
  - `position_snapshots`
  - `config_kv`

### Minimum Table Definitions (Stage 0)

> These are *minimum viable schemas*. Columns may be added later, but existing columns must not be removed or repurposed.

**run_events**
- `run_id` (TEXT, PK)
- `strategy_id` (TEXT)
- `mode` (TEXT) — `loop` or `once`
- `decision_ts` (TIMESTAMP)
- `started_at` (TIMESTAMP)
- `finished_at` (TIMESTAMP)
- `status` (TEXT) — `started|success|failed`
- `error_message` (TEXT, nullable)

**market_data_events**
- `symbol` (TEXT)
- `ts` (TIMESTAMP) — event time
- `ingested_at` (TIMESTAMP)
- `price` (DOUBLE)
- `volume` (DOUBLE, nullable)
- `source` (TEXT)

**signal_events**
- `run_id` (TEXT)
- `symbol` (TEXT)
- `signal_value` (DOUBLE)
- `target_qty` (DOUBLE)
- `generated_at` (TIMESTAMP)

**order_events**
- `order_event_id` (TEXT, PK)
- `client_order_id` (TEXT)
- `run_id` (TEXT)
- `symbol` (TEXT)
- `side` (TEXT)
- `qty` (DOUBLE)
- `order_type` (TEXT)
- `status` (TEXT)
- `broker_order_id` (TEXT, nullable)
- `created_at` (TIMESTAMP)

**fill_events**
- `client_order_id` (TEXT)
- `fill_ts` (TIMESTAMP)
- `fill_qty` (DOUBLE)
- `fill_price` (DOUBLE)

**position_snapshots**
- `asof_ts` (TIMESTAMP)
- `symbol` (TEXT)
- `qty` (DOUBLE)
- `avg_price` (DOUBLE)

**config_kv**
- `key` (TEXT, PK)
- `value` (TEXT)

### Schema Design Requirements
- timestamps stored in **UTC** (explicit `ts` for event time, plus `ingested_at` where relevant)
- stable identifiers where needed (`run_id`, `client_order_id`)
- include `source` and `mode` where relevant for auditability
- support efficient “latest state” queries (e.g., last run, last positions)

- Enforce constraints:
  - primary keys where appropriate
  - unique `order_event_id`
  - (recommended) uniqueness on `(symbol, ts, source)` for market data events if applicable
- Transaction helpers (atomic cycle execution)

**Acceptance Criteria**
- DB auto-initialises
- Duplicate `client_order_id` insertion is allowed (append-only order events)
- Schema supports fast append at 1s cadence without schema contention
- Tests validate schema and constraints (including a simple high-frequency insert test)
- Documentation updated:
  - `docs/schema.md` includes table definitions, keys, and event semantics
  - `docs/schema.md` includes recommended query patterns for “latest state” reads

---

## Task 0.3 — Deterministic Run & Order Identity

**Purpose**  
Guarantee idempotency across retries and restarts.

**Scope**
- Define deterministic `run_id`:
  - derived from `STRATEGY_ID + decision timestamp`
- Define deterministic `client_order_id`:
  - derived from `run_id + symbol + side + target_qty`
- Persist run lifecycle:
  - started → success / failed

**Acceptance Criteria**
- Same inputs → same IDs
- Re-running a cycle does not create new orders
- Retry scenarios covered by tests
- Documentation updated:
  - `docs/schema.md` documents `run_id` and `client_order_id` formats and guarantees

---

## Task 0.4 — Market Data Ingestion (Streaming-Lite)

**Purpose**  
Ingest live or near-live market data.

**Scope**
- Implement polling or websocket client using `alpaca-py` market data clients
- Persist **raw** market data events to DuckDB
- Minimal normalization (timestamp, symbol)

**Acceptance Criteria**
- Market data written before strategy runs
- Missing/late data handled safely (skip + warn)
- Tests verify persistence

---

## Task 0.4b — Minimal Data Viewer (Reflex UI)

**Purpose**  
Provide a minimal UI to inspect ingested market data from DuckDB.

**Scope**
- Build a small Reflex app that reads from DuckDB (`DB_PATH`).
- UI filters:
  - Type: `stock` or `crypto`
  - Ticker (symbol)
  - Timeframe (e.g., `1Min`, `1Hour`, `1Day`)
- Views:
  - Table view of bars (columns: ts, open, high, low, close, volume, vwap, trade_count)
  - Time series chart (candlestick view)
- Default behavior:
  - Most recent timeframe + symbol
  - Date range selector or “last N rows” selector for safety
- No trading actions, read-only.

### Trading-Session Axis (No Time Gaps)

**Goal**  
Display OHLC candlesticks with no visual gaps for overnight/weekends/holidays by using a trading-session axis: bars are spaced evenly by bar index, not by wall-clock time.

**Inputs**
- Bars from DuckDB for a selected:
  - `asset_type`: `stock` | `crypto`
  - `symbol` (ticker)
  - `timeframe` (e.g., `1Min`, `5Min`, `1Hour`, `1Day`)
  - `limit` (max rows)
- Each bar row must include: `ts`, `open`, `high`, `low`, `close`, `volume` (optional: `vwap`, `trade_count`).

**Core Behavior**
- Sort bars ascending by `ts`.
- Create a synthetic index `i = 0..N-1` for the sorted bars.
- Use `i` as the x-axis, not `ts`.
- Preserve timestamp visibility:
  - Use `ts` as `customdata` (or equivalent) per point.
  - Show `ts` in hover tooltip and/or tick labels.
- Tick label strategy:
  - Render ticks sparsely to remain readable (e.g., 6–12 ticks across the chart).
  - For each tick index, label it with a formatted timestamp from the corresponding bar:
    - Default format: `YYYY-MM-DD HH:mm` (timezone-aware for stocks; UTC ok for crypto).
    - For daily/weekly/monthly timeframes, use `YYYY-MM-DD`.
- No market calendar required: session gaps are removed implicitly because index increments only when a bar exists.

**Plotly Implementation Requirements (Candlestick)**
- Candlestick trace:
  - `x = indices`
  - `open/high/low/close = series`
- Layout:
  - `xaxis.type = "linear"`
  - `xaxis.tickmode = "array"`
  - `xaxis.tickvals = [indices...]`
  - `xaxis.ticktext = [formatted timestamps...]`
  - `hovermode = "x unified"` (optional)
- Tooltip:
  - Use `customdata = [ts_strings...]`
  - `hovertemplate` includes timestamp + OHLC + volume.

**UI Requirements**
- Add a toggle in the chart view:
  - Axis mode: Trading session | Real time
  - Default for stocks: Trading session (recommended)
  - Default for crypto: Real time (since it trades 24/7) or still allow session mode.
- When switching axis mode:
  - The figure regenerates without requerying the DB.

**Data/State Changes**
- Extend UI state to compute:
  - `sorted_chart_rows`
  - `x_indices`
  - `x_tickvals`
  - `x_ticktext`
  - `customdata_ts`
- Ensure the system handles:
  - `N == 0` → show empty state
  - `N < tick_count` → label every point or every other point
  - Duplicate timestamps → keep stable order; index still unique

**Acceptance Criteria**
- Candlestick chart shows continuous bars with no gaps when data has overnight/weekend gaps.
- Hover tooltip shows the true timestamp for each bar.
- Axis tick labels show meaningful timestamps at a readable density.
- Works for both `stock_bar_events` and `crypto_bar_events` (crypto may show continuous even in real-time mode).
- No dependency on market calendars/holidays for this mode.

**Non-goals**
- No holiday-aware range breaks in this mode.
- No imputation/fill of missing bars.
- No resampling/aggregation beyond what’s already stored.

**Suggested Defaults**
- `tick_count = 8` for `limit <= 2000`, else `tick_count = 12`.
- `label_timezone`:
  - stocks: `America/New_York`
  - crypto: `UTC`

**Acceptance Criteria**
- UI starts with a single command and connects to DuckDB.
- Filters update both table and chart.
- Works for both `stock_bar_events` and `crypto_bar_events`.
- Docs updated with how to run the UI and required env vars.

---

## Task 0.5 — Postgres Migration (No Data Carry-Over)

**Purpose**  
Enable concurrent streaming + trading workloads with a multi-connection, concurrent OLTP backend.

**Scope**
- Replace DuckDB as the authoritative event store with Postgres.
- No data migration required (fresh schema only).
- Maintain event semantics and idempotency guarantees.

### Detailed Plan

**1) Schema & Storage Layer**
- Create Postgres DDL for all current event tables:
  - `run_events`, `stock_bar_events`, `crypto_bar_events`, `signal_events`,
    `order_events`, `fill_events`, `position_snapshots`, `config_kv`
- Translate indexes/constraints to Postgres:
  - PKs and unique indexes (e.g., `order_events.order_event_id`, `run_events.run_id`)
  - Uniqueness for bar tables on `(symbol, timeframe, ts, source)`
- Add migrations or bootstrap SQL that runs on startup.

**2) Event Store Abstraction**
- Introduce `PostgresEventStore` implementing `EventStore` (parity with DuckDB).
- Ensure `record_event`, `record_run_start`, `record_run_finish`, `transaction`.
- Use parameterized SQL and safe transactions.

**3) Configuration**
- Add environment variables:
  - `PG_DSN` or `PG_HOST`, `PG_PORT`, `PG_DB`, `PG_USER`, `PG_PASSWORD`
  - `EVENT_STORE=postgres|duckdb` (optional toggle during transition)
- Update config loader and docs.

**4) Data Access / Queries**
- Update any direct DuckDB queries in the UI and data tools:
  - UI data viewer queries to use Postgres (read-only connection).
  - Backfill merge logic: replace DuckDB `MERGE` with `INSERT ... ON CONFLICT DO NOTHING` (or `DO UPDATE` if desired).
- Ensure `market_data_backfill` uses Postgres staging only if needed; otherwise direct upsert.

**5) Concurrency & Streaming**
- Ensure the websocket streamer uses a separate Postgres connection pool from the trading loop.
- Set sensible pool sizes and timeouts to avoid lock contention.

**6) Tests**
- Update tests to use Postgres:
  - Use Docker/Postgres test container or local test database.
  - Replace DuckDB assertions with Postgres queries.
- Maintain unit tests for event store behavior + uniqueness constraints.

**7) Docs & Runbook**
- Update `docs/schema.md`, `docs/ops.md`, `docs/testing.md`, and `README.md`.
- Provide new setup instructions:
  - How to start Postgres locally
  - How to initialize schema
  - How to run app/tests against Postgres

### Acceptance Criteria
- All event writes/readbacks work against Postgres.
- Concurrent streamer + trading cycle can write simultaneously without lock errors.
- Tests pass against Postgres.
- Docs updated with Postgres setup and operational guidance.

---

## Task 0.6 — Minimal Strategy Implementation

**Purpose**  
Establish the end-to-end strategy + backtest loop with deterministic signals, portfolio state, and cash tracking.

**Scope**
- Signal/indicator primitives with SMA crossover strategy.
- YAML-driven configuration for strategy + backtest runs.
- Portfolio snapshots persisted per cycle (positions + cash).
- Backtest runner with in-memory bars and equity curve metrics.

**Acceptance Criteria**
- Strategy deterministic for same inputs.
- Signals + portfolio snapshots persisted correctly.
- Backtest produces equity curve + benchmark metrics.
- Tests validate strategy, portfolio, and backtest plumbing.

---

## Task 0.7 — InternalPaperBroker (Deterministic Simulator)

**Purpose**  
Provide deterministic execution for CI, testing, and fallback.

**Scope**
- Instant fills at last known price
- Persist:
  - order events
  - fill events
  - position snapshots
- Persist indicator telemetry for run interrogation:
  - `indicator_events` with `run_id`, `cycle_id`, `symbol`, `indicator_name`, `value`, `bar_ts`
  - Record which bar timestamp each indicator was computed from
- Persist a `runs.config_snapshot` (full YAML payload) at run start
- Record `order_events` for every generated order (created/validated/submitted/filled) even in simulation
- Backtest performance summary (strategy vs buy-and-hold), including:
  - total return, CAGR, volatility
  - Sharpe/Sortino, max drawdown, Calmar
  - hit rate, profit factor, expectancy, avg win/loss
  - trade count, exposure %, turnover
  - tracking error, information ratio, alpha/beta
  - equity curve and buy-and-hold benchmark curve
  - note required inputs (cash ledger, fills, and benchmark series)


### Subtasks
- Define deterministic InternalPaperBroker behavior and lifecycle events.
- Add `indicator_events` schema (run_id, cycle_id, symbol, indicator_name, value, bar_ts).
- Persist `runs.config_snapshot` for backtest and trading sessions.
- Emit order lifecycle events (created/validated/submitted/filled) in simulation.
- Emit fill events and update position snapshots idempotently.
- Persist indicator values during signal generation per cycle.
- Expand backtest summary metrics (hit rate, profit factor, expectancy, avg win/loss, turnover, exposure %).
- Update docs: `docs/schema.md`, `docs/er.md`, `docs/execution.md`, `docs/backtesting.md`.
- Add tests for broker determinism/idempotency and indicator event persistence.
- Validate Task 0.7 DoD with updated acceptance criteria.

**Acceptance Criteria**
- Orders → fills → positions consistent
- Deterministic behaviour
- Idempotency preserved on rerun
- Indicator series are queryable per `run_id`/`cycle_id`
- Run config snapshot stored for audit/replay
- Backtest summary reports strategy vs buy-and-hold metrics with clear inputs and assumptions

---

## Task 0.8 — AlpacaPaperBroker Adapter

**Purpose**  
Execute real paper trades via Alpaca from the VPS with a well-defined, idempotent order lifecycle.

**Scope**

### Configuration
- Load Alpaca credentials from env vars
- Use `alpaca-py` to interact with Alpaca trading APIs (avoid raw HTTP unless required)

### Broker methods
Implement:
- `get_positions()`
- `place_orders(orders)`
- `get_order_by_id(broker_order_id)`
- `list_orders(since_ts)` (or equivalent) for reconciliation
- Optional:
  - `get_account()`

### Order submission rules (idempotency)
- Always submit with deterministic `client_order_id`.
- Before submit:
  - check DuckDB for existing `client_order_id`
  - if order exists in `submitted|accepted|partially_filled|filled`, **do not resubmit**
  - if order exists in `error`, attempt reconciliation first
- Persist:
  - `created` and `validated` events before contacting broker
  - `submitted` event with Alpaca `broker_order_id`
  - subsequent status transitions from reconciliation

### Status mapping
- Map Alpaca order status values into canonical states:
  - `accepted|partially_filled|filled|rejected|canceled|expired|error`
- Persist every transition as an append-only `order_event`.

### Error handling
- Bounded retries for transient failures
- If submission outcome uncertain:
  - write `order_event.status=error`
  - defer to reconciliation (fetch by recent orders)
- Default to “no trade” on ambiguity

### Documentation
- Update `docs/execution.md` with:
  - Alpaca mapping
  - reconciliation approach
  - idempotency guarantees

**Acceptance Criteria**
- Alpaca paper orders execute successfully from VPS
- No duplicate Alpaca orders on retries
- Broker order IDs and status transitions persisted
- Reconciliation updates statuses for open orders
- Integration tests with mocked Alpaca responses cover:
  - idempotent resubmission prevention
  - uncertain submission → `error` → reconcile

---

## Task 0.8d — Trading Sessions & Session-Scoped Event Tagging

**Purpose**  
Introduce a stable trading-session join key so live runs can be analyzed independently of the persistent Alpaca account state.

**Scope**
- Add `trading_sessions` table to persist session metadata (strategy_id, mode, symbols, timeframe, status).
- Add `session_id` columns to `run_events`, `signal_events`, `indicator_events`, `order_events`, `fill_events`,
  `position_snapshots`, and `metrics_snapshots`.
- Use the `run_id` as the session key for trading sessions (stable join key for all events in the run).
- Tag all emitted events with `session_id` and include in portfolio/metrics snapshots.
- Ensure Postgres schema creation/migration includes the new table and columns.

**Acceptance Criteria**
- All event tables contain `session_id` and are populated for live trading runs.
- `trading_sessions` entries are created/updated on run start/finish with strategy metadata.
- Queries can join all events for a session using `session_id=run_id`.

---

## Task 0.8e — Strategy Externalization (User-Provided Code)

**Purpose**  
Allow users to author strategies and risk managers in their own codebases while importing trader interfaces from this repo.

**Scope**
- Stabilize `Strategy` and `RiskManager` interfaces in `trader.strategy` / `trader.risk` with clear method contracts.
- Add a dynamic loader that imports user classes via `module:Class` strings.
- Extend YAML schema with:
  - `strategy.class_path` + `strategy.params`
  - `risk_manager.class_path` + `risk_manager.params`
- Wire `run_cycle` to prefer external implementations when `class_path` is provided; fall back to internal strategy types otherwise.
- Add strategy state persistence keyed by `session_id` for realtime parity (opt-in at first).
- Document a minimal external strategy template and “how to run” flow.

**Acceptance Criteria**
- A user can `pip install trader`, subclass `Strategy` in their own repo, and run it by setting `strategy.class_path`.
- `run_cycle` successfully loads external strategies and risk managers with params.
- Clear errors are surfaced when class paths are invalid or do not conform to the interface.
- Docs include an external strategy example and YAML config snippet.

---

## Task 0.8f — Analytics via Apache Superset

**Purpose**  
Provide a dedicated analytics UI over the Postgres event store for run/session analysis.

**Scope**
- Add a Superset service (docker-compose) and connect it to the Postgres DB.
- Create a minimal set of datasets: runs, trading_sessions, run_events, order_events, fill_events, position_snapshots, metrics_snapshots.
- Provide example dashboards: session PnL, equity curve, fill rate, order lifecycle funnel.
- Document setup and environment variables for Superset.

**Acceptance Criteria**
- Superset starts locally and can connect to Postgres with read-only credentials.
- Example dashboards load and query live data.
- Docs include setup + basic dashboard steps.

---

## Task 0.8g — Split UI into `trader-core` and `trader-ui`

**Purpose**  
Decouple the Reflex UI from the core trading library to allow separate installation and release cadence.

**Scope**
- Create a `trader-core` package for core classes (cycle, broker, data, config, strategy, risk, metrics, backtest).
- Create a `trader-ui` package (existing Reflex app) with its own dependencies and run scripts.
- Update imports so UI depends on core via package install, not relative paths.
- Add build/install docs for both packages.
- Ensure API endpoints live in core (or a separate `trader-api` module) and UI consumes them via HTTP.

**Acceptance Criteria**
- `pip install trader-core` works without UI deps.
- `pip install trader-ui` brings UI + HTTP client deps only.
- UI runs against a core API server as a separate process.

---

## Task 0.8c — Statistical Fill Model for Internal Broker

**Purpose**
Enrich the `InternalPaperBroker` simulation with tunable statistical parameters so latency, rejection, partial fills, and slippage mimic real execution behavior.

**Scope**
- Add new `internal.broker.fill_model` config values (latency distribution, fill fraction Beta parameters, slippage scale, rejection logistic).
- Extend `Config` to expose these parameters and pass them into `InternalPaperBroker`.
- Update the broker to sample latency/log-normal, fill fraction/Beta, slippage/t-distribution, and conditional rejection, defaulting to deterministic seeds for testability.
- Document the configuration knobs and their effect on fills.
- Add tests ensuring deterministic output when seeding the RNG and verifying reject/fill behavior.

**Acceptance Criteria**
- Configuration exposes latency/fill/slippage/reject parameters for the internal broker.
- `InternalPaperBroker` samples from the specified distributions and respects the reproducible RNG seed.
- Docs mention Task 0.8c and describe how to tune the simulation.
- Tests confirm behavior for deterministic seeds and validate distribution wiring.

---

## Task 0.9 — Risk Management Layer

**Purpose**  
Prevent catastrophic behaviour.

**Scope**
- Implement checks:
  - `halt=true` (from `config_kv`)
  - `max_orders_per_run`
  - `max_gross_usd`
  - `max_pos_usd_per_symbol`
- Enforce **before** broker submission
- Persist risk rejections as events

**Acceptance Criteria**
- Violations prevent order placement
- Rejections are traceable
- Tests cover each limit

---

## Task 0.10 — Execution Orchestrator (Real-time + Once)

**Status**
Complete (trader_service loop/realtime, cycle orchestration, idempotent flow).

**Summary**
- `trader_service` already provides loop/realtime/once modes that enqueue `run_cycle` with single-flight safeguards via LISTEN/NOTIFY and pending coalescing.
- `run_cycle` implements the pipeline (persist market data, signals, risk, broker, fills, positions, run events).
- `TraderService._run_realtime` listens on `notify_channel`, retries on missing data, and respects min trigger interval.
- `cycle.py`, `api.py`, and docs already describe staleness handling and run lifecycle.

**Evidence**
- Code: `src/trader/trader_service.py`, `src/trader/cycle.py`.
- Docs: `docs/execution.md`, `README.md`.
- Tests: existing cycle/backtest tests exercise the pipeline indirectly.

**Acceptance Criteria**
- Runs work with `BROKER=internal` and `BROKER=alpaca` (0.8 implemented).
- `python -m trader.cycle` executes a single pass with freshness checks.
  - `MODE=once`
  - `MODE=realtime` (smoke test)
- No overlapping executions (single-flight enforced)
- Failures recorded cleanly and default to safe behaviour

---

## Task 0.11 — Health & Status API

**Purpose**  
Enable remote monitoring and operations.

**Scope**
- FastAPI app:
  - `GET /health`
  - `GET /status`
- `/health` checks:
  - last successful run age
  - halt flag
  - repeated failure condition
- `/status` returns:
  - last run
  - last error
  - positions
  - broker mode
  - key risk limits

**Acceptance Criteria**
- Health flips to non-200 when unsafe
- Status reflects live state accurately
- Tests validate logic

---

## Task 0.12 — Containerisation & VPS Runtime

**Purpose**  
Run unattended in the cloud.

**Scope**
- Dockerfile (single image)
- docker-compose.yml (single service)
- systemd service (required):
  - run in `MODE=loop` for 1-second cadence
  - restart on failure
- systemd timer (optional):
  - only for `MODE=once` scheduled cadence (e.g., 1m+)
- Logging to stdout
- README:
  - VPS setup
  - Alpaca credential setup
  - halt procedures
  - health checks
  - how to run 1s cadence (`MODE=loop`, `CADENCE_SECONDS=1`)

**Acceptance Criteria**
- Bot runs unattended on VPS in `MODE=loop` at 1s cadence (smoke test)
- Restarts on failure
- Logs accessible
- Health endpoint reachable
