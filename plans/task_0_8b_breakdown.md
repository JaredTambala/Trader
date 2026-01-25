# Incremental Delivery Breakdown for Task 0.8b – UI Backtest Runner

The **UI Backtest Runner** (Task 0.8b) adds the ability to launch, monitor, and view back‑test results from the Reflex UI.  The work is split into small, testable increments that can be built and merged independently.

## Chunk List

| # | Chunk | Description | Files | Acceptance Criteria |
|---|-------|-------------|-------|----------------------|
| 0️⃣ | **Prep** | Catalog the current backtest/trader endpoints and UI flow, and attach inline comments summarizing the data path (config → run_id → progress → result). | `src/trader/backtest.py`, `src/trader/trader_service.py`, `src/ui/ui/pages/backtest.py` | Comments or short docstrings added; no behavior change. |
| 1️⃣ | **Reflex Configuration Form** | Build the Reflex backtest form (`backtest.py`) with inputs for symbols, timeframe, start/end datetimes, initial cash, and strategy JSON, along with a submit button wired to `DataViewerState.start_backtest`. | `src/ui/ui/pages/backtest.py`, `src/ui/ui/state.py` | Form renders. Submit button triggers API call and updates `status_message`. |
| 2️⃣ | **POST /backtest API** | Implement `POST /backtest` handler that validates the payload, persists the submitted config snapshot, generates a deterministic `run_id`, enqueues `_run_backtest_async`, and immediately returns `{run_id}`. | `src/trader/trader_service.py` | Handler returns 200 + run_id; `_run_backtest_async` runs in background. |
| 3️⃣ | **Progress Tracking & Endpoint** | During `_run_backtest_async`, write progress checkpoints to `config_kv` (or lightweight table). Expose `GET /backtest/progress?run_id=` returning JSON (status, bars processed, percent, elapsed, last_ts). | `src/trader/trader_service.py`, `src/trader/data.py` | Endpoint gives streaming progress until status is `completed`/`failed`. |
| 4️⃣ | **Result Persistence** | On completion (success/failure), write a `metrics_snapshots` payload containing strategy + benchmark metrics, equity curves, exposure, and final positions. Mark run status accordingly. | `src/trader/backtest.py`, `src/trader/data.py` | Querying `metrics_snapshots` for the run yields the latest payload. |
| 5️⃣ | **Result Endpoint** | Implement `GET /backtest/result?run_id=` returning the JSON payload (or error if missing). Ensure 404/error statuses propagate. | `src/trader/trader_service.py` | UI can fetch results; API returns 200 with JSON on success, 4xx on failures. |
| 6️⃣ | **UI Result Page** | Create/refine `backtest_result_page` displaying summary metrics, equity vs benchmark chart, and final positions from `DataViewerState.backtest_result`. Include status banners and links back to the form. | `src/ui/ui/pages/backtest_result.py`, `src/ui/ui/state.py` | Page renders for populated result; charts/tables show real numbers. |
| 7️⃣ | **Polling & Navigation** | After receiving `run_id`, poll `/backtest/progress` via `DataViewerState.poll_backtest_progress` every 5–10s, update `backtest_progress`, and, on completion, auto-fetch results and enable a “View Results” link. | `src/ui/ui/state.py`, `src/ui/ui/pages/backtest.py` | Status updates show progress; completion reveals navigation to `/backtest/result`. |
| 8️⃣ | **Error & Retry Handling** | On failures from start/progress/result endpoints, record errors in `status_message`/`error` and surface banners; backend records failed run status + error message in `runs`. | `src/trader/backtest.py`, `src/trader/trader_service.py`, `src/ui/ui/state.py`, `src/ui/ui/pages/backtest_result.py` | Failures set `runs.status=failed`, UI displays descriptive error with retry guidance. |
| 9️⃣ | **API Integration Tests** | Add `tests/test_backtest_api.py` covering each endpoint: start returns run_id, progress evolves, result returns metrics, failure path returns error. | `tests/test_backtest_api.py` | Tests pass under `uv run pytest`. |
| 🔟 | **UI Flow Tests (optional)** | Add a UI smoke test (Reflex or Playwright) that fills the form, triggers the run, polls progress, and verifies the results page displays metrics. | `tests/ui/test_backtest_flow.py` | Test scripts run end-to-end (can be skipped if tooling absent). |
| 1️⃣1️⃣ | **Docs & Ops** | Document the UI backtest workflow, API contract, env vars, and how to interpret results in `docs/ops.md`/`README.md`. | `docs/ops.md`, `README.md` | Documentation builds without errors and includes a new section. |

## Suggested Timeline
1. **Prep → UI Form** (Day 1) 
2. **Backend Start Endpoint** (Day 2) 
3. **Progress & Result Endpoints** (Day 3) 
4. **Result Persistence** (Day 4) 
5. **UI Result View** (Day 5) 
6. **Error Handling** (Day 6) 
7. **Tests** (Days 7‑8) 
8. **Docs & Full Suite** (Day 9)

Each chunk can be developed on its own feature branch, reviewed, and merged, ensuring a continuously releasable code base while progressing toward the complete UI Backtest Runner.
