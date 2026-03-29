# Task 0.8e — Strategy Externalization (User-Provided Code)

## Goal
Allow users to build strategies and risk managers in **their own codebases** while importing the official interfaces from this repo (`trader`). The system should load these implementations dynamically at runtime and run them without code changes to this repo.

---

## Phase 1 — Interface hardening

1) **Stabilize interfaces**
- Confirm and document required methods for:
  - `Strategy` (signals/orders generation)
  - `RiskManager` (approve/reject orders)
- Add clear docstrings and type hints for inputs/outputs.

2) **Version metadata (optional)**
- Add `StrategyInfo` / `RiskManagerInfo` (name, version, supported features).
- Make version checks explicit in logs.

---

## Phase 2 — Dynamic loader

3) **Add a loader utility**
- `trader/loader.py`:
  - `load_class("module:Class")`
  - Validate interface compliance (method presence / subclass check)
  - Raise helpful errors with import path + missing method detail

4) **Config schema updates**
- Extend YAML:
  ```yaml
  strategy:
    class_path: "my_bot.strategy:MyStrategy"
    params: {...}
  risk_manager:
    class_path: "my_bot.risk:MyRiskManager"
    params: {...}
  ```
- Keep existing `strategy_type` and `risk_manager_type` for internal defaults.
- Implement precedence: `class_path` > built-in type.

---

## Phase 3 — Runtime wiring

5) **Instantiate external classes**
- In `run_cycle`, if `strategy.class_path` exists:
  - Load class
  - Instantiate with `params`
  - Inject context (event_store, timeframe, symbols)
- Same for risk manager (if strategy doesn’t embed its own RM).

6) **Strategy state persistence (optional but recommended)**
- Add `strategy_state` persistence by `session_id`:
  - Store JSON state in `config_kv` or a new `strategy_state` table
  - Provide `get_state()` / `set_state()` helpers
- Enable identical behavior between backtest and realtime.

---

## Phase 4 — Docs & examples

7) **Docs**
- Add “External Strategy” section with example repo layout and config snippet.
- Include instructions for installing user code (editable install).

8) **Example external strategy**
- Add `examples/` folder with a minimal strategy & risk manager.
- Use it in a test config to demonstrate dynamic loading.

---

## Acceptance Criteria
- User can `pip install trader`, subclass `Strategy` in their own repo, and run via `strategy.class_path`.
- Runtime loads external classes without code changes to core.
- Clear errors when class path invalid or methods missing.
- Docs + example demonstrate external usage end-to-end.

---

## Tests
- Loader import success and failure cases.
- External strategy instance executes via `run_cycle`.
- Risk manager override works.

---

## Risks / Decisions
- Whether to require subclassing vs duck-typing.
- Where to persist strategy state (new table vs config_kv).
- How to expose event_store safely to user code.
