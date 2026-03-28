# Phase 1 Backlog — Core Trading Engine

This file preserves the historical task numbering from the earlier Stage 0 roadmap, but the active roadmap has been reset to **Phase 1: core trading engine**.

## Phase 1 Goal

Build and stabilize a **core trading engine** that:

- ingests and persists market data
- loads and runs strategies via direct Python imports and injection
- applies risk management before order placement
- supports truthful backtesting
- executes live paper orders through Alpaca
- records every meaningful runtime action in a Postgres-backed event store

## Phase 1 Active Scope

- Postgres-first event storage and schema management
- market data ingestion, backfill, replay, and data-quality checks
- cycle execution and trader-service orchestration
- strategy interfaces, injected runtime composition, and example strategies
- risk context, risk pipeline, and user-owned risk-manager composition
- internal paper broker and Alpaca paper broker
- backtesting, metrics snapshots, and trading-session tagging
- minimal runtime observability directly required for safe execution

## Explicitly Deferred Beyond Phase 1

- the Reflex frontend and UI-driven backtest workflow
- Apache Superset analytics
- package split into `trader-core` and `trader-ui`
- VPS/containerization/deployment-productization work

## Current Architectural Truth

- `Postgres` is the authoritative runtime event store.
- `DuckDB` is retained only for tests and historical compatibility.
- Strategies are supplied directly from user code; there is no config-driven class-path loading path.
- Risk managers are composed directly in user code through a `RiskPipeline`.
- The frontend interface exists in the repo but is not active-phase work.

## Definition of Done

A task is complete only when:

- the behavior is implemented and working
- tests exist or are updated where applicable
- documentation is updated alongside the change
- interfaces, schema expectations, and operational assumptions are explicit
- failures default to safe behavior

---

## Active Phase 1 Tasks

### Task 0.1 — Repository Skeleton & Core Interfaces

**Purpose**  
Establish the core package, external entrypoints, tests, and public contracts that the rest of the engine relies on.

**Current Phase 1 interpretation**
- `src/trader/` is the core engine package.
- Top-level scripts are the supported operational entrypoints.
- Core interfaces exist for strategy, broker, risk, config, cycle, and event-store behaviors.

**Acceptance Criteria**
- Project installs cleanly with `uv`.
- External entrypoints work from top-level scripts.
- Tests provide basic coverage of the runtime skeleton.

---

### Task 0.2 — Event Store & Schema Foundation

**Purpose**  
Provide the event-sourced persistence layer for market data, runs, sessions, signals, orders, fills, positions, and metrics.

**Current Phase 1 interpretation**
- The task is no longer “DuckDB authoritative.”
- The runtime foundation is the Postgres-backed event store plus mirrored DuckDB test support.

**Scope**
- Event-store abstraction and schema bootstrap
- append-only execution tables and snapshots
- transaction helpers
- latest-state query support

**Acceptance Criteria**
- Runtime writes and reads succeed against Postgres.
- Schema bootstrap is automatic and repeatable.
- Test support remains available for local/unit workflows.

---

### Task 0.3 — Deterministic Run & Order Identity

**Purpose**  
Guarantee idempotent execution across retries, restarts, and reconciliation loops.

**Scope**
- deterministic run-session IDs
- deterministic cycle IDs
- deterministic client order IDs
- persistent run lifecycle tracking

**Acceptance Criteria**
- same inputs yield the same logical IDs
- retries do not create duplicate logical orders
- IDs are traceable through event tables and logs

---

### Task 0.4 — Market Data Ingestion

**Purpose**  
Ingest live and historical market data for both execution and backtesting workflows.

**Scope**
- Alpaca market-data integration
- websocket stream ingestion
- REST backfill
- persisted bars with normalized timeframe handling
- replay of stored bars into the realtime path
- data-quality checks for gaps and session assumptions

**Acceptance Criteria**
- market data is persisted before trading decisions
- stale or missing data blocks trading safely
- replay drives the same runtime path used by realtime execution

---

### Task 0.5 — Postgres Migration / Runtime Foundation

**Purpose**  
Make Postgres the runtime store and execution backbone for concurrent ingestion, trading, and analysis.

**Scope**
- Postgres event-store implementation
- schema bootstrap and runtime use
- concurrent runtime usage across streamer, trader service, and backtest persistence
- local Postgres runtime support

**Acceptance Criteria**
- Postgres is the authoritative runtime backend
- runtime services can operate concurrently without corrupting event state
- docs and configuration reflect Postgres-first operation

---

### Task 0.6 — Strategy & Backtest Foundation

**Purpose**  
Provide the base execution logic for strategy evaluation, signal generation, portfolio state, and backtest replay.

**Scope**
- strategy interfaces and examples
- signal and indicator primitives
- backtest runner
- portfolio and cash handling
- runtime configuration for backtests and strategies

**Acceptance Criteria**
- strategies can run deterministically in backtest mode
- portfolio and metrics outputs are persisted or summarized correctly
- backtest and live code paths remain aligned where intended

---

### Task 0.7 — InternalPaperBroker (Execution-Aligned Simulation)

**Purpose**  
Provide a simulated execution venue aligned with the event-sourced lifecycle used by live execution.

**Scope**
- internal broker responses for orders/fills
- append-only order lifecycle events
- fill events and portfolio effects
- indicator telemetry and metrics snapshot support

**Acceptance Criteria**
- internal-broker runs produce consistent order/fill/position state
- simulated execution follows the same high-level event flow as live execution
- reruns preserve idempotent behavior

**Relationship to Task 0.8c**
- Task 0.7 covers the execution-aligned simulator.
- Task 0.8c covers richer statistical realism on top of that baseline.

---

### Task 0.8 — AlpacaPaperBroker Adapter

**Purpose**  
Enable real paper execution through Alpaca while preserving the core engine’s idempotent lifecycle.

**Scope**
- Alpaca broker client integration
- deterministic client order IDs
- canonical status mapping
- startup recovery and recent-order reconciliation
- fill capture and lifecycle persistence
- account/portfolio sync behaviors needed by the runtime
- symbol and asset-class normalization for broker responses
- fail-closed mismatch handling when broker state is outside the configured universe

**Acceptance Criteria**
- paper orders can be submitted through Alpaca
- retries do not duplicate broker-side logical intent
- reconciliation updates local runtime state safely
- startup can resume safely from existing broker/open-order state
- broker portfolio mismatches stop trading rather than being silently tolerated

---

### Task 0.8c — Statistical Fill Model for Internal Broker

**Purpose**  
Improve the realism of the internal paper broker through configurable latency, rejection, partial-fill, and slippage models.

**Current status**
- Deferred beyond Phase 1.
- Basic tunables already exist and are sufficient for the current phase.

**Deferred scope**
- explicit distribution families
- slippage modeling
- stronger seeded deterministic tests

**Later-phase acceptance**
- users can configure richer fill behavior through YAML
- seeded runs remain deterministic
- docs explain the simulation knobs clearly

---

### Task 0.8d — Trading Sessions & Session-Scoped Event Tagging

**Purpose**  
Track a live or backtest run as a coherent session even when the broker-side account persists across time.

**Scope**
- `trading_sessions`
- `session_id` across runtime tables
- session-scoped metrics and event joins

**Acceptance Criteria**
- all session-scoped runtime artifacts can be joined reliably
- live and backtest runs can be analyzed independently at the session level

---

### Task 0.8e — Strategy Externalization (User-Provided Code)

**Purpose**  
Allow users to author strategies in their own codebases while importing the trader interfaces from this repo.

**Scope**
- importable strategy and risk-manager interfaces
- direct object injection into `run_cycle`, `TraderService`, and `BacktestRunner`
- user-owned wrapper scripts

**Acceptance Criteria**
- a user can define a strategy outside `src/trader/`
- the engine can run it through normal imports and direct injection
- no central class-path registration is required for the supported path

---

### Task 0.9 — Risk Management Layer

**Purpose**  
Filter candidate orders through a dedicated, composable risk layer rather than embedding risk in strategy code.

**Scope**
- `RiskContext`
- `RiskPipeline`
- focused built-in risk-manager subclasses
- externally authored risk managers composed through normal Python imports
- rejection traceability

**Acceptance Criteria**
- risk checks run before broker submission
- rejections are visible in runtime state and runtime logs
- risk logic can use positions, open orders, prices, and runtime metadata

---

### Task 0.10 — Execution Orchestrator (Real-time + Once)

**Purpose**  
Provide the runtime orchestration layer for loop, once, and realtime execution.

**Scope**
- `TraderService`
- LISTEN/NOTIFY realtime triggers
- coalescing / single-flight execution
- cycle orchestration from data through persistence
- startup recovery and broker-state validation

**Acceptance Criteria**
- realtime and loop execution behave safely
- no overlapping runs occur for the same runtime loop
- failures are recorded and default to no-trade behavior
- Alpaca-backed startup resets local portfolio state from the broker before trading begins

---

### Task 0.11 — Health & Status API

**Purpose**  
Expose runtime health and current status information needed to operate the core engine safely.

**Current status**
- Deferred beyond Phase 1.
- The current code contains placeholder helpers rather than a finished API surface.

**Deferred scope**
- `/health`
- `/status`
- runtime-backed safety/status signals

**Later-phase acceptance**
- health reports unsafe runtime states clearly
- status reports last-run and current-runtime information accurately
- tests validate the operational logic

---

## Deferred Beyond Phase 1

These tasks remain documented, but they are intentionally removed from the active phase.

### Task 0.4b — Minimal Data Viewer (Reflex UI)

**Deferred from Phase 1**

Reason:
- frontend inspection tooling is outside the active core-engine scope

Repo evidence:
- `src/ui/`

---

### Task 0.8b — UI Backtest Runner

**Deferred from Phase 1**

Reason:
- UI-driven execution and result viewing are interface work, not core-engine work

Repo evidence:
- `src/trader/api.py`
- `src/ui/ui/pages/backtest.py`
- `src/ui/ui/pages/backtest_result.py`
- `tests/test_backtest_api.py`

Related plan:
- `plans/task_0_8b_breakdown.md`

---

### Task 0.8f — Analytics via Apache Superset

**Deferred from Phase 1**

Reason:
- analytics UI and dashboarding are later-phase concerns

---

### Task 0.8g — Split UI into `trader-core` and `trader-ui`

**Deferred from Phase 1**

Reason:
- package extraction and UI/core separation are valid later-phase cleanup, not active-phase goals

Related plan:
- `plans/task_0_8g_reflex_ui_refactor_plan.md`

---

### Task 0.12 — Containerisation & VPS Runtime

**Deferred from Phase 1**

Reason:
- deployment packaging and VPS-ready operationalization are no longer part of the current phase definition

---

## Historical Notes / Completed Foundation

- Historical “Stage 0” wording is preserved only to avoid breaking task references.
- Historical DuckDB-first descriptions are superseded by the current Postgres runtime architecture.
- Deferred interface/platform work still exists in the repo and should be treated as later-phase inventory, not active-phase commitments.
