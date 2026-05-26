# Testing (Phase 1)

## Standards

- Use `uv` for dependency management and all local quality commands.
- Keep unit tests fast and deterministic.
- Use Postgres-backed integration tests for runtime-store behavior that DuckDB cannot prove.
- Keep deferred UI/interface tests green, but do not let them reshape the core-engine test strategy.

## Required Local Checks

Core development baseline:

```bash
uv sync --dev
uv run ruff check src tests examples run_*.py external_strategy_demo.py
uv run mypy
uv run pytest
```

## Postgres Integration Coverage

The active runtime store is Postgres. DuckDB remains test support only.

Start local Postgres with:

```bash
docker compose -f docker-compose.postgres.yml up -d
```

Postgres integration tests require:

- `PG_HOST`
- `PG_PORT`
- `PG_DB`
- `PG_USER`
- `PG_PASSWORD`

Example local env:

```bash
export PG_HOST=127.0.0.1
export PG_PORT=5432
export PG_DB=trader
export PG_USER=trader
export PG_PASSWORD=traderpass
```

Run the Postgres subset with:

```bash
uv run pytest -m postgres
```

When the Postgres env vars are absent, Postgres-marked tests skip explicitly.

## Coverage Expectations

- Unit tests should cover contracts, deterministic identifiers, risk logic, strategy behavior, and non-network runtime helpers.
- Postgres tests should cover schema bootstrap, lifecycle upserts, event-store idempotency, `session_id` propagation, metrics writes, and notification behavior.
- External broker/network behavior should stay isolated behind fakes or dedicated integration boundaries.

## CI

GitHub Actions runs the Sprint 1 baseline:

```bash
uv sync --dev
uv run ruff check src tests examples run_*.py external_strategy_demo.py
uv run mypy
uv run pytest
```
