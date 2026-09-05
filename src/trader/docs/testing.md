# Testing

## Standards

- Use `uv` for dependency management and all local quality commands.
- Keep unit tests fast and deterministic.
- Use Postgres-backed integration tests for runtime-store behavior that DuckDB cannot prove.
- Keep deferred UI/interface tests green, but do not let them reshape the core-engine test strategy.

## Test Ownership

Core-owned tests live under `tests/trader/<bounded-context>/`; repository-wide seams live under
`tests/cross_package/`. The backtest suite, for example, separates runner orchestration, HTTP compatibility, broker
isolation, export payloads, portfolio state, replay data, trade accounting, result assembly, and statistical
performance into focused modules under `tests/trader/backtest/`. These modules share an owner but remain separate
because each protects a different production contract. The cross-repository placement and narrative rules are defined
in [Repository And Test Architecture](../../../docs/test_architecture.md).

The cycle suite follows the same rule under `tests/trader/cycle/`: whole-pipeline behavior is distinct from pure
market-data, lifecycle, order-recording, broker-state, risk, metrics, stream, configuration, and event-persistence
contracts. Package-owned factories centralize only the configuration and market-event values shared across those
cycle modules.

The event-store suite lives under `tests/trader/event_store/`. Its deterministic modules separately protect the base
interface, filtering, buffering, lifecycle builders, record normalization, SQL shapes, factory configuration, schema
metadata, adapter wiring, and the shared DuckDB adapter used by deterministic workflows. The guarded Postgres modules
then prove the behavior that fakes cannot: real schema bootstrap, lifecycle persistence, natural-key idempotency,
append-only records, status queries, and notifications. The word `postgres` in a module name identifies the production
subject; only tests marked `postgres` require the guarded database environment.

The market-data suite lives under `tests/trader/market_data/` and separates ingestion, backfill, gap analysis, quality
summaries, stable quality-report export, query execution, pure query shaping, and streaming. Provider behavior is
exercised through injected fakes; the stream import contracts use bounded fresh Python processes to prove that optional
Alpaca dependencies remain lazy and their upstream warning is contained. Research symbol discovery and catalogue
providers are not core market-data tests: their contracts belong to `tests/trader_research/data/` because
`trader_research` owns that service boundary.

The portfolio suite lives under `tests/trader/portfolio/`. It distinguishes the public state-flow contract from model
validation, raw order normalization, arithmetic, event persistence, row reconstruction, snapshot construction,
snapshot query planning, and immutable multi-order transitions. DuckDB is used only where the public reconstruction
flow needs a real queryable store; the other modules keep persistence planning and domain decisions deterministic.

Provider-neutral inference contracts live under `tests/trader/predictions/`; optional MLflow loading and maintained
strategy mapping are tested by their owning outer packages. Runtime tests live under `tests/trader/runtime/` and
separate order-recovery decisions and shell behavior, broker construction, metrics, broker-portfolio synchronization,
service configuration and scheduling, operator status projections, event-store-backed status, and the long-lived
service shell. Provider and broker interactions use bounded fakes; temporary DuckDB is used only where recovery or
status behavior requires executable event history.

Core architecture contracts follow the same ownership rule. Portfolio export and persistence boundaries live in
`tests/trader/portfolio/test_architecture_boundaries.py`; deterministic/effect separation across the core execution
modules lives in `tests/trader/runtime/test_side_effect_boundaries.py`; and the explicit cycle order-policy contract
lives in `tests/trader/cycle/test_open_order_policy.py`. Only the public `trader`/`trader_standard` extension seam lives
under `tests/cross_package/boundaries/`.

## Python Code Quality

Use [Python Code Quality](../../../docs/python_code_quality.md) for cross-codebase guidance on readable, testable,
observable Python, including comments, docstrings, error handling, typing, and PR review expectations.

## Required Local Checks

Core development baseline:

<!-- verified: integration:repository tests/cross_package/documentation/test_package_documentation.py -->
```bash
uv sync --dev --extra ml --group docs
uv run ruff check src tests examples run_*.py external_strategy_demo.py
uv run mypy
uv run pytest -m 'not postgres'
```

## Postgres Integration Coverage

The active runtime store is Postgres. DuckDB remains test support only.

Start local Postgres with:

<!-- verified: integration:repository tests/cross_package/documentation/test_package_documentation.py -->
```bash
docker compose -f docker-compose.postgres.yml up -d
```

Postgres integration tests require:

- `PG_TEST_HOST`
- `PG_TEST_PORT`
- `PG_TEST_DB` (must end in `_test` or `_testing`)
- `PG_TEST_USER`
- `PG_TEST_PASSWORD`

The configured role must be able to own or alter the runtime tables in its isolated test database because event-store
initialization normalizes existing constraints as well as creating missing objects. Granting only data-manipulation
privileges is insufficient for this adapter contract.

Example local env:

<!-- verified: integration:repository tests/cross_package/documentation/test_package_documentation.py -->
```bash
export PG_TEST_HOST=127.0.0.1
export PG_TEST_PORT=5432
export PG_TEST_DB=trader_orchestration_test
export PG_TEST_USER=trader_verification_runner
export PG_TEST_PASSWORD='<isolated-test-role-password>'
```

Run the Postgres subset with:

<!-- verified: integration:repository tests/cross_package/documentation/test_package_documentation.py -->
```bash
uv run pytest tests/trader tests/trader_standard tests/trader_research tests/trader_mlflow tests/trader_mcp tests/trader_agents tests/cross_package/workflows -m postgres
```

When the Postgres test variables are absent, Postgres-marked tests skip explicitly. The guarded qualification suites
also require their profile, admin, operator, checkpoint, provider, and locale variables; follow
[historical controlled qualification runbook](../../../docs/history/research_agents/research_operations_before_package_ownership.md#isolated-postgres-runtime) rather than
deriving them from the runtime `.env`.

## Coverage Expectations

- Unit tests should cover contracts, deterministic identifiers, risk logic, strategy behavior, and non-network runtime helpers.
- Postgres tests should cover schema bootstrap, lifecycle upserts, event-store idempotency, `session_id` propagation, metrics writes, and notification behavior.
- External broker/network behavior should stay isolated behind fakes or dedicated integration boundaries.

## CI

GitHub Actions runs the repository baseline:

<!-- verified: integration:repository tests/cross_package/documentation/test_package_documentation.py -->
```bash
uv sync --dev --extra ml --group docs
uv run ruff check src tests examples run_*.py external_strategy_demo.py
uv run mypy
uv run pytest -m 'not postgres'
```
