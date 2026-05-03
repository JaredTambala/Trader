# Platform Sprint Task Breakdown

Date: 2026-05-03

Source audit: `docs/platform_audit_2026-05-03.md`

## Working Rules

- Keep the active path focused on the core engine, not UI expansion.
- Every task should leave `uv run pytest` green.
- Add Postgres-backed validation when behavior depends on Postgres semantics.
- Prefer CLI and library surfaces before UI surfaces.
- Treat strategy authoring as normal Python injection unless a task explicitly says otherwise.
- Do not add new strategy families until backtest realism, experiment metadata, and operations are stronger.

## Sprint 1: Stabilize The Foundation

Goal: make the current engine trustworthy before adding new capabilities.

### S1.1 Repository Hygiene Cleanup

Objective:
Remove local runtime artifacts from the tracked package and make clone state reproducible.

Likely areas:

- `.gitignore`
- `README.md`
- tracked root files `events.duckdb`, `events_stock_test.duckdb`
- optional new `examples/data/` or `tests/fixtures/` policy docs

Tasks:

1. Decide whether any binary database file is an intentional fixture.
2. Remove runtime `.duckdb` files from version control if they are not deliberate fixtures.
3. Add `*.duckdb` to `.gitignore`, with an explicit exception only if fixture DBs are intentionally versioned.
4. Replace absolute local README links with repo-relative links.
5. Add a short note explaining where reproducible sample data should live.

Acceptance checks:

- `git ls-files '*.duckdb'` returns no runtime databases, or only documented fixtures.
- A new clone does not inherit local trading state.
- README links do not point to `/home/jared/...`.
- `uv run pytest` passes.

Dependencies:

- None.

### S1.2 Dependency And Packaging Cleanup

Objective:
Make runtime dependencies represent runtime needs, not test/development needs.

Likely areas:

- `pyproject.toml`
- `uv.lock`
- `README.md`
- `docs/testing.md`

Tasks:

1. Move `pytest` out of `[project].dependencies`.
2. Keep test tooling in dependency groups or optional test dependencies.
3. Audit whether UI dependencies belong in the core runtime install.
4. Verify `trader` and `trader_standard` import after a clean sync.
5. Document the intended install commands for runtime, development, and UI work.

Acceptance checks:

- `uv sync --dev` succeeds.
- `uv run python -c "import trader, trader_standard"` succeeds.
- `uv run pytest` passes.
- Runtime dependency list no longer includes test-only tools.

Dependencies:

- S1.1 is helpful but not required.

### S1.3 CI Baseline

Objective:
Make tests run automatically on every push or pull request.

Likely areas:

- `.github/workflows/ci.yml`
- `docs/testing.md`

Tasks:

1. Add a GitHub Actions workflow for Python 3.12.
2. Install `uv`.
3. Run `uv sync --dev`.
4. Run `uv run pytest`.
5. Cache dependencies if it stays simple.
6. Document the CI command locally.

Acceptance checks:

- CI workflow exists and runs `uv run pytest`.
- Local command matches CI command.
- No external secrets are required for the base unit suite.

Dependencies:

- S1.2 should land first if dependency groups change.

### S1.4 Ruff Baseline

Objective:
Introduce fast style and correctness linting without turning this into a cosmetic refactor.

Likely areas:

- `pyproject.toml`
- `src/`
- `tests/`
- `examples/`
- root scripts

Tasks:

1. Add `ruff` to dev dependencies.
2. Add conservative `ruff` config.
3. Run `uv run ruff check`.
4. Fix only actionable issues needed to establish the baseline.
5. Add the lint command to docs.
6. Decide whether CI should enforce ruff immediately or after one cleanup pass.

Acceptance checks:

- `uv run ruff check src tests examples run_*.py external_strategy_demo.py` passes, or a documented narrowed scope passes.
- `uv run pytest` passes.
- No broad unrelated formatting churn.

Dependencies:

- S1.2.

### S1.5 Type Checking Baseline

Objective:
Catch contract drift in public interfaces without requiring perfect typing everywhere.

Likely areas:

- `pyproject.toml`
- `src/trader/`
- `src/trader_standard/`
- `docs/testing.md`

Tasks:

1. Choose `mypy` or `pyright`.
2. Configure an incremental scope around public contracts first.
3. Type-check `trader.risk`, `trader.strategies.base`, `trader.broker`, key dataclasses, and config.
4. Add type ignores only where justified.
5. Document the command and the intended expansion path.

Acceptance checks:

- Type checker runs successfully on the agreed initial scope.
- Public strategy/risk/broker contracts are included.
- `uv run pytest` passes.

Dependencies:

- S1.2.

### S1.6 Postgres Test Harness

Objective:
Create a repeatable way to test runtime behavior against real Postgres.

Likely areas:

- `tests/`
- `tests/conftest.py`
- `docker-compose.postgres.yml`
- `docs/testing.md`
- `pyproject.toml`

Tasks:

1. Add a `postgres` pytest marker.
2. Add fixtures that connect to a test database from env vars.
3. Ensure tests skip clearly when Postgres is unavailable.
4. Provide a local command using `docker compose -f docker-compose.postgres.yml up -d`.
5. Ensure schema setup and cleanup are isolated per test run.

Acceptance checks:

- Unit suite still runs without Postgres.
- Postgres-marked tests can run locally when Postgres env vars are set.
- Skips are explicit, not silent passes.

Dependencies:

- S1.3 can happen before or after this.

### S1.7 Postgres Event Store Integration Tests

Objective:
Verify that the authoritative runtime store behaves as expected.

Likely areas:

- `src/trader/data.py`
- `tests/test_postgres_event_store.py`
- `docs/schema.md`

Tasks:

1. Test schema bootstrapping creates all current tables.
2. Test duplicate market bar insert idempotency.
3. Test run session start/finish.
4. Test cycle start/finish.
5. Test order lifecycle append behavior.
6. Test `session_id` columns are populated where expected.
7. Test metrics snapshot writes.
8. Test config key/value writes.

Acceptance checks:

- Postgres tests cover behavior that DuckDB tests cannot prove.
- Tests fail if `docs/schema.md` assumptions are wrong enough to affect runtime behavior.
- `uv run pytest` passes.

Dependencies:

- S1.6.

### S1.8 Postgres Notification Test

Objective:
Verify the event-driven path's trigger mechanism.

Likely areas:

- `src/trader/market_data_stream.py`
- `src/trader/notifications.py`
- `src/trader/market_data_backfill.py`
- `tests/test_postgres_notifications.py`

Tasks:

1. Test `NOTIFY` payload format for inserted bars.
2. Test channel name validation.
3. Test listener receives a payload with symbol, timeframe, timestamp, asset class, and source.
4. Test duplicate bar inserts do not create duplicate trigger semantics where the code promises idempotency.

Acceptance checks:

- Realtime trigger assumptions are verified against Postgres.
- Notification payloads are documented and tested.

Dependencies:

- S1.6.

### S1.9 Schema Documentation Synchronization

Objective:
Make schema docs match implementation.

Likely areas:

- `docs/schema.md`
- `docs/er.md`
- `src/trader/data.py`
- `tests/`

Tasks:

1. Add `trading_sessions` to schema docs.
2. Add `session_id` columns to all documented tables that include them.
3. Clarify which tables are append-only and which use upsert semantics.
4. Clarify Postgres as runtime store and DuckDB as test/support store.
5. Fix stale references to removed modules such as `src/trader/loader.py`.
6. Consider adding a schema assertion test that compares expected table/column names.

Acceptance checks:

- `docs/schema.md` matches `PostgresEventStore._ensure_schema`.
- Stale module references are removed or clearly marked historical.
- `uv run pytest` passes.

Dependencies:

- S1.7 is useful because it exposes schema facts.

## Sprint 2: Make Backtests More Truthful

Goal: reduce the chance of believing false research results.

### S2.1 Backtest Assumptions Model

Objective:
Represent execution assumptions explicitly in code and result payloads.

Likely areas:

- `src/trader/backtest.py`
- `docs/backtesting.md`
- examples
- tests

Tasks:

1. Add a small assumptions dataclass for fill model, fees, slippage, latency, and data constraints.
2. Add the assumptions object to `BacktestResult`.
3. Populate defaults that match current behavior.
4. Log assumptions at backtest start and completion.
5. Document all defaults.

Acceptance checks:

- Existing backtests still behave the same by default.
- `BacktestResult` exposes current assumptions.
- Tests verify defaults.

Dependencies:

- Sprint 1 is preferred first, but this can begin after S1.2.

### S2.2 Fee And Commission Model

Objective:
Support explicit transaction costs in backtests.

Likely areas:

- `src/trader/backtest.py`
- `src/trader/broker.py`
- `src/trader/portfolio.py`
- `docs/backtesting.md`
- config examples

Tasks:

1. Define fee config shape: fixed per order, basis points of notional, optional minimum fee.
2. Apply fees to cash accounting in backtest fills.
3. Persist fee values in fill or metrics payloads.
4. Include total fees in performance output.
5. Add tests for buy, sell, and round-trip fee accounting.

Acceptance checks:

- A deterministic round trip produces expected cash and PnL after fees.
- Backtest output includes total fees.
- Defaults preserve current no-fee behavior.

Dependencies:

- S2.1.

### S2.3 Deterministic Slippage Model

Objective:
Model simple slippage without introducing random unreproducibility.

Likely areas:

- `src/trader/backtest.py`
- `src/trader/broker.py`
- config examples
- tests

Tasks:

1. Define slippage config shape, starting with basis points of fill price.
2. Apply buy slippage as worse price and sell slippage as worse price.
3. Include slippage assumptions in `BacktestResult`.
4. Add tests for buy and sell adjusted fill prices.
5. Keep stochastic slippage out of scope until calibrated.

Acceptance checks:

- Same inputs produce same slippage-adjusted results.
- Slippage defaults to zero.
- Backtest docs state exactly how it is applied.

Dependencies:

- S2.1.

### S2.4 Fill Event Cost Fields

Objective:
Persist execution costs and adjusted fill assumptions in audit data.

Likely areas:

- `src/trader/data.py`
- `tests/support/duckdb_store.py`
- `docs/schema.md`
- `src/trader/backtest.py`
- tests

Tasks:

1. Decide whether to add columns to `fill_events` or store cost details in metrics payloads.
2. If columns are added, include `fee_amount`, `slippage_amount`, and possibly `raw_fill_price`.
3. Update Postgres schema and DuckDB test schema.
4. Update docs and tests.
5. Preserve compatibility for old rows with null cost fields.

Acceptance checks:

- Cost fields are queryable after a backtest.
- Old no-cost behavior still works.
- Schema docs match implementation.

Dependencies:

- S2.2 and S2.3 clarify what needs to be stored.

### S2.5 Accounting Scenario Tests

Objective:
Lock down portfolio/accounting correctness with small known examples.

Likely areas:

- `tests/test_backtest_accounting.py`
- `src/trader/backtest.py`
- `src/trader/portfolio.py`

Tasks:

1. Test buy opens position and reduces cash.
2. Test sell closes long and realizes expected PnL.
3. Test average price after multiple buys.
4. Test partial fill behavior.
5. Test fees and slippage together.
6. Test turnover and exposure calculations.
7. Test drawdown from a known equity curve.

Acceptance checks:

- Each test has explicit expected numbers.
- Tests do not depend on random prices or broker calls.
- `uv run pytest` passes.

Dependencies:

- S2.2 and S2.3 for cost cases.

### S2.6 Backtest Result Export Contract

Objective:
Make backtest outputs easy to inspect and compare outside Python internals.

Likely areas:

- `src/trader/backtest.py`
- `examples/`
- docs
- tests

Tasks:

1. Add a serializable result conversion helper.
2. Include assumptions, metrics, positions, equity curve, benchmark curve, and warnings.
3. Add JSON export helper.
4. Add CSV export helper for equity curves and trades if trade records are available.
5. Test serialization for datetimes and optional values.

Acceptance checks:

- One helper produces stable JSON-compatible data.
- Exported payload contains assumptions and key metrics.
- Existing UI/API consumers are not broken.

Dependencies:

- S2.1.

### S2.7 Fixed Sample Dataset

Objective:
Provide a reproducible dataset without checking in runtime database files.

Likely areas:

- `examples/data/`
- `tests/fixtures/`
- `docs/backtesting.md`
- `run_market_data_backfill.py` or a new fixture loader

Tasks:

1. Choose CSV or JSONL for a tiny deterministic OHLCV dataset.
2. Add a loader that imports the sample data into the event store.
3. Use symbols and dates that are obviously synthetic or documented sample data.
4. Add tests for loader behavior.
5. Document how to run a backtest against the sample.

Acceptance checks:

- No binary DB fixture is needed.
- A new clone can load sample data and run a backtest.
- Data provenance is explicit.

Dependencies:

- S1.1.

### S2.8 Reproducible Example Backtest

Objective:
Give a new quant a known-good baseline run.

Likely areas:

- `examples/run_reproducible_backtest.py`
- `configs/`
- `docs/backtesting.md`
- `README.md`

Tasks:

1. Create a config for the sample dataset.
2. Create an example runner using direct strategy/risk injection.
3. Print or export a stable result summary.
4. Document expected headline metrics for the sample.
5. Add a smoke test if feasible.

Acceptance checks:

- User can run one command after loading sample data and get deterministic output.
- Output states fees/slippage/fill assumptions.

Dependencies:

- S2.6 and S2.7.

## Sprint 3: Build The Research Loop

Goal: let strategy development become iterative and comparable.

### S3.1 Experiment Metadata Model

Objective:
Define how research runs are grouped and described.

Likely areas:

- `src/trader/data.py`
- `src/trader/backtest.py`
- `docs/schema.md`
- tests

Tasks:

1. Define an experiment identifier and name.
2. Decide whether to add `experiments` and `experiment_runs` tables or store metadata in run config snapshots.
3. Capture purpose, tags, created time, strategy ID, symbols, timeframe, and data window.
4. Add tests for persistence and lookup.
5. Document query patterns.

Acceptance checks:

- Multiple backtest runs can be grouped under one experiment.
- Experiment metadata is queryable without parsing logs.

Dependencies:

- S1.9.

### S3.2 Strategy Metadata Helper

Objective:
Make strategy identity richer than a free-form `strategy_id`.

Likely areas:

- `src/trader/strategy_metadata.py`
- `src/trader/strategies/base.py`
- `src/trader_standard/strategies/`
- examples
- tests

Tasks:

1. Add a `StrategyInfo` dataclass or equivalent helper.
2. Include name, version, description, parameters, and optional author/source.
3. Keep current `strategy_id` compatibility.
4. Add helper to resolve metadata from a strategy object.
5. Update standard strategies to expose useful metadata where practical.

Acceptance checks:

- Existing strategies still work.
- New metadata is available to backtests and trader service.
- Tests cover fallback behavior.

Dependencies:

- None, but it supports S3.3.

### S3.3 Run Provenance Capture

Objective:
Persist enough context to reproduce a run.

Likely areas:

- `src/trader/backtest.py`
- `src/trader/trader_service.py`
- `src/trader/config.py`
- `src/trader/strategy_metadata.py`
- tests

Tasks:

1. Capture strategy metadata.
2. Capture config snapshot.
3. Capture package version.
4. Capture git SHA and dirty flag when available.
5. Capture data window, symbols, timeframe, asset class, and cost model.
6. Store provenance in run/session metadata.

Acceptance checks:

- A completed backtest has enough metadata to identify code, data window, parameters, and assumptions.
- Git capture degrades gracefully outside a git repo.

Dependencies:

- S3.1 and S3.2.

### S3.4 Experiment Runner CLI

Objective:
Provide a repeatable command for research runs.

Likely areas:

- new `run_research_experiment.py`
- `examples/strategy_library_support.py`
- `docs/backtesting.md`
- tests

Tasks:

1. Add a CLI that takes config path and experiment name.
2. Build strategy/risk through a user-owned Python module or a constrained library example path.
3. Run `BacktestRunner`.
4. Persist experiment metadata.
5. Export result JSON.

Acceptance checks:

- One command produces a persisted experiment run and export.
- CLI does not become a general unsafe code loader.

Dependencies:

- S3.1 through S3.3.

### S3.5 Parameter Sweep Support

Objective:
Support small deterministic strategy parameter experiments.

Likely areas:

- new research helper module
- examples
- tests

Tasks:

1. Define a simple Cartesian grid config shape.
2. Generate deterministic parameter combinations.
3. Run backtests sequentially by default.
4. Persist each run under one experiment.
5. Add max-run guardrails.
6. Add tests for parameter expansion.

Acceptance checks:

- Sweep order is deterministic.
- Failed runs are recorded without losing successful run results.
- Large sweeps require explicit limits.

Dependencies:

- S3.4.

### S3.6 Result Comparison CLI

Objective:
Compare backtest results without manual SQL.

Likely areas:

- new `run_compare_results.py`
- `src/trader/metrics.py` or new research module
- docs
- tests

Tasks:

1. Load latest runs for an experiment.
2. Select key metrics: total return, Sharpe, max drawdown, turnover, fees, slippage, alpha, beta.
3. Print a compact table.
4. Support JSON output.
5. Include warnings when assumptions differ across compared runs.

Acceptance checks:

- Two runs can be compared from the CLI.
- Machine-readable output is stable enough for future agent use.

Dependencies:

- S3.1 and S2.6.

### S3.7 Export Helpers

Objective:
Make research artifacts portable to notebooks and dashboards.

Likely areas:

- `src/trader/backtest.py`
- new `src/trader/research.py`
- docs
- tests

Tasks:

1. Export metrics as JSON.
2. Export equity curve as CSV.
3. Export benchmark curve as CSV.
4. Export positions/trades where available.
5. Include run provenance in every export bundle.

Acceptance checks:

- Export paths are deterministic and documented.
- Exports include assumptions and run IDs.

Dependencies:

- S2.6 and S3.3.

### S3.8 First Strategy Tutorial

Objective:
Make the package approachable for an aspiring quant.

Likely areas:

- `docs/first_strategy.md`
- `examples/`
- sample config/data

Tasks:

1. Explain the mental model: data, strategy, risk, broker, backtest, live service.
2. Build one strategy from `trader_standard`.
3. Build one tiny custom external strategy.
4. Run a sample backtest.
5. Compare two results.
6. State all modeling limitations clearly.

Acceptance checks:

- A new user can follow the tutorial from a clean clone.
- The tutorial avoids UI and live broker requirements.

Dependencies:

- S2.7, S2.8, S3.6.

### S3.9 Data Quality As Research Provenance

Objective:
Connect data checks to experiment trust.

Likely areas:

- `src/trader/data_quality.py`
- `run_data_quality.py`
- experiment metadata
- docs

Tasks:

1. Allow data quality output to be saved as JSON.
2. Link data quality report IDs or payloads to experiments.
3. Include gap summaries in experiment provenance.
4. Warn when a backtest uses data with known quality gaps.

Acceptance checks:

- A research run can identify whether data quality checks were run.
- Data quality warnings are visible in result exports.

Dependencies:

- S3.1 and S2.7.

## Sprint 4: Live Paper Maturation

Goal: make paper trading operationally safer.

### S4.1 Runtime Status Query Layer

Objective:
Create reusable status queries independent of UI.

Likely areas:

- new `src/trader/runtime_status.py`
- `src/trader/data.py`
- tests
- docs

Tasks:

1. Query latest run/session.
2. Query latest cycle.
3. Query latest market data timestamp per symbol.
4. Query latest positions and cash.
5. Query latest open local orders.
6. Return JSON-serializable status objects.

Acceptance checks:

- Status can be generated from an event store without broker access.
- Tests cover empty store, healthy store, and failed latest cycle.

Dependencies:

- S1.9.

### S4.2 Operator CLI

Objective:
Expose operational state through commands.

Likely areas:

- new `run_runtime_status.py` or `run_operator.py`
- `docs/ops.md`
- tests

Tasks:

1. Add `status` command.
2. Add `health` command with exit codes.
3. Add `open-orders` command.
4. Add `positions` command.
5. Add `--json` output.
6. Keep broker-mutating actions out of read-only commands.

Acceptance checks:

- Commands work against local event store config.
- JSON output is parseable.
- Health command returns non-zero for failed/stale states.

Dependencies:

- S4.1.

### S4.3 Global Halt Implementation

Objective:
Make halt behavior enforceable and operator-controlled.

Likely areas:

- `src/trader/cycle.py`
- `src/trader/risk.py`
- `src/trader/data.py`
- operator CLI
- `docs/ops.md`
- tests

Tasks:

1. Add CLI commands to set, clear, and read halt state in `config_kv`.
2. Decide whether halt is core-enforced before risk or implemented as a required default risk manager.
3. Prefer core fail-closed behavior so a missing wrapper risk manager cannot bypass halt.
4. Persist explicit rejection or cycle skip reason when halted.
5. Add tests proving halt blocks orders even with permissive risk manager.

Acceptance checks:

- Operator can halt and unhalt from CLI.
- Orders are not submitted while halted.
- Halt state appears in status output.

Dependencies:

- S4.2.

### S4.4 Broker Contract Definition

Objective:
Clarify what every broker implementation must support.

Likely areas:

- `src/trader/broker.py`
- docs
- tests

Tasks:

1. Define required vs optional broker methods.
2. Document response payload fields.
3. Document status lifecycle expectations.
4. Identify Alpaca-specific assumptions to remove from generic contract.
5. Add type hints or protocols where useful.

Acceptance checks:

- Broker contract documentation is explicit.
- Existing broker implementations still satisfy the contract or clearly mark unsupported methods.

Dependencies:

- S1.5 is helpful.

### S4.5 Broker Conformance Tests

Objective:
Prevent broker implementations from drifting.

Likely areas:

- `tests/broker_conformance/`
- `tests/test_alpaca_broker.py`
- `tests/test_internal_broker_ordering.py`

Tasks:

1. Build a reusable conformance test mixin or helper.
2. Test deterministic client order ID handling.
3. Test accepted/filled/rejected/error response shape.
4. Test open-order lookup behavior where supported.
5. Test cancellation behavior where supported.
6. Run conformance suite against internal broker and fake Alpaca client.

Acceptance checks:

- New broker implementations have a clear test suite to satisfy.
- Existing tests still pass.

Dependencies:

- S4.4.

### S4.6 Broker Refresh Boundary Review

Objective:
Reduce ambiguous remote reads and duplicated account refreshes.

Likely areas:

- `src/trader/trader_service.py`
- `src/trader/cycle.py`
- `src/trader/metrics.py`
- docs
- tests

Tasks:

1. Map every `get_account` and `get_positions` call.
2. Decide which component owns account refresh per cycle.
3. Avoid metrics worker and trading cycle racing or duplicating expensive reads unnecessarily.
4. Add logging that states why a broker refresh happened.
5. Add tests with fake broker call counters.

Acceptance checks:

- Broker refresh behavior is documented.
- Tests prevent accidental duplicate refreshes in hot paths where avoidable.

Dependencies:

- S4.1 and S4.5.

### S4.7 Order Update Policy

Objective:
Decide and implement how live open orders are kept current after submission.

Likely areas:

- `src/trader/order_recovery.py`
- `src/trader/trader_service.py`
- `src/trader/broker.py`
- `docs/execution.md`
- tests

Tasks:

1. Decide cadence-based polling vs startup-only reconciliation vs broker stream support.
2. Start with a conservative periodic reconciliation option if needed.
3. Ensure reconciliation appends events rather than rewriting history.
4. Expose stale-open-order counts in status.
5. Add tests for stale local orders and broker-filled orders discovered later.

Acceptance checks:

- Live paper runs have a documented open-order update policy.
- Operator can see when local state is stale.

Dependencies:

- S4.1, S4.5, S4.6.

### S4.8 Operations Runbook Completion

Objective:
Make paper trading operation repeatable.

Likely areas:

- `docs/ops.md`
- `README.md`
- operator CLI docs

Tasks:

1. Document startup sequence.
2. Document status checks.
3. Document halt/unhalt.
4. Document recovery decision tree.
5. Document broker mismatch resolution.
6. Document expected logs and event queries.

Acceptance checks:

- An operator can follow the runbook without reading source.
- Runbook commands match implemented CLI commands.

Dependencies:

- S4.2, S4.3, S4.7.

## Sprint 5: Prepare For Quant-Shop Tooling

Goal: make the codebase ready for agents and tools without overbuilding prematurely.

### S5.1 Tool Command Contract

Objective:
Define stable machine-facing commands before adding agent orchestration.

Likely areas:

- `docs/tool_contracts.md`
- operator/research CLI modules
- tests

Tasks:

1. List supported commands for data, backtest, compare, status, halt, and recovery.
2. Define required inputs and JSON outputs.
3. Define exit codes.
4. Define commands that are read-only vs mutating.
5. Mark live broker actions as requiring explicit command names and configs.

Acceptance checks:

- Tool contracts can be read without source inspection.
- Commands avoid ambiguous side effects.

Dependencies:

- S3.6 and S4.2.

### S5.2 Machine-Readable CLI Output

Objective:
Make CLIs usable by agents, scripts, and humans.

Likely areas:

- backfill/replay/data quality/status/recovery scripts
- tests
- docs

Tasks:

1. Add `--json` output where absent.
2. Standardize success/error envelope.
3. Include run IDs and artifact paths in outputs.
4. Add tests that parse CLI JSON.
5. Keep default human output readable.

Acceptance checks:

- Important commands can emit valid JSON.
- Error payloads are structured enough for tooling.

Dependencies:

- S5.1.

### S5.3 Strategy Artifact Metadata

Objective:
Represent promoted strategies as auditable artifacts.

Likely areas:

- `src/trader/strategy_metadata.py`
- docs
- examples
- tests

Tasks:

1. Define artifact metadata: strategy name, version, source path/package, parameters, risk profile, data assumptions.
2. Capture source revision and dependency versions.
3. Define compatibility checks for runtime package version.
4. Store artifact metadata with runs.
5. Provide a validation helper.

Acceptance checks:

- Strategy artifacts can be described without importing arbitrary code in a control plane.
- Runtime still uses direct Python objects for execution.

Dependencies:

- S3.2 and S3.3.

### S5.4 Research To Paper Promotion Workflow

Objective:
Create a deliberate path from a researched strategy to paper deployment.

Likely areas:

- docs
- examples
- configs
- tests

Tasks:

1. Define minimum promotion criteria: sample size, max drawdown, turnover, data quality, cost assumptions.
2. Add a promotion checklist document.
3. Add a command or helper that packages selected metadata into a paper-run config.
4. Ensure paper config references the same strategy metadata and risk profile.
5. Add a dry-run validation step.

Acceptance checks:

- A backtest run can be traced to a proposed paper deployment config.
- Promotion does not start live trading by itself.

Dependencies:

- S5.3 and S4.2.

### S5.5 Agent-Safe Guardrails

Objective:
Prevent automation from accidentally trading or mutating broker state.

Likely areas:

- docs
- CLI command implementations
- tests

Tasks:

1. Classify commands as read-only, local-mutating, or broker-mutating.
2. Require explicit flags for broker-mutating commands.
3. Make default automation examples use backtest or dry-run modes.
4. Add tests that dangerous commands fail closed when required flags are absent.
5. Document environment variable and secret handling rules.

Acceptance checks:

- Tooling cannot accidentally start live paper trading through a generic command.
- Mutating behavior is explicit in command names, flags, and docs.

Dependencies:

- S5.1.

### S5.6 Thin Tool Wrappers

Objective:
Build tool-friendly wrappers over proven package APIs, not a second runtime.

Likely areas:

- new `src/trader/tools/`
- CLIs
- tests

Tasks:

1. Add Python functions for common tool actions: load config, run sample backtest, compare runs, read status.
2. Return structured dataclasses or JSON-compatible mappings.
3. Keep wrappers thin over existing APIs.
4. Add tests that wrappers match CLI behavior.

Acceptance checks:

- Tool wrappers do not duplicate trading logic.
- Agent-facing surfaces use the same tested package paths as humans.

Dependencies:

- S5.2.

### S5.7 Multi-Agent Workflow Documentation

Objective:
Document how agents should interact with the platform once the APIs are stable.

Likely areas:

- `docs/agent_workflows.md`
- `docs/tool_contracts.md`

Tasks:

1. Define roles: data auditor, strategy researcher, risk reviewer, operator assistant.
2. Define allowed commands per role.
3. Define handoff artifacts between roles.
4. Define escalation points for live trading decisions.
5. Keep humans in control of broker-mutating actions.

Acceptance checks:

- Agent workflows reference implemented commands.
- Documentation does not imply agents are part of the hot trading path.

Dependencies:

- S5.1, S5.5, S5.6.

### S5.8 End-To-End Tool Smoke Test

Objective:
Prove the tool-facing workflow works from clean inputs to structured outputs.

Likely areas:

- tests
- examples
- docs

Tasks:

1. Load sample data.
2. Run reproducible backtest.
3. Export result JSON.
4. Compare results.
5. Query status.
6. Verify all outputs are parseable and contain run IDs.

Acceptance checks:

- One automated smoke test covers the non-live research workflow.
- No Alpaca credentials are required.
- The test demonstrates the future agent/tool path without adding agent dependency.

Dependencies:

- S2.7, S2.8, S3.6, S5.2.

## Suggested Execution Order

The first practical backlog should be:

1. S1.1 Repository Hygiene Cleanup
2. S1.2 Dependency And Packaging Cleanup
3. S1.3 CI Baseline
4. S1.6 Postgres Test Harness
5. S1.7 Postgres Event Store Integration Tests
6. S1.9 Schema Documentation Synchronization
7. S2.1 Backtest Assumptions Model
8. S2.5 Accounting Scenario Tests

This order reduces hidden risk before adding research features.

