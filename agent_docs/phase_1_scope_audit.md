# Phase 1 Scope Audit

This document reconciles the refactored Phase 1 roadmap with the current codebase.

## Audit Method

The audit was performed by comparing:

- active planning docs
  - `agent_docs/stage_0_task_tracker.md`
  - `agent_docs/stage_0_task_backlog_remote_paper_trading_system_alpaca.md`
  - `agent_docs/master_design_document.md`
  - `README.md`
- current code structure under `src/trader/` and `src/ui/`
- current test coverage under `tests/`
- existing plan files under `plans/`

Each category below records:

- intended Phase 1 status
- code evidence
- test evidence
- documentation evidence
- conclusion
- action required

---

## Phase 1 Retained Capabilities

### Ingestion

- Intended Phase 1 status: retained
- Code evidence:
  - `src/trader/market_data.py`
  - `src/trader/alpaca_market_data.py`
  - `src/trader/market_data_stream.py`
  - `src/trader/market_data_backfill.py`
  - `src/trader/market_data_replay.py`
  - `src/trader/data_quality.py`
- Test evidence:
  - `tests/test_market_data.py`
  - `tests/test_market_data_stream.py`
  - `tests/test_market_data_backfill.py`
- Doc evidence:
  - `README.md`
  - `agent_docs/stage_0_task_tracker.md`
  - `agent_docs/stage_0_task_backlog_remote_paper_trading_system_alpaca.md`
- Conclusion:
  - Ingestion and supporting data tooling are clearly part of the retained core.
- Action required:
  - none beyond normal maintenance

### Event store and state model

- Intended Phase 1 status: retained
- Code evidence:
  - `src/trader/data.py`
  - `src/trader/portfolio.py`
- Test evidence:
  - `tests/test_data.py`
  - `tests/support/duckdb_store.py`
- Doc evidence:
  - `README.md`
  - `agent_docs/stage_0_task_tracker.md`
  - `agent_docs/stage_0_task_backlog_remote_paper_trading_system_alpaca.md`
- Conclusion:
  - The code is Postgres-first at runtime and still keeps DuckDB for tests.
- Action required:
  - keep future docs explicit that DuckDB is not the runtime source of truth

### Strategy model

- Intended Phase 1 status: retained
- Code evidence:
  - `src/trader/strategy.py`
  - `src/trader/strategies/`
  - `external_strategy_demo.py`
- Test evidence:
  - `tests/test_strategy_sma.py`
  - `tests/test_cycle.py`
  - external demo smoke path
- Doc evidence:
  - `README.md`
  - `agent_docs/stage_0_task_tracker.md`
- Conclusion:
  - Strategy externalization is implemented through direct imports and object injection and belongs in Phase 1.
- Action required:
  - continue documenting strategy authoring around direct imports and object injection

### Risk model

- Intended Phase 1 status: retained
- Code evidence:
  - `src/trader/risk.py`
  - `src/trader/cycle.py`
  - `src/trader/trader_service.py`
  - `src/trader/backtest.py`
- Test evidence:
  - `tests/test_risk_manager.py`
  - `tests/test_cycle.py`
  - `tests/test_market_data.py`
- Doc evidence:
  - `README.md`
  - `agent_docs/stage_0_task_tracker.md`
- Conclusion:
  - Risk is now a distinct runtime layer and fits the new phase definition well.
- Action required:
  - none for scope alignment

### Backtesting

- Intended Phase 1 status: retained
- Code evidence:
  - `src/trader/backtest.py`
  - `src/trader/cycle.py`
  - `src/trader/metrics.py`
- Test evidence:
  - `tests/test_backtest.py`
  - `tests/test_cycle.py`
- Doc evidence:
  - `README.md`
  - `agent_docs/stage_0_task_tracker.md`
- Conclusion:
  - Backtesting is a core retained engine capability.
- Action required:
  - keep backtest documentation focused on the core runner, not UI launch flows

### Live execution / trader service

- Intended Phase 1 status: retained
- Code evidence:
  - `src/trader/trader_service.py`
  - `src/trader/cycle.py`
  - `run_trader_service.py`
- Test evidence:
  - `tests/test_trader_service.py`
  - `tests/test_cycle.py`
- Doc evidence:
  - `README.md`
  - `agent_docs/stage_0_task_tracker.md`
- Conclusion:
  - Runtime orchestration is essential to the retained live-execution scope.
- Action required:
  - none for scope alignment

### Alpaca integration

- Intended Phase 1 status: retained
- Code evidence:
  - `src/trader/broker.py`
  - `src/trader/cycle.py`
  - `src/trader/trader_service.py`
- Test evidence:
  - `tests/test_alpaca_broker.py`
- Doc evidence:
  - `README.md`
  - `agent_docs/stage_0_task_tracker.md`
- Conclusion:
  - Alpaca paper execution is implemented and central to the current phase.
- Action required:
  - keep startup recovery, local-only clean-start semantics, broker-driven portfolio reset, and fail-closed mismatch handling documented as part of runtime safety

### Observability and runtime metrics

- Intended Phase 1 status: retained
- Code evidence:
  - `src/trader/metrics.py`
  - `src/trader/data.py`
  - `src/trader/cycle.py`
- Test evidence:
  - covered indirectly through cycle/backtest/event tests
- Doc evidence:
  - `README.md`
  - `agent_docs/stage_0_task_tracker.md`
- Conclusion:
  - Metrics snapshots and runtime traces are retained as core observability, not analytics UI.
- Action required:
  - none for scope alignment

---

## Deferred Capabilities Still Present in Repo

### Interface layer

- Intended Phase 1 status: deferred
- Code evidence:
  - `src/ui/`
  - `src/trader/api.py`
- Test evidence:
  - `tests/test_backtest_api.py`
- Doc evidence:
  - historical references in plans and older README content
- Conclusion:
  - The interface layer exists and is functional enough to keep, but it is not active-phase work.
- Action required:
  - keep interface work documented as deferred only

### UI-specific plans

- Intended Phase 1 status: deferred
- Code evidence:
  - none required; these are planning artifacts
- Test evidence:
  - none
- Doc evidence:
  - `plans/task_0_8b_breakdown.md`
  - `plans/task_0_8g_reflex_ui_refactor_plan.md`
- Conclusion:
  - These plans remain useful for later phases and should not be treated as current commitments.
- Action required:
  - reference them only from deferred tasks

### Deployment/platform packaging

- Intended Phase 1 status: deferred
- Code evidence:
  - `docker-compose.postgres.yml`
- Test evidence:
  - none specific
- Doc evidence:
  - task references in tracker/backlog
- Conclusion:
  - local development infrastructure exists, but deployment-productization is not current-phase scope.
- Action required:
  - keep local Postgres guidance; defer VPS/container roadmap language

### Superset / analytics

- Intended Phase 1 status: deferred
- Code evidence:
  - none implemented yet
- Test evidence:
  - none
- Doc evidence:
  - backlog/tracker task references
- Conclusion:
  - analytics remain a later-phase idea only.
- Action required:
  - none beyond preserving the deferred task

---

## Mismatch Register

### 1. Authoritative store mismatch

- Previous mismatch:
  - planning docs described DuckDB as authoritative
  - runtime code is Postgres-first
- Code evidence:
  - `src/trader/data.py`
  - `README.md`
- Conclusion:
  - fixed in the refactored docs
- Action required:
  - avoid reintroducing DuckDB-first language in active docs

### 2. Phase purpose mismatch

- Previous mismatch:
  - docs framed the phase around remote deployment and broad platform scope
  - actual intent is core engine first
- Code evidence:
  - core runtime concentration under `src/trader/`
- Conclusion:
  - fixed in tracker, backlog, README, and design doc
- Action required:
  - preserve the new phase framing in future roadmap edits

### 3. Frontend scope mismatch

- Previous mismatch:
  - tracker/backlog/README treated Reflex UI as active scope
  - current product direction removes frontend from Phase 1
- Code evidence:
  - `src/ui/`
  - `src/trader/api.py`
- Conclusion:
  - fixed by reclassifying UI work as deferred
- Action required:
  - keep UI work clearly labeled as later-phase or experimental

### 4. Strategy loading mismatch

- Previous mismatch:
  - older docs mixed built-in `strategy.type` guidance with the current class-path model
- Code evidence:
  - `src/trader/config.py`
  - `src/trader/cycle.py`
  - `src/trader/backtest.py`
- Conclusion:
  - fixed in the README and Phase 1 docs
- Action required:
  - keep direct injection as the only documented strategy path

### 5. Health/status mismatch

- Updated scope decision:
  - health/status endpoints are no longer treated as Phase 1 work
- Code evidence:
  - `src/trader/web.py`
- Conclusion:
  - resolved by deferring the task beyond Phase 1 rather than treating it as an active gap
- Action required:
  - keep any future HTTP status work tied to a later client/application phase

### 6. Deployment/package split mismatch

- Previous mismatch:
  - these items were mixed into the active roadmap
- Code evidence:
  - `plans/task_0_8g_reflex_ui_refactor_plan.md`
  - `docker-compose.postgres.yml`
- Conclusion:
  - fixed by deferring them beyond Phase 1
- Action required:
  - treat them as later-phase work only

### 7. Task history mismatch

- Previous mismatch:
  - early tracker entries still described obsolete DuckDB-first behavior as if it were current
- Code evidence:
  - runtime code now contradicts those older descriptions
- Conclusion:
  - fixed by rewriting the tracker and backlog around current architecture
- Action required:
  - preserve history only as notes, not as active truth

---

## Recommended Follow-Up Tasks

### 1. Refresh lower-level docs for architectural consistency

- Review:
  - `docs/schema.md`
  - `docs/execution.md`
  - `docs/ops.md`
  - `docs/backtesting.md`
- Ensure they do not drift back toward UI-first or DuckDB-first language.

### 2. Decide how long deferred interface code remains in-tree

- The current audit only reclassifies it.
- A later decision can determine whether the deferred UI/API code should stay in the monorepo, move to a separate package, or be archived.

### 3. Revisit internal-broker realism only when calibration targets exist

- Richer slippage/distribution work should not resume until there is a concrete empirical or product target.
- Until then, the current internal-broker tunables are sufficient for the completed Phase 1 scope.
