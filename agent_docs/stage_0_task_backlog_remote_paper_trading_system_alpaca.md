# Stage 0 Task Backlog — Remote Paper Trading System (Alpaca)

## Stage 0 Goal

> A remotely deployed, unattended **paper trading bot** that ingests live market data, generates signals, executes trades via **Alpaca paper**, and records **every action** in a transactional DuckDB event store — with full idempotency, risk controls, and observability.

---

## Global Stage 0 Constraints

- **Single node**, single container
- **DuckDB is the authoritative store**
- **Alpaca paper brokerage** is the default execution target
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
- `client_order_id` is deterministic and **unique** in DuckDB.
- A given `client_order_id` may transition states forward, but must never create a second broker order.
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
- `client_order_id` (TEXT, PK)
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
  - unique `client_order_id`
  - (recommended) uniqueness on `(symbol, ts, source)` for market data events if applicable
- Transaction helpers (atomic cycle execution)

**Acceptance Criteria**
- DB auto-initialises
- Duplicate `client_order_id` insertion fails
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
- Implement polling or websocket client
- Persist **raw** market data events to DuckDB
- Minimal normalization (timestamp, symbol)

**Acceptance Criteria**
- Market data written before strategy runs
- Missing/late data handled safely (skip + warn)
- Tests verify persistence

---

## Task 0.5 — Minimal Strategy Implementation

**Purpose**  
Generate deterministic trade intent.

**Scope**
- Implement a simple strategy:
  - small fixed universe
  - deterministic logic
- Output target positions or signals
- Persist signal events with `run_id`

**Acceptance Criteria**
- Strategy deterministic for same inputs
- Signals persisted correctly
- Tests validate signal generation

---

## Task 0.6 — InternalPaperBroker (Deterministic Simulator)

**Purpose**  
Provide deterministic execution for CI, testing, and fallback.

**Scope**
- Instant fills at last known price
- Persist:
  - order events
  - fill events
  - position snapshots

**Acceptance Criteria**
- Orders → fills → positions consistent
- Deterministic behaviour
- Idempotency preserved on rerun

---

## Task 0.7 — AlpacaPaperBroker Adapter

**Purpose**  
Execute real paper trades via Alpaca from the VPS with a well-defined, idempotent order lifecycle.

**Scope**

### Configuration
- Load Alpaca credentials from env vars

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

## Task 0.8 — Risk Management Layer

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

## Task 0.9 — Execution Orchestrator (Real-time + Once)

**Purpose**  
Tie ingestion → strategy → risk → execution into a safe pipeline that can run:
- **real-time** on new market data events (`MODE=realtime`)
- as a **single cycle** for tests/manual runs (`MODE=once`)

**Scope**

### Core pipeline (single-flight)
Implement a `process_market_event()` pipeline that:
1. persists the market data event
2. generates signals/targets
3. applies risk checks
4. generates order intents
5. persists `created` / `validated` order events
6. submits via selected broker
7. persists `submitted` and later status transitions
8. reconciles open orders and updates positions
9. records run status (`run_events`) for observability

### Real-time mode
- Implement a long-running listener (websocket or poller) that:
  - calls `process_market_event()` on each new market datum
  - enforces **single-flight** execution
  - coalesces bursts using `MIN_TRIGGER_INTERVAL_MS`
  - sets a `pending` flag if new events arrive mid-flight

### Once mode
- Implement `python -m trader.cycle` to run one pass using latest available market data.

### Staleness handling
- Define and enforce:
  - max allowable age of latest market data before trading
  - if stale: record run event and skip trading

### Documentation
- Update `docs/execution.md` describing:
  - real-time event-driven flow
  - single-flight/pending behaviour
  - coalescing and staleness policy

**Acceptance Criteria**
- End-to-end pipeline works with:
  - `BROKER=internal`
  - `BROKER=alpaca`
- Runs correctly in:
  - `MODE=once`
  - `MODE=realtime` (smoke test)
- No overlapping executions (single-flight enforced)
- Failures recorded cleanly and default to safe behaviour

---

## Task 0.10 — Health & Status API

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

## Task 0.11 — Containerisation & VPS Runtime

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

