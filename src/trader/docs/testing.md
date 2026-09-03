# Testing

## Standards

- Use `uv` for dependency management and all local quality commands.
- Keep unit tests fast and deterministic.
- Use Postgres-backed integration tests for runtime-store behavior that DuckDB cannot prove.
- Keep deferred UI/interface tests green, but do not let them reshape the core-engine test strategy.

## Python Code Quality

Use [Python Code Quality](../../../docs/python_code_quality.md) for cross-codebase guidance on readable, testable,
observable Python, including comments, docstrings, error handling, typing, and PR review expectations.

## Required Local Checks

Core development baseline:

<!-- verified: integration:repository tests/test_package_documentation.py -->
```bash
uv sync --dev --extra ml --group docs
uv run ruff check src tests examples run_*.py external_strategy_demo.py
uv run mypy
uv run pytest
```

## Postgres Integration Coverage

The active runtime store is Postgres. DuckDB remains test support only.

Start local Postgres with:

<!-- verified: integration:repository tests/test_package_documentation.py -->
```bash
docker compose -f docker-compose.postgres.yml up -d
```

Postgres integration tests require:

- `PG_TEST_HOST`
- `PG_TEST_PORT`
- `PG_TEST_DB` (must end in `_test` or `_testing`)
- `PG_TEST_USER`
- `PG_TEST_PASSWORD`

Example local env:

<!-- verified: integration:repository tests/test_package_documentation.py -->
```bash
export PG_TEST_HOST=127.0.0.1
export PG_TEST_PORT=5432
export PG_TEST_DB=trader_orchestration_test
export PG_TEST_USER=trader_verification_runner
export PG_TEST_PASSWORD='<isolated-test-role-password>'
```

Run the Postgres subset with:

<!-- verified: integration:repository tests/test_package_documentation.py -->
```bash
uv run pytest -m postgres
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

<!-- verified: integration:repository tests/test_package_documentation.py -->
```bash
uv sync --dev --extra ml --group docs
uv run ruff check src tests examples run_*.py external_strategy_demo.py
uv run mypy
uv run pytest
```
