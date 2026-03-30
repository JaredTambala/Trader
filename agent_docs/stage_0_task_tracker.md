# Phase 1 Task Tracker — Core Trading Engine

This file keeps the historical task numbering, but the active roadmap is now framed as **Phase 1: core trading engine** rather than the older Stage 0 paper-bot scope.

## Phase 1 Purpose

Deliver and stabilize the core runtime needed to:

- ingest market data
- build and run strategies via direct Python imports and injection
- apply risk management
- run backtests
- execute live paper trades through Alpaca
- operate the minimum safe runtime/orchestration around those flows

## In Scope

- Postgres-first event storage
- market data stream, backfill, replay, and quality checks
- cycle execution, trader service orchestration, and reconciliation
- strategy authoring interfaces and injected runtime composition
- risk pipeline, risk context, and user-owned risk composition
- internal paper broker and Alpaca broker
- backtesting, metrics snapshots, and trading-session tagging
- health/status capabilities directly tied to safe runtime operation

## Explicitly Out of Scope for Phase 1

- the Reflex frontend and UI-driven backtest workflow
- Apache Superset analytics
- splitting the repo into `trader-core` and `trader-ui`
- containerization, VPS packaging, and deployment-productization work

## Status Vocabulary

- `Active / Complete` — retained in Phase 1 and complete enough for the current phase.
- `Active / Incomplete` — retained in Phase 1 but still has material work left.
- `Deferred Beyond Phase 1` — intentionally removed from the active phase.
- `Historical / Superseded` — preserved for continuity, but no longer the active architectural truth.

---

## Task 0.1 — Repository Skeleton & Core Interfaces

### Status
Active / Complete

### Current meaning
The repo has a stable core layout under `src/trader/`, top-level runtime entrypoints, tests, and the basic contracts required to build the rest of the engine.

### Delivered
- Core modules under `src/trader/`.
- Public interfaces for strategy, broker, risk, config, cycle, and event-store concerns.
- External runtime entrypoints such as `run_trader_service.py`, `run_market_data_stream.py`, `run_market_data_backfill.py`, and `run_data_quality.py`.
- Baseline packaging and test structure.

### Evidence
- Core package: `src/trader/`
- Entry points: `run_trader_service.py`, `run_market_data_stream.py`, `run_market_data_backfill.py`, `run_data_quality.py`
- Tests: `tests/`
- Package config: `pyproject.toml`

### Notes
- The original “no-op cycle via `python -m trader.cycle`” milestone is historical context only. The repo now favors external entrypoints and library usage.

---

## Task 0.2 — Event Store & Schema Foundation

### Status
Active / Complete

### Current meaning
The project has an event-sourced storage foundation with append-only execution records, lifecycle events, and queryable state. The original DuckDB-first version is historical; the current runtime truth is Postgres-first.

### Delivered
- Event-store abstraction and schema bootstrap in `src/trader/data.py`.
- Append-only event tables for market data, signals, orders, fills, positions, runs, sessions, and metrics.
- Transaction helpers and filtered event-store behavior.
- DuckDB retained only for tests and local support utilities.

### Evidence
- Event-store implementation: `src/trader/data.py`
- DuckDB test support: `tests/support/duckdb_store.py`
- Schema docs: `docs/schema.md`, `docs/er.md`
- Tests: `tests/test_data.py`

### Remaining gaps
- None for Phase 1 foundation, but historical wording in older docs had drifted and is corrected by this refactor.

### Historical note
- Earlier documents described this task as “DuckDB authoritative.” That is superseded by Task 0.5 and the current codebase.

---

## Task 0.3 — Deterministic Run & Order Identity

### Status
Active / Complete

### Current meaning
Run sessions, cycles, and client order IDs are deterministic enough to support idempotent retries and reconciliation.

### Delivered
- Deterministic helpers for run sessions, cycles, and client order IDs.
- Run-session lifecycle persistence in the event store.
- Idempotent order identity used by both simulated and Alpaca flows.

### Evidence
- Identifiers: `src/trader/identifiers.py`
- Cycle/run-session usage: `src/trader/cycle.py`, `src/trader/trader_service.py`, `src/trader/backtest.py`
- Tests: `tests/test_identifiers.py`, `tests/test_cycle.py`, `tests/test_data.py`, `tests/test_alpaca_broker.py`

---

## Task 0.4 — Market Data Ingestion (Streaming-Lite)

### Status
Active / Complete

### Current meaning
The engine can ingest Alpaca market data, persist bars, replay stored bars, and guard trading against missing or stale inputs.

### Delivered
- Alpaca market-data integration and normalized bar persistence.
- Continuous websocket streaming runner.
- Historical backfill runner.
- Replay tooling that re-emits NOTIFY events from stored bars.
- Staleness handling in the cycle before trading proceeds.
- Data-quality tooling for gap detection.

### Evidence
- Ingestion: `src/trader/market_data.py`, `src/trader/alpaca_market_data.py`
- Streaming: `src/trader/market_data_stream.py`
- Backfill: `src/trader/market_data_backfill.py`
- Replay: `src/trader/market_data_replay.py`
- Data quality: `src/trader/data_quality.py`
- Tests: `tests/test_market_data.py`, `tests/test_market_data_stream.py`, `tests/test_market_data_backfill.py`

---

## Task 0.4b — Minimal Data Viewer (Reflex UI)

### Status
Deferred Beyond Phase 1

### Why deferred
The frontend interface is no longer part of the active phase. The existing Reflex data viewer remains in the repo as deferred interface work, not an active Phase 1 deliverable.

### Evidence
- UI code: `src/ui/`
- UI-specific pages/state: `src/ui/ui/pages/index.py`, `src/ui/ui/state.py`

### Related later work
- See Task 0.8g and `plans/task_0_8g_reflex_ui_refactor_plan.md`

---

## Task 0.5 — Postgres Migration (Runtime Foundation)

### Status
Active / Complete

### Current meaning
The runtime system is Postgres-first, with schema creation, runtime writes, and concurrent workflows built around Postgres rather than DuckDB.

### Delivered
- Postgres event store as the authoritative runtime backend.
- Runtime schema for runs, cycles, orders, fills, positions, metrics, and sessions.
- Updated ingestion/trading flows to operate against Postgres.
- Local compose support for Postgres development.

### Evidence
- Event store: `src/trader/data.py`
- Local runtime infra: `docker-compose.postgres.yml`
- Runtime integrations: `src/trader/cycle.py`, `src/trader/trader_service.py`, `src/trader/market_data_stream.py`, `src/trader/market_data_backfill.py`
- Tests: `tests/test_market_data.py`, `tests/test_data.py`

---

## Task 0.6 — Strategy Implementation & Backtest Foundation

### Status
Active / Complete

### Current meaning
The system has a working strategy/backtest foundation, including signal generation, portfolio state, backtest replay, runtime configuration, and direct object injection into the core execution path.

### Delivered
- Signal, indicator, and signal-generator primitives.
- Example strategies in the repo.
- A reusable policy-driven long/flat strategy engine with built-in trend-following,
  mean-reversion, and Bollinger Band compositions.
- Built-in EMA, RSI, MACD, and Bollinger indicator/signal support for Phase 1 strategy authoring.
- Backtest runner with equity curve and portfolio metrics.
- Portfolio state tracking with cash and positions.
- YAML-driven configuration for runtime and backtest flows.

### Evidence
- Strategies: `src/trader/strategies/`
- Signals/indicators: `src/trader/signals/`, `src/trader/indicators/`, `src/trader/signal_generators/`
- Backtest: `src/trader/backtest.py`
- Portfolio: `src/trader/portfolio.py`
- Tests: `tests/test_backtest.py`, `tests/test_portfolio.py`, `tests/test_cycle.py`, `tests/test_strategy_sma.py`

### Notes
- Earlier built-in strategy selection and class-path-first language is historical. The current Phase 1 strategy model is direct injection only.

---

## Task 0.7 — InternalPaperBroker (Execution-Aligned Simulation)

### Status
Active / Complete

### Current meaning
The repo contains an internal execution simulator aligned with the event-sourced lifecycle used by the live system. More advanced statistical realism is tracked separately in Task 0.8c.

### Delivered
- Internal paper broker integrated into the cycle and broker response flow.
- Append-only order lifecycle recording and fill event handling.
- Indicator telemetry and metrics snapshots used by backtests and simulated execution.
- Execution-aligned behavior shared with the rest of the engine.

### Evidence
- Broker implementation: `src/trader/broker.py`
- Cycle integration: `src/trader/cycle.py`
- Metrics: `src/trader/metrics.py`
- Tests: `tests/test_cycle_events.py`, `tests/test_backtest.py`, `tests/test_data.py`

### Remaining gaps
- Richer stochastic fill realism is explicitly deferred to Task 0.8c.

---

## Task 0.8 — AlpacaPaperBroker Adapter

### Status
Active / Complete

### Current meaning
The live paper broker path exists and supports deterministic client order IDs, Alpaca submission, status mapping, startup recovery, and broker-sourced portfolio safety checks.

### Delivered
- `AlpacaPaperBroker` backed by `alpaca-py`.
- Deterministic and idempotent submission behavior.
- Canonical order-status mapping.
- Startup recovery that reconciles local order history against broker state.
- Local-state adoption/closure of open orders for safe resume behavior.
- Alpaca portfolio sync and reset-from-broker support in the trader service/runtime path.
- Symbol and asset-class normalization across Alpaca responses, including fail-closed mismatch handling.

### Evidence
- Broker: `src/trader/broker.py`
- Cycle/runtime integration: `src/trader/cycle.py`, `src/trader/trader_service.py`
- Tests: `tests/test_alpaca_broker.py`
- Docs: `docs/execution.md`, `README.md`

---

## Task 0.8b — UI Backtest Runner

### Status
Deferred Beyond Phase 1

### Why deferred
This is frontend/interface work. It exists in the repo, but it is not part of the active phase after the scope reset.

### Evidence
- Backend API: `src/trader/api.py`
- UI pages/state: `src/ui/ui/pages/backtest.py`, `src/ui/ui/pages/backtest_result.py`, `src/ui/ui/state.py`
- Tests: `tests/test_backtest_api.py`

### Related plan
- `plans/task_0_8b_breakdown.md`

---

## Task 0.8c — Statistical Fill Model for Internal Broker

### Status
Deferred Beyond Phase 1

### Current meaning
The internal broker already has the basic tunables needed for Phase 1. Richer stochastic realism is now treated as later-phase research work rather than an active blocker.

### Delivered
- Configuration knobs for rejection probability, fill delay, fill fraction, and RNG seeding.

### Evidence
- Broker/config: `src/trader/broker.py`, `src/trader/config.py`
- Example config: `configs/example.yaml`

### Why deferred
- Additional realism here would currently be speculative rather than calibrated.
- The existing tunables are enough for the current phase’s execution-aligned simulation baseline.
- More advanced slippage and distribution modeling belongs in a later phase with clearer empirical targets.

---

## Task 0.8d — Trading Sessions & Session-Scoped Event Tagging

### Status
Active / Complete

### Current meaning
Trading sessions are first-class and all relevant runtime events can be joined back to a session/run.

### Delivered
- `trading_sessions` and `session_id` tagging across event tables.
- Session-aware run/cycle/metrics persistence.
- Stable join key for backtest and live-run analysis.

### Evidence
- Schema/event tagging: `src/trader/data.py`, `src/trader/cycle.py`, `src/trader/backtest.py`, `src/trader/metrics.py`, `src/trader/portfolio.py`
- DuckDB test mirror: `tests/support/duckdb_store.py`

---

## Task 0.8e — Strategy Externalization (User-Provided Code)

### Status
Active / Complete

### Current meaning
Strategies and risk managers are externalizable through normal Python imports. User code can import trader interfaces, instantiate concrete objects directly, and pass them into the runtime without editing core internals.

### Delivered
- Importable strategy base interfaces for external user code.
- `run_cycle`, `TraderService`, and `BacktestRunner` all support direct object injection.
- External examples showing injected strategy/risk construction in user-owned scripts.
- No framework-owned class-path loading or config-owned composition path remains.

### Evidence
- Injection path: `src/trader/cycle.py`, `src/trader/trader_service.py`, `src/trader/backtest.py`
- Base interfaces: `src/trader/strategy.py`, `src/trader/risk.py`
- Examples: `external_strategy_demo.py`, `examples/run_injected_trader_service.py`, `examples/run_injected_backtest.py`

---

## Task 0.8f — Analytics via Apache Superset

### Status
Deferred Beyond Phase 1

### Why deferred
Analytics UI is outside the active core-engine phase.

### Related plan surface
- Backlog entry retained for later-phase analytics work.

---

## Task 0.8g — Split UI into `trader-core` and `trader-ui`

### Status
Deferred Beyond Phase 1

### Why deferred
Package-splitting and UI extraction are no longer active-phase concerns. They remain valid later-phase platform work.

### Evidence
- Plan file: `plans/task_0_8g_reflex_ui_refactor_plan.md`

---

## Task 0.9 — Risk Management Layer

### Status
Active / Complete

### Current meaning
Risk is now a standalone pipeline that filters candidate orders using a rich runtime context rather than being strategy-owned.

### Delivered
- `RiskContext` with positions, open orders, prices, and run metadata.
- `RiskPipeline` composition through direct Python object assembly.
- Focused built-in risk managers for halt, order count, gross exposure, and per-symbol exposure.
- Open-buy guard behavior.
- Runtime-visible risk rejection logging.

### Evidence
- Risk layer: `src/trader/risk.py`
- Cycle integration: `src/trader/cycle.py`
- Runtime integration: `src/trader/trader_service.py`, `src/trader/backtest.py`
- Tests: `tests/test_risk_manager.py`, `tests/test_cycle.py`, `tests/test_market_data.py`

---

## Task 0.10 — Execution Orchestrator (Real-time + Once)

### Status
Active / Complete

### Current meaning
The runtime orchestrator exists and supports loop/once/realtime execution, LISTEN/NOTIFY-driven triggers, startup recovery, broker-state validation, and single-flight behavior.

### Delivered
- `TraderService` runtime orchestration.
- Realtime and loop execution with trigger coalescing.
- Startup recovery and fail-closed broker portfolio validation.
- Cycle execution path from ingestion through broker/fills/persistence.
- Replay compatibility via market-data notify events.

### Evidence
- Runtime service: `src/trader/trader_service.py`
- Cycle engine: `src/trader/cycle.py`
- Replay: `src/trader/market_data_replay.py`
- Tests: `tests/test_trader_service.py`, `tests/test_cycle.py`, `tests/test_backtest.py`

---

## Task 0.11 — Health & Status API

### Status
Deferred Beyond Phase 1

### Current meaning
HTTP health/status endpoints are no longer part of the active core-engine phase. The current phase relies on logs, event-store state, and operator tooling rather than a client-facing API surface.

### Evidence
- Placeholder helpers: `src/trader/web.py`

### Why deferred
- These endpoints are mainly relevant for a future client/application layer.
- They do not change the core ingestion, strategy, risk, backtest, or live-execution capabilities.
- The current operator model is logs plus event-store inspection, not an HTTP control plane.

---

## Task 0.12 — Containerisation & VPS Runtime

### Status
Deferred Beyond Phase 1

### Why deferred
Deployment packaging and VPS/runtime productization are no longer active-phase deliverables. The repo may still contain supporting local infrastructure, but this is not part of the current Phase 1 target.

### Evidence
- Local compose support: `docker-compose.postgres.yml`

---

## Phase 1 Supporting Capabilities

These are not separate renumbered tasks here, but they are part of the retained core scope and should be treated as supporting Phase 1 functionality:

- market data replay
- data quality checks
- metrics snapshots / runtime metrics
- Alpaca portfolio sync and fill-driven portfolio updates

## Historical Notes

- Earlier “Stage 0” language is preserved only for task-number continuity.
- Earlier DuckDB-first descriptions are historical and superseded by the current Postgres runtime architecture.
- Deferred interface work remains in the repo for later phases, but is no longer part of the active roadmap.
