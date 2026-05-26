# Platform Audit: Core Quant Trading Engine

Date: 2026-05-03

> Historical audit baseline. Use [../core/operations/README.md](../core/operations/README.md), [../core/backtesting.md](../core/backtesting.md),
> [../core/schema.md](../core/schema.md), and [../core/testing.md](../core/testing.md) for the current operating documentation.

## Audit Purpose

This audit assesses the current repository as the foundation for a personal "quant shop in a box":

- event-driven backtesting
- live paper trading through a broker interface
- externally authored Python strategies
- composable risk controls
- market-data ingestion, replay, and quality checks
- pluggable audit/event data
- a codebase an aspiring quant can realistically use for strategy development

The audit is based on repository inspection, existing roadmap/design documents, and a full local test run.

Verification performed:

```bash
uv run pytest
```

Result: `80 passed, 12 warnings in 10.22s`.

The warnings are currently from deferred FastAPI/UI paths and a `websockets.legacy` deprecation.

## Executive Verdict

The system is past the "toy bot" stage. It has a real core engine architecture: direct strategy/risk injection,
event persistence, deterministic IDs, backtest/live cycle reuse, Postgres-first runtime design, Alpaca paper
execution, startup recovery, data ingestion/backfill/replay, and a reasonable first-party strategy library.

It is not yet a rock-solid public-quality quant package or a reliable research workbench for a new quant. The
largest remaining delta is not another strategy. The highest-leverage work is hardening: Postgres integration
tests, schema discipline, packaging hygiene, stronger backtest accounting realism, a reproducible research
workflow, and operational health controls.

Practical maturity estimate:

- Core engine foundation: strong partial completion.
- Phase 1 runtime thesis: mostly implemented, with hardening gaps.
- Aspiring-quant research platform: useful but not yet ergonomic or reproducible enough.
- Multi-agent quant-shop framework: later-phase idea; not blocked by architecture, but premature until the core
  package is stable.

## Current Strengths

### 1. Clear Core / Standard Boundary

The package split between `trader` and `trader_standard` is a strong design choice.

- `trader` exposes contracts, orchestration, state models, brokers, event stores, and runtime primitives.
- `trader_standard` contains maintained indicators, signals, risk managers, and strategies.
- `tests/test_core_boundary.py` verifies that core exports do not leak standard implementations.

This is exactly the right shape for a library that should support user-owned strategy code.

### 2. Injection-First Strategy Model

The system now avoids runtime code loading as the main extension mechanism. Users instantiate `Strategy` and
`RiskManager` objects in normal Python and inject them into `run_cycle`, `TraderService`, or `BacktestRunner`.

Evidence:

- `src/trader/strategies/base.py`
- `src/trader/risk.py`
- `examples/run_injected_backtest.py`
- `examples/run_injected_trader_service.py`
- `external_strategy_demo.py`

This is a good choice for serious experimentation because it keeps user strategy development debuggable,
importable, testable, and IDE-friendly.

### 3. Event-Sourced Runtime Foundation

The event model is coherent. The system records runs, cycles, bars, signals, indicators, orders, fills, positions,
metrics, and trading sessions.

Evidence:

- `src/trader/data.py`
- `docs/core/schema.md`
- `docs/core/system_architecture.md`
- `docs/core/runtime_hot_path_and_reconciliation.md`

The model is append-oriented where it matters, especially for order lifecycle and reconciliation.

### 4. Backtest / Live Conceptual Reuse

Backtests reuse `run_cycle(...)` and injected runtime objects. This is important: strategy logic is not forked into
a separate research-only path.

Evidence:

- `src/trader/backtest.py`
- `src/trader/cycle.py`
- `docs/core/backtesting.md`
- `docs/core/execution.md`

The backtest runner also computes a meaningful initial metric set: equity curve, buy-and-hold benchmark, drawdown,
Sharpe, Sortino, Calmar, exposure, trade stats, turnover, alpha, beta, tracking error, and information ratio.

### 5. Live Paper Safety Semantics

The live path includes several safety-first behaviors:

- deterministic client order IDs
- stale-data skip behavior
- Alpaca status normalization
- idempotent order submission checks
- startup order recovery
- local-open order repair
- broker-sourced portfolio reset
- fail-closed broker universe validation

Evidence:

- `src/trader/broker.py`
- `src/trader/order_recovery.py`
- `src/trader/trader_service.py`
- `tests/test_alpaca_broker.py`
- `tests/test_order_recovery.py`
- `tests/test_trader_service.py`

This is a meaningful foundation for paper trading.

### 6. Market Data Surface Is Broader Than Minimal

The repo includes:

- polling market data
- websocket streaming
- historical backfill
- replay into the realtime path
- data-quality checks

Evidence:

- `src/trader/alpaca_market_data.py`
- `src/trader/market_data_stream.py`
- `src/trader/market_data_backfill.py`
- `src/trader/market_data_replay.py`
- `src/trader/data_quality.py`

This is a major advantage over a backtest-only framework.

### 7. Test Suite Is Fast and Broad Enough To Support Refactoring

The current suite has 80 tests and runs quickly. It covers identifiers, config, core boundaries, cycle behavior,
market data, backtesting, risk, strategy library behavior, Alpaca broker behavior, recovery, symbols, and service
startup behavior.

That is enough coverage to support a stabilization sprint.

## Gap Register

### P0: Runtime Store Confidence Gap

The active architecture is Postgres-first, but most automated tests use `tests/support/duckdb_store.py`.

Risk:

- Postgres schema, SQL syntax, transaction behavior, `LISTEN/NOTIFY`, JSONB, array columns, and conflict behavior
  can drift from the test double.
- The runtime's most important dependency is not continuously verified.

Required action:

- Add a Postgres integration test profile using `docker-compose.postgres.yml`.
- Test schema bootstrapping, duplicate bar insert idempotency, run/cycle lifecycle, order lifecycle, metrics writes,
  recovery queries, and notification behavior against real Postgres.

### P0: Schema Documentation Drift

`docs/core/schema.md` does not fully match the current schema in `src/trader/data.py`.

Examples:

- The implementation has `trading_sessions`; `docs/core/schema.md` does not list it.
- The implementation has `session_id` on multiple event tables; `docs/core/schema.md` omits it in several places.
- Older audit docs still reference `src/trader/loader.py`, which no longer exists.

Risk:

- New contributors and future agents will reason from stale contracts.
- Analytics work will join against the wrong mental model.

Required action:

- Make `docs/core/schema.md` generated or at least schema-test-backed.
- Refresh older docs so `Stage 0` history does not read as active truth.

### P0: Repository Hygiene Gap

Tracked runtime data artifacts exist:

- `events.duckdb`
- `events_stock_test.duckdb`

`.env` exists locally and is ignored, which is correct, but tracked database artifacts should not remain part of the
package history unless they are intentional fixtures with documented provenance.

Other hygiene issues:

- `pytest` is included in main project dependencies as well as dev/test dependencies.
- There is no visible CI workflow.
- There is no configured formatter/linter/type checker.
- README links use absolute local paths in multiple places.

Required action:

- Remove or relocate tracked database artifacts.
- Add `*.duckdb` to `.gitignore` unless specific fixture DBs are deliberately versioned.
- Move `pytest` out of runtime dependencies.
- Add CI for `uv run pytest`.
- Add `ruff` and at least lightweight type checking for public contracts.

### P0: Operational Control Surface Is Incomplete

The runtime has good logs and event records, but operational controls are still skeletal.

Evidence:

- `docs/core/ops.md` says "Halt trading: set global halt flag (to be implemented)."
- `docs/core/execution.md` lists health/status runtime surface as a remaining gap.

Risk:

- A live process can be debugged after the fact, but there is not yet enough first-class health/control machinery
  for confident operation.

Required action:

- Implement a minimal operator surface:
  - read health/status
  - read latest cycle and run state
  - read broker/account summary
  - set/unset halt flag
  - inspect open local and broker orders

This can be CLI-first. A UI is not required.

### P1: Backtest Realism and Accounting Gap

Backtesting is structurally sound but not yet research-grade.

Known limitations:

- no fees or commissions
- no slippage model
- simple deterministic fill behavior unless internal broker randomness is configured
- limited fill-driven accounting depth across all modes
- no exchange calendar integration as a first-class backtest constraint
- no corporate actions / split / dividend handling
- no survivorship-bias controls
- no borrow, margin, or short-sale realism

Risk:

- A new quant can build strategies and get numbers, but those numbers can be too optimistic or misleading.

Required action:

- Add explicit execution-cost models before adding more strategies.
- Make backtest assumptions visible in result payloads.
- Add scenario tests with known fills, realized PnL, cash, exposure, drawdown, and turnover.

### P1: Research Workflow Gap

The package can run a backtest, but it does not yet provide a clean research loop.

Missing or partial:

- experiment registry
- strategy version/hash capture
- dataset snapshot/provenance
- parameter sweep or walk-forward workflow
- result comparison CLI
- canonical example dataset
- "first strategy" tutorial for a new quant
- artifact export for notebooks or dashboards

Required action:

- Build a small experiment layer on top of `BacktestRunner`, not inside strategy code.
- Persist experiment metadata alongside run/session data.
- Provide one reproducible sample workflow from data ingestion to strategy comparison.

### P1: Strategy Promotion and Versioning Gap

Strategies are externally injectable, which is good. But promoted strategy artifacts are not yet governed.

Missing:

- formal strategy metadata beyond `strategy_id`
- code version / git SHA capture
- dependency/version capture
- config schema for strategy-specific parameters
- promotion path from research to paper runtime

Required action:

- Keep direct Python injection as the authoring model.
- Add explicit metadata helpers for strategy name, version, parameter schema, and source revision.
- Store those values in run/session metadata.

### P1: Broker Interface Is Alpaca-Centric

The broker abstraction exists, but live implementation maturity is centered on Alpaca paper.

Risk:

- The broker contract may still encode Alpaca assumptions as more venues are added.

Required action:

- Define a stricter broker contract around order submission, order lookup, open orders, account state, positions,
  cancellation, and reconciliation.
- Add a fake broker conformance test suite that every broker implementation must pass.

### P1: Monolithic Hot-Path Modules

Some core files are now large:

- `src/trader/backtest.py`: 1772 lines
- `src/trader/data.py`: 1471 lines
- `src/trader/cycle.py`: 1317 lines
- `src/trader/trader_service.py`: 676 lines
- `src/trader/broker.py`: 683 lines

This is acceptable at the current phase, but it will slow future work if the next phase adds optimization,
multi-agent tooling, and more broker/data adapters.

Required action:

- Do not do a cosmetic refactor immediately.
- Extract only around real pressure points:
  - schema/migrations from event-store writes
  - backtest metrics/accounting from replay orchestration
  - cycle market-data readiness from order execution
  - broker conformance helpers from Alpaca implementation

### P2: UI/API Surface Is Deferred But Still In-Tree

The repo contains `src/ui/` and `src/trader/api.py`, but the active roadmap correctly classifies these as deferred.

Risk:

- Future work may accidentally optimize deferred interface paths before the core engine is stable.

Required action:

- Keep UI/API tests passing.
- Do not prioritize new UI work until the core package hardening and research workflow are complete.

## Capability Matrix

| Capability | Current Status | Audit Assessment |
| --- | --- | --- |
| Core Python package | Implemented | Good foundation; needs package hygiene and public API discipline |
| Strategy definition | Implemented | Direct injection is strong and should remain the default |
| Risk management | Implemented | Composable pipeline is good; expand standard managers over time |
| Event-driven live loop | Implemented | LISTEN/NOTIFY path exists; needs Postgres integration tests |
| Backtesting | Implemented | Strong structure; realism/accounting assumptions need hardening |
| Broker interface | Partial | Alpaca paper path is meaningful; broker conformance is missing |
| Audit data system | Partial/strong | Good event model; docs/schema and migration discipline need work |
| Market data ingestion | Implemented | Stronger than minimal; provenance and validation can improve |
| Monitoring/ops | Partial | Logs/events exist; health/halt/status surface remains incomplete |
| Data quality | Partial | Good start; needs to become part of research dataset governance |
| Strategy research loop | Partial | Can run experiments manually; needs registry/comparison/reproducibility |
| New quant onboarding | Partial | Examples exist; missing curated tutorial, sample data, and assumptions guide |
| Multi-agent framework | Deferred | Should wait until package contracts and artifacts are stable |

## Recommended Reprioritization

Detailed task breakdown: `docs/history/platform_sprint_task_breakdown_2026-05-03.md`

### Sprint 1: Stabilize The Foundation

Goal: make the current engine trustworthy before adding new capabilities.

Tasks:

1. Add CI running `uv run pytest`.
2. Add Postgres integration tests for event store, schema, run/cycle lifecycle, order lifecycle, and notification behavior.
3. Remove or relocate tracked `.duckdb` runtime artifacts.
4. Add `ruff` and basic type checking.
5. Move test-only dependencies out of runtime dependencies.
6. Refresh `docs/core/schema.md` and stale planning references.
7. Replace absolute README paths with repo-relative links.

Definition of done:

- A new clone can run tests without hidden local state.
- Runtime schema docs match implementation.
- Postgres behavior is tested directly.

### Sprint 2: Make Backtests More Truthful

Goal: reduce the chance of believing false research results.

Tasks:

1. Add explicit commission/fee model.
2. Add slippage model with a simple deterministic baseline.
3. Make fill model assumptions visible in `BacktestResult`.
4. Add scenario tests for cash, realized PnL, position averaging, partial fills, turnover, and exposure.
5. Add a fixed sample dataset and one reproducible example backtest.

Definition of done:

- Backtest result payloads state their assumptions.
- A new quant can inspect a simple strategy result and understand what is and is not modeled.

### Sprint 3: Build The Research Loop

Goal: let strategy development become iterative and comparable.

Tasks:

1. Add experiment metadata around `BacktestRunner`.
2. Persist strategy version, code revision, parameters, data window, symbols, and cost model.
3. Add a result comparison CLI.
4. Add a "first strategy" tutorial using the standard library and an external custom strategy.
5. Add export helpers for JSON/CSV metrics and equity curves.

Definition of done:

- Two backtests can be compared without reading internal tables manually.
- Results are reproducible from recorded metadata.

### Sprint 4: Live Paper Maturation

Goal: make paper trading operationally safer.

Tasks:

1. Implement CLI-first health/status/halt commands.
2. Add broker conformance tests.
3. Make broker/account refresh boundaries explicit.
4. Add structured runtime event summaries for latest run, latest cycle, open orders, and broker positions.
5. Decide whether order updates should be polled, reconciled on cadence, or streamed where the broker supports it.

Definition of done:

- An operator can answer "is it safe, live, halted, stale, or out of sync?" without opening Python internals.

### Sprint 5: AI-Toolable Signal Discovery

Goal: make the codebase ready for a tool-using quant workflow where Codex is a first-class customer, while the same
contracts also support other AI assistants, orchestration systems, and scripts. These tool clients should be able to
prepare recent market data, run controlled research suites, compare results, recommend candidate strategies, and
package promotion proposals for human-reviewed Alpaca paper trading.

The target interaction is intentionally high-level: a human quant should be able to ask an AI/tool client to pull data
for specific symbols and research selected strategy families. The platform should then expose bounded, structured tool
calls for data planning/backfill, quality checks, suite execution, comparison, recommendations, and dry-run promotion
packaging.

The workflow should also be iterative. AI/tool clients should be able to use Sprint 4 operator outputs (`status`,
`health`, `positions`, `open-orders`, halt state) and prior strategy/result artifacts (`result.json`, `metrics.json`,
`provenance.json`, trades, and strategy metadata) as inputs when comparing strategies and deciding what experiment to
run next.

Tasks:

1. Define a discovery request contract covering symbols, asset class, timeframe, data window, strategy families,
   parameter budget, assumptions, risk profile, output directory, dry-run behavior, optional operator-state context,
   and optional prior strategy/result artifacts.
2. Define stable tool-facing commands around recent data acquisition, data quality, research suites, result comparison,
   recommendations, live status, halt, and recovery.
3. Add research-suite definitions so multiple standard-library strategies and parameter sweeps can be run
   deterministically from config.
4. Add recommendation scoring and rejection explanations based on return, risk, turnover, costs, data quality,
   warnings, assumption compatibility, current operator state, and prior strategy outputs.
5. Add strategy artifact metadata and promotion-packet rules that trace a recommended backtest to a proposed paper
   config.
6. Keep AI systems outside the hot path; discovery can be automated, but paper trading still requires explicit human
   operator action.
7. Build only thin automation wrappers over proven package APIs, including one orchestration helper that turns a
   validated discovery request into data, research, comparison, recommendation, operator-context, and artifact outputs.

Definition of done:

- An AI/tool client can execute the non-live discovery workflow and inspect structured outputs without scraping logs.
- The workflow produces ranked recommendations with auditable reasons and artifacts.
- The workflow can use Sprint 4 operator JSON and prior strategy output files as context for follow-up experiment
  suggestions.
- A recommendation can be converted into a dry-run paper promotion packet without starting paper trading.
- The trading engine remains a normal Python package, not an AI-system-dependent platform.

## Suggested North Star For The Next Phase

The next phase should not be "add more strategies." It should be:

> Make one simple strategy development loop boringly reproducible from data ingest to backtest comparison to paper
> deployment, with tested Postgres persistence and explicit assumptions.

That milestone would make the project meaningfully useful to an aspiring quant while preserving the architecture
needed for a later multi-agent quant-shop layer.
