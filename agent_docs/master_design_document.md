# Trading System Roadmap — Functional & Non-Functional Requirements

This document summarises the **functional requirements (what the system must do)** and **non-functional requirements (how the system must behave)** for each stage of the trading system roadmap.

The roadmap is explicitly **value-driven**:
- early stages prioritise *real execution, traceability, and safety*
- later stages add *research scale, experimentation, and advanced data infrastructure*
- infrastructure complexity is introduced only when it unlocks new capability


---
## Global Definition of Done (applies to all stages)

A stage, feature, or task is considered done only when all of the following are true:

# Engineering & Quality
- The functionality is fully implemented and works as specified
- Automated tests are added or updated where applicable
- All tests pass in CI (pytest or equivalent)
- Public interfaces and contracts are stable and intentional

# Documentation (Mandatory)

- Relevant documentation is updated as part of the change, not after:
- what was built
- why it exists
- how to run it
- how to validate correctness
- Any change to data models, schemas, or interfaces includes an explicit documentation update

# Traceability & Auditability

- All behaviour introduced by the change is traceable via logs, events, or persisted state
- Identifiers, versions, and assumptions are explicit and discoverable

# Safety & Operations

- Failure modes default to safe behaviour (no trading, no corruption)
- Operational procedures (start, stop, halt, recover) are documented

# Stage Integrity

- The change does not introduce future-stage infrastructure prematurely
- Complexity added is justified by the current stage’s goals

---

## Stage 0 — Remote Paper Trading Skeleton (Execution Exists)

### Purpose
Establish a **remotely deployed, always-on paper trading bot** that operates independently of the developer machine and provides full traceability of all actions.

This stage proves that:
> *“I can run a real trading system in the cloud, safely, and observe it.”*

---

### Functional Requirements

#### Execution & Deployment
- The system **must run remotely** (e.g. VPS or cloud container).
- The system **must not require the developer PC** to be running.
- The trading loop must be executable as a **single-cycle run** (scheduled or triggered).
- Deployment must be reproducible and documented.

#### Market Data Ingestion
- The system must ingest live or near-live market data:
  - polling or websocket (“streaming-lite”) is sufficient
- Raw market data events must be persisted before signal generation.

#### Strategy & Signal Generation
- The system must support at least one trading strategy.
- The strategy must operate on a defined trading universe.
- The strategy must produce explicit signals or target positions.

#### Risk Management
- The system must enforce:
  - a global halt switch
  - maximum orders per run
  - maximum gross exposure
  - maximum per-symbol exposure
- Risk checks must run **before** order placement.

#### Order Execution (Paper)
- The system must place paper orders via:
  - an internal paper broker or
  - a broker-provided paper environment
- Orders must follow a deterministic lifecycle:
  - created → submitted → filled/rejected

#### Idempotency
- All execution must be **idempotent**:
  - re-running the same cycle must not duplicate orders
- Deterministic identifiers must exist for:
  - runs
  - orders

#### State & Traceability
- All operations must be traceable via persistent storage:
  - market data events
  - signals / targets
  - orders
  - fills
  - positions
  - run outcomes
- Storage must support transactional guarantees (DuckDB chosen).

#### Observability
- The system must expose:
  - `/health` endpoint
  - `/status` endpoint
- Operators must be able to determine:
  - whether the bot is running
  - whether it is safe
  - what it last did

---

### Non-Functional Requirements

- **Reliability:**  
  The system must survive restarts and crashes without corrupting state.

- **Simplicity:**  
  Single-node, single-process architecture preferred.

- **Safety-first:**  
  Failure modes must default to *not trading*.

- **Traceability:**  
  Every decision must be explainable post-hoc.

- **Low operational overhead:**  
  No managed services required at this stage.

---

## Stage 1 — Execution-Aligned Backtesting

### Purpose
Ensure that backtests are **truthful** by reusing the same execution logic as live trading.

---

### Functional Requirements

- Backtests must reuse:
  - strategy logic
  - risk checks
  - order generation logic
- A simulated broker must model:
  - fills
  - costs
  - slippage
- Backtests must support walk-forward or rolling evaluation.
- Backtest outputs must include:
  - trades
  - PnL
  - drawdowns
  - turnover
- Backtests must be reproducible from stored inputs.

---

### Non-Functional Requirements

- **Determinism:**  
  Same inputs must produce identical results.

- **Consistency:**  
  Live and backtest execution paths must not diverge.

- **Auditability:**  
  Backtest decisions must be traceable like live decisions.

---

## Stage 2 — Experiment Tracking (MLflow for Research)

### Purpose
Enable **transparent, repeatable experimentation** and comparison of strategies.

---

### Functional Requirements

- Backtests must log to an experiment tracking system (MLflow):
  - parameters
  - metrics
  - artifacts
  - dataset identifiers
- Experiments must be comparable across runs.
- Strategy versions must be identifiable and reproducible.

---

### Non-Functional Requirements

- **Isolation:**  
  Live trading must not depend on MLflow availability.

- **Reproducibility:**  
  Experiments must be reconstructable from logged metadata.

- **Clarity:**  
  Results must be interpretable without reading code.

---

## Stage 3 — Strategy-as-Model Packaging & Promotion Contract

### Purpose
Treat a strategy as a **deployable, versioned artifact** that can be promoted to live trading.

---

### Functional Requirements

- Strategies must be packageable as deployable models:
  - including logic, configuration, and metadata
- A model registry must exist with:
  - clear versioning
  - promotion semantics (e.g. candidate → production)
- Compatibility checks must validate:
  - feature schemas
  - universe definitions
  - risk constraints

---

### Non-Functional Requirements

- **Governance:**  
  Promotion to live must be explicit and auditable.

- **Decoupling:**  
  Strategy promotion must not require code redeployment.

---

## Stage 4 — Live Consumption of Promoted Models

### Purpose
Allow the live trading bot to **load strategies dynamically** based on registry state.

---

### Functional Requirements

- Live bot must load the currently promoted strategy by alias/stage.
- The system must support:
  - fallback to last-known-good model
  - safe halting on validation failure
- All live decisions must be tagged with:
  - model version
  - feature version

---

### Non-Functional Requirements

- **Resilience:**  
  Live trading must tolerate registry outages.

- **Traceability:**  
  Every trade must be attributable to a specific model version.

---

## Stage 5 — Out-of-Sample Monitoring & Retraining Triggers

### Purpose
Turn live paper performance into **actionable feedback**.

---

### Functional Requirements

- Continuous out-of-sample metrics must be computed:
  - performance
  - risk
  - execution quality
- Retraining triggers must be defined:
  - performance degradation
  - drawdown breaches
  - time-based retraining
  - drift indicators
- Retraining requests must be explicitly recorded.

---

### Non-Functional Requirements

- **Separation of concerns:**  
  Monitoring and retraining logic must not block live trading.

- **Explainability:**  
  Retraining decisions must be reviewable.

---

## Stage 6 — Automated Retraining & Promotion Gates

### Purpose
Make retraining **systematic, repeatable, and safe**.

---

### Functional Requirements

- Automated pipelines must:
  - rebuild datasets
  - retrain models
  - backtest candidates
  - log results
- Promotion gates must enforce:
  - performance thresholds
  - stability checks
  - risk sanity checks
- Optional shadow or canary evaluation must be supported.

---

### Non-Functional Requirements

- **Determinism:**  
  Retraining runs must be reproducible.

- **Governance:**  
  Promotions must leave an audit trail.

---

## Stage 7 — Data Lake, Tick Data & Microstructure Research

### Purpose
Support **high-resolution data and advanced research** without destabilising execution.

---

### Functional Requirements

- Object storage for large datasets.
- Columnar formats (e.g. Parquet) for analytical access.
- Table formats (e.g. Iceberg) for large-scale querying.
- Separate research environment for tick / order book data.

---

### Non-Functional Requirements

- **Isolation:**  
  Research infrastructure must not compromise live execution.

- **Scalability:**  
  Data and compute must scale independently.

- **Extensibility:**  
  Architecture must accommodate thesis-driven microstructure research.

---

## Final Architectural Constraint

> **The execution event store is always authoritative.**  
> Analytical systems, lakes, and research tooling are *derived*, never primary.

This constraint allows the system to grow from a lean paper trader into a serious research and execution platform without collapsing under its own complexity.
