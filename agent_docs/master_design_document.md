# Trading System Roadmap — Functional and Non-Functional Requirements

This document defines the roadmap at a phase level. The active roadmap is now centered on a **core trading engine**, not a frontend-heavy or deployment-heavy platform.

## Global Definition of Done

A phase, feature, or task is considered done only when all of the following are true:

### Engineering and Quality

- the functionality works as specified
- automated tests exist or are updated where applicable
- public interfaces and contracts are intentional and stable

### Documentation

- relevant documentation is updated as part of the change
- what was built, why it exists, and how to run it are documented
- schema or interface changes update the relevant docs

### Traceability and Auditability

- introduced behavior is observable through logs, events, or persisted state
- identifiers, versions, and assumptions are explicit

### Safety and Operations

- failure modes default to safe behavior
- operational expectations are documented for the scope of the active phase

### Stage Integrity

- work does not pull later-phase concerns into the current phase without a clear reason

---

## Phase 1 — Core Trading Engine

### Purpose

Establish a **core trading engine** that can be run, tested, and reasoned about without depending on a frontend application.

This phase proves:

> “I can ingest market data, run strategies and risk, backtest them truthfully, and execute paper trades through Alpaca with an auditable runtime.”

### Functional Requirements

#### Event-Sourced Runtime Foundation

- The runtime must persist market data, signals, orders, fills, positions, run sessions, and metrics.
- The authoritative runtime store must be **Postgres**.
- Test and support workflows may still use DuckDB, but DuckDB is not the active runtime target.

#### Market Data Ingestion

- The system must ingest live or near-live market data.
- The system must support:
  - websocket or polling-based live ingestion
  - historical backfill
  - replay of stored bars into the realtime execution path
- Market data must be persisted before strategy evaluation.

#### Strategy Execution

- The system must support at least one working strategy path.
- Strategies must be loadable via a stable external interface.
- Users must be able to provide strategy implementations from outside the core codebase.

#### Risk Management

- Candidate orders must pass through a dedicated risk layer before broker submission.
- Risk logic must have access to:
  - current positions
  - open orders
  - relevant prices
  - run/session metadata
- Risk behavior must be configurable and composable.

#### Backtesting

- Backtests must reuse the same core execution concepts as live trading.
- Backtests must persist or expose sufficient outputs to analyze:
  - trades
  - equity curve
  - drawdown
  - turnover
  - benchmark comparison

#### Live Paper Execution via Alpaca

- The engine must support paper order submission through Alpaca.
- Order submission must be idempotent.
- Reconciliation must update runtime state when broker-side outcomes change.
- Portfolio state must remain aligned with broker fills and account state.

#### Runtime Orchestration

- The runtime must support single-cycle, loop, and realtime-triggered execution.
- The runtime must avoid overlapping execution for the same service loop.
- Freshness and staleness checks must prevent unsafe trading.

#### Minimal Runtime Observability

- The phase should include the minimum health/status capabilities required to operate the engine safely.
- Runtime metrics and event traces must allow post-hoc inspection of what the engine did.

### Non-Functional Requirements

- **Safety-first:** failures default to not trading.
- **Determinism where needed:** backtests and identity generation must be reproducible.
- **Traceability:** runtime decisions must be explainable through persisted state.
- **Operational simplicity:** keep the active phase focused on engine behavior, not interface or deployment productization.

---

## Phase 2 — Interfaces and Operational Surfaces

### Purpose

Add human-facing and operator-facing interfaces around the core engine once the engine scope is stable.

### Example capabilities

- frontend or UI workflows
- HTTP APIs built specifically for interface consumers
- richer health/status surfaces
- packaging splits such as `trader-core` and `trader-ui`
- deployment packaging and runtime ergonomics

### Non-Functional Theme

- **Separation of concerns:** interfaces should depend on the engine, not reshape it.

---

## Phase 3 — Analytics and Research Tooling

### Purpose

Add richer analytics and experiment visibility on top of the stable engine and runtime data model.

### Example capabilities

- Apache Superset dashboards
- research-oriented analytics views
- experiment tracking and comparison tooling

### Non-Functional Theme

- **Interpretability:** results should be understandable without reading runtime internals.

---

## Phase 4 — Packaging, Promotion, and Advanced Deployment

### Purpose

Treat strategies and runtime configurations as promotable artifacts and mature the system into a cleaner deployable platform.

### Example capabilities

- strategy packaging/promotion contracts
- runtime loading of promoted artifacts
- more formal deployment topologies and release separation

### Non-Functional Theme

- **Governance and isolation:** promotion and deployment should become explicit, auditable operations.

---

## Current Roadmap Interpretation

- The **active phase** is Phase 1.
- The current codebase already contains some deferred interface work, but that does not make it active-phase work.
- When there is a conflict between older Stage 0 wording and current runtime reality, the current runtime reality wins:
  - Postgres-first runtime
  - core-engine focus
  - frontend deferred
- The Phase 1 architecture review artifacts live in:
  - `docs/system_architecture.md`
  - `docs/runtime_hot_path_and_reconciliation.md`
