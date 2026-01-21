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
- `stock_bar_events` and `crypto_bar_events` enforce uniqueness on `(symbol, ts, source)` via indexes.
- `run_events` is single-row per run; later tasks may expand lifecycle handling if intermediate states are needed.
- Default `DB_PATH` is now `events.duckdb` so `run_cycle` works without `/data`; tests still override it per run.

### Testing
- Tests passed with `UV_CACHE_DIR=.uv-cache uv run pytest`.

### Open Questions
- None.

---

## Task 0.3 — Deterministic Run & Order Identity

### Status
In progress (deterministic IDs and run lifecycle implemented; order idempotency pending order generation).

### What was delivered
- Deterministic `run_id` and `client_order_id` helpers.
- `run_cycle` uses deterministic `run_id` and records started/success/failed lifecycle.
- `DuckDBEventStore` supports run start/finish upserts for idempotent retries.
- Tests for deterministic IDs and run lifecycle behavior.

### Evidence
- Identifier helpers: `src/trader/identifiers.py`.
- Run lifecycle recording: `src/trader/cycle.py`, `src/trader/data.py`.
- Tests: `tests/test_identifiers.py`, `tests/test_data.py`, `tests/test_cycle.py`.
- Documentation: `docs/schema.md`.

### Review Notes
- Run lifecycle uses a single-row update (insert + update) rather than append-only events.
- Deterministic IDs rely on UTC ISO-8601 timestamps and 8-decimal quantity normalization.

### Testing
- Tests passed with `UV_CACHE_DIR=.uv-cache uv run pytest`.

### Open Questions
- Should run lifecycle be modeled as append-only events instead of a single row update?
- Confirm `target_qty` normalization precision (8 decimals) aligns with intended instruments.

---

## Task 0.4 — Market Data Ingestion (Streaming-Lite)

### Status
Complete (pending validation of Alpaca data credentials in the runtime environment).

### What was delivered
- Market data ingestion module with source interface, Alpaca polling source (via `alpaca-py`), and persistence helper.
- Cycle now ingests market data before strategy and skips trading on missing/stale data.
- Stock and crypto bars are stored in separate OHLCV tables with dedicated event types.
- Websocket streaming runner that persists Alpaca bars continuously.
- Historical backfill runner for Alpaca bars using a time-delta window.
- Backfill supports calendar month windows via `--since 6mo`.
- Backfill CLI now uses a single `--since` flag (`m`/`h`/`d`/`mo`).
- Backfill timeframe parsing now matches Alpaca formats (Min/T, Hour/H, Day/D, Week/W, Month/M).
- Stock and crypto bar events now include a `timeframe` column and are indexed by `(symbol, timeframe, ts, source)`.
- Backfill now paginates all available records by default; `--limit` caps totals when needed.
- Backfill uses staging tables and `MERGE` to deduplicate reruns.
- Tests covering ingestion ordering, staleness skip, and persistence to DuckDB.
- Ops doc updated with market data configuration.
- Local `.env` template and README instructions for Alpaca ingestion.

### Evidence
- Market data module: `src/trader/market_data.py`.
- Cycle integration: `src/trader/cycle.py`.
- Config additions: `src/trader/config.py`.
- Alpaca bar parsing: `src/trader/alpaca_market_data.py`.
- Websocket streaming runner: `src/trader/market_data_stream.py`.
- Backfill runner: `src/trader/market_data_backfill.py`.
- Event store schema: `src/trader/data.py`.
- Tests: `tests/test_market_data.py`.
- Streaming tests: `tests/test_market_data_stream.py`.
- Backfill tests: `tests/test_market_data_backfill.py`.
- Schema tests: `tests/test_data.py`.
- Documentation: `docs/ops.md`.
- Local env template: `.env`.
- README updates: `README.md`.

### Review Notes
- Default `MARKET_DATA_SOURCE=noop` skips trading; set `MARKET_DATA_SOURCE=alpaca` and `MARKET_DATA_SYMBOLS` to enable ingestion.
- Staleness check uses the newest event timestamp; all events are still persisted even if stale.
- Alpaca ingestion uses `MARKET_DATA_ASSET_CLASS=stocks|crypto` to select the alpaca-py client.
- Alpaca bar parsing now supports `timestamp/close/volume` attribute names in addition to `t/c/v`.
- Stock data can now set `MARKET_DATA_STOCK_FEED=iex|sip` (Basic plan should use `iex`).
- Alpaca stock and crypto bars now persist to `stock_bar_events` and `crypto_bar_events`; the legacy `market_data_events` table was dropped.

### Testing
- Tests passed with `UV_CACHE_DIR=.uv-cache uv run pytest`.

### Open Questions
- Should unknown `MARKET_DATA_SOURCE` values raise errors instead of skipping ingestion?

---

## Task 0.4b — Minimal Data Viewer (Reflex UI)

### Status
Complete (local UI scaffolded; run with Reflex).

### What was delivered
- Reflex UI in `src/ui` with filters for Type, Ticker, Timeframe, and row limit.
- Table view and time series chart view for selected bars.
- DuckDB-backed queries for both `stock_bar_events` and `crypto_bar_events`.
- Candlestick chart with session axis (no time gaps) and real-time axis toggle.
- Session axis uses timestamp labels (category axis) with 45° ticks and higher-resolution visibility on zoom.
- Docs updated with run instructions.

### Evidence
- UI app: `src/ui/ui/ui.py`, `src/ui/ui/app.py`, `src/ui/ui/pages/index.py`, `src/ui/ui/state.py`.
- UI styles: `src/ui/assets/styles.css`.
- Reflex config: `src/ui/rxconfig.py`.
- README instructions: `README.md`.

---

## Task 0.5 — Postgres Migration (No Data Carry-Over)

### Status
Planned.

### What is planned
- Replace DuckDB with Postgres for concurrent streaming + trading workloads.
- Fresh schema only (no data migration).
- Postgres-backed `EventStore`, updated UI queries, and tests.

### Evidence
- Task definition in `agent_docs/stage_0_task_backlog_remote_paper_trading_system_alpaca.md`.
