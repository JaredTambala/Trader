# Task 0.8g — Reflex UI Refactor (Two Packages)

## Goal
Split the monorepo into two separately installable packages:
- **trader-core**: core trading engine + API
- **trader-ui**: Reflex UI that talks to the API over HTTP

This allows users to install and run the core system without UI dependencies and to deploy the UI independently.

---

## Phase 1 — Package split scaffolding

1) **Create `trader-core/` package**
- Move core code from `src/trader/` → `trader-core/src/trader/`.
- Create `trader-core/pyproject.toml` with core dependencies only.
- Ensure entrypoints:
  - `python -m trader.api` (FastAPI)
  - `python run_trader_service.py` (runtime)

2) **Create `trader-ui/` package**
- Move UI from `src/ui/` → `trader-ui/src/ui/`.
- Create `trader-ui/pyproject.toml` with Reflex + HTTP client deps only.
- Ensure entrypoint:
  - `reflex run` (or `uv run reflex run`)

3) **Workspace layout**
- Keep a thin root (optional) for docs + docker + shared configs.
- Document how to install core/UI separately (two virtualenvs or uv workspace).

---

## Phase 2 — Dependency + import cleanup

4) **Core exports only**
- Core must not import anything from UI.
- All API endpoints remain in core.

5) **UI uses HTTP only**
- Remove any direct DB/EventStore usage in UI.
- All reads/writes go through API endpoints:
  - `/backtest` (start)
  - `/backtest/progress` (poll)
  - `/backtest/result` (fetch)
  - `/data/query` (if still needed for data viewer)

6) **Config split**
- Core uses YAML config.
- UI uses `UI_API_BASE_URL` (and optional poll intervals) from env.

---

## Phase 3 — Docs & examples

7) **Docs update**
- Root README: two-package install + run flow.
- `trader-core/README.md`: API + runtime usage.
- `trader-ui/README.md`: UI setup + API base URL.

8) **Example config**
- Keep `configs/example.yaml` under `trader-core/`.
- Add `trader-ui/.env.example` with `UI_API_BASE_URL=http://localhost:8100`.

---

## Phase 4 — Validation

9) **Smoke checks**
- Start core API: `uv run python -m trader.api configs/example.yaml`.
- Start UI: `reflex run` in `trader-ui/`.
- Verify UI can submit backtest and render results.

---

## Risks / Decisions
- **Package naming**: `trader-core` vs `trader` (PyPI). Decide naming to avoid collisions.
- **Workspace tooling**: choose uv workspace or separate venvs.
- **Data viewer**: keep or drop (if kept, must call API not DB).

---

## Deliverables
- Two package directories with independent `pyproject.toml`.
- UI uses HTTP API only.
- Updated docs and example configs.
- Verified two-process startup works locally.
