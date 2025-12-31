# Stage 0 Task Tracker

## Task 0.1 — Repository Skeleton & Core Interfaces

### Status
Complete (per current implementation).

### What was delivered
- Repo structure with core modules under `src/trader/`.
- Interface definitions for `Strategy`, `Broker`, `RiskManager`, and `EventStore`.
- No-op cycle runnable via `python -m trader.cycle`.
- Initial docs in `docs/schema.md`, `docs/testing.md`, `docs/ops.md`.
- Minimal tests validating the no-op cycle and module entrypoint.
- Packaging via `pyproject.toml`.

### Evidence
- Core modules: `src/trader/broker.py`, `src/trader/strategy.py`, `src/trader/risk.py`, `src/trader/data.py`, `src/trader/cycle.py`, `src/trader/config.py`, `src/trader/web.py`.
- Docs: `docs/schema.md`, `docs/testing.md`, `docs/ops.md`.
- Tests: `tests/test_cycle.py`.
- README: `README.md`.

### Review Notes
- The original warning about `trader.cycle` preloading was addressed by removing re-exports from `src/trader/__init__.py`.
- `pytest` is listed as both a project dependency and a `test` optional dependency; consider keeping it only in dev/test groups.
- `duckdb`, `fastapi`, and `httpx` are listed in `dependencies` even though the skeleton is no-op; confirm whether you want these at Stage 0.1.

### Testing
- Local test run attempted: `python -m pytest` failed due to missing `pytest` in the environment.
- With `uv`, the expected command is: `uv run pytest`.

### Open Questions
- Should `pytest` remain in runtime dependencies, or move solely to `dependency-groups.dev` / `project.optional-dependencies.test`?
- Are `duckdb`, `fastapi`, and `httpx` intended for Stage 0.1 or later tasks?

---

## Task 0.2 — DuckDB Event Store & Schema

### Status
Complete (pending verification in your environment).

### What was delivered
- DuckDB-backed `EventStore` implementation that initializes the Stage 0 schema.
- Transaction helper for atomic cycle execution.
- Updated `run_cycle` to write `run_events` with required fields.
- Default `run_cycle` now instantiates `DuckDBEventStore` from `DB_PATH` and closes the connection.
- Schema documentation expanded with table definitions, constraints, semantics, and query patterns.
- Tests covering schema initialization, uniqueness constraint, and high-frequency inserts.

### Evidence
- Event store implementation: `src/trader/data.py`.
- Updated cycle write: `src/trader/cycle.py`.
- Schema doc: `docs/schema.md`.
- Tests: `tests/test_data.py`.

### Review Notes
- `market_data_events` enforces uniqueness on `(symbol, ts, source)` via an index; confirm if this matches desired ingestion behavior.
- `run_events` is single-row per run; later tasks may expand lifecycle handling if intermediate states are needed.
- Default `DB_PATH` is now `events.duckdb` so `run_cycle` works without `/data`; tests still override it per run.

### Testing
- Tests passed with `UV_CACHE_DIR=.uv-cache uv run pytest`.

### Open Questions
- Should `market_data_events` allow duplicates for the same `(symbol, ts, source)` or keep the unique index?
