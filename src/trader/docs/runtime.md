# Runtime Orchestration

The runtime orchestration component decides when a trading cycle runs, what state is passed into it, and how the run
is bounded. It is implemented primarily by `BacktestRunner`, `TraderService`, and `run_cycle`.

## Component responsibilities

- Load the typed runtime config supplied by a wrapper.
- Establish a run/session audit boundary.
- Reuse injected strategy and risk objects.
- Select the correct market-data source for the mode.
- Provide broker and portfolio objects to each cycle.
- Record cycle start, finish, status, and errors.
- Keep backtest mode deterministic and live mode fail-closed.

## Backtest operation

Backtest orchestration is handled by `BacktestRunner`.

Primary entrypoints:

<!-- verified: integration:postgres/provider tests/trader/runtime/test_trader_service.py tests/trader/runtime/test_runtime_status.py -->
```bash
uv run python examples/run_injected_backtest.py
uv run python examples/run_library_backtest.py
uv run python examples/run_reproducible_backtest.py
```

Flow:

1. The wrapper loads YAML and builds `Config`.
2. The wrapper constructs strategy and risk objects.
3. `BacktestSpec` defines start, end, timeframe, and optional `max_runs`.
4. `BacktestRunner` loads historical bars into memory.
5. Initial cash and initial positions seed the in-memory portfolio.
6. For each historical timestamp, the runner calls `run_cycle` once per symbol that has a bar.
7. Each cycle uses `decision_ts` from the historical bar and `ingest_market_data=false`.
8. The runner forces a deterministic internal paper broker.
9. Run, cycle, signal, order, fill, and position records are persisted.
10. The runner builds `BacktestResult`.

Canonical research orchestration is exposed through MCP. It validates registered implementation versions and immutable
strategy/risk/backtest specifications before invoking this same runner, then stores complete run evidence in Postgres
research artifacts. See [Research Workflows](../../../docs/workflows/research.md).

Backtest mode does not call Alpaca, does not write market-data bars, and does not depend on wall-clock timing for
decisions. Its main persistence boundary is the run/cycle trail: `runs` records the run, `run_events` records each
cycle, and the shared `run_id`/`cycle_id` values connect those lifecycle records to signals, orders, fills, positions,
and result snapshots.

The mode is deterministic because bar timestamps drive cycle invocation and the broker is forced to the internal paper
path. It is currently a sequential in-process runner, so parallel or distributed backtest execution remains future
orchestration work.

## Live operation

Live orchestration is handled by `TraderService`.

Primary entrypoints:

<!-- verified: integration:postgres/provider tests/trader/runtime/test_trader_service.py tests/trader/runtime/test_runtime_status.py -->
```bash
uv run python examples/run_injected_trader_service.py
uv run python examples/run_library_trader_service.py
```

Startup flow:

1. The wrapper loads YAML and builds `Config`.
2. The wrapper constructs strategy and risk objects.
3. `TraderService` builds the event store and a persistent broker.
4. A trading session is recorded.
5. Startup recovery runs in `resume` or `fail_closed` mode.
6. Alpaca-backed portfolio mode refreshes local position snapshots from broker account state.
7. Broker positions are validated against configured symbols and asset class.
8. Metrics sampling starts if enabled and reads event-store snapshots by default.
9. The service enters `once`, `loop`, or realtime mode.

Live execution modes:

| Mode | Trigger | Typical use |
| --- | --- | --- |
| `once` | One immediate cycle, then finish. | Smoke tests, manual dry runs, one-off decisions. |
| `loop` | Fixed cadence from `trader_service.cadence_seconds`. | Polling-style operation. |
| `real_time`, `realtime`, `real-time` | Postgres `LISTEN/NOTIFY`. | Normal event-driven paper trading. |

Realtime cycle flow:

1. Market-data process writes a bar and emits `NOTIFY`.
2. `TraderService` receives and parses the payload.
3. Duplicate triggers are suppressed.
4. Single-flight execution prevents overlapping cycles.
5. `run_cycle` checks global halt state before strategy execution.
6. `run_cycle` loads market context, applies strategy/risk, submits orders, records results, and finishes the cycle.

Live orchestration records a `trading_sessions` row for the service lifetime and `run_events` rows for each cycle.
Startup recovery, broker portfolio validation, duplicate trigger suppression, and single-flight execution are the
mechanisms that keep live operation conservative. They reduce the chance of trading against ambiguous state, but they
also mean the current service favors safety over throughput.

Operator commands are centralized in `run_operator.py`:

<!-- verified: integration:postgres/provider tests/trader/runtime/test_trader_service.py tests/trader/runtime/test_runtime_status.py -->
```bash
uv run python run_operator.py configs/example.yaml status --json
uv run python run_operator.py configs/example.yaml health --json
uv run python run_operator.py configs/example.yaml positions --json
uv run python run_operator.py configs/example.yaml open-orders --json
uv run python run_operator.py configs/example.yaml halt status --json
uv run python run_operator.py configs/example.yaml halt set --reason "manual safety stop"
uv run python run_operator.py configs/example.yaml halt clear
uv run python run_operator.py configs/example.yaml reconcile --json
```

`status`, `health`, `positions`, `open-orders`, and `halt status` are event-store-first and do not need broker access.
`reconcile` constructs the configured broker and appends local order/fill events when broker state differs from local
history.
Health classification is computed as a typed pure assessment from normalized run, cycle, market-data, halt, and
open-order subsections before it is serialized for CLI/API output.

AI/tool discovery may read JSON emitted by these operator commands as context. Recommendation and promotion readiness
will surface halted, stale, or unhealthy runtime state, but the discovery tools do not clear halt state, reconcile broker
orders, or start `TraderService`.

## Configurability

Runtime orchestration is controlled by:

<!-- verified: config -->
```yaml
runtime:
  mode: once

trader_service:
  mode: real_time
  startup_recovery_mode: resume
  cadence_seconds: 1.0
  min_trigger_interval_ms: 200
  notify_channel: market_data
  max_iterations: null
  portfolio_source: alpaca
  order_reconciliation_interval_seconds: 60
```

`portfolio_source` is a typed runtime setting. Use `alpaca` when the paper broker account is authoritative for cash and
positions; use `db` when local snapshots are the intended runtime state. Periodic reconciliation runs in loop/realtime
modes when `order_reconciliation_interval_seconds` is positive; set it to `0` to disable.

Backtest wrappers also read:

<!-- verified: config -->
```yaml
backtest:
  start: "2026-01-20T12:00:00Z"
  end: "2026-01-20T12:11:00Z"
  timeframe: 1Min
  max_runs: null
  log_cycle_details: false
```

Strategy and risk construction is not configured by the orchestration component. It is owned by user wrapper code.
The research CLI is the narrow exception: it supports config-defined `trader_standard` strategies only, so it can run
repeatable local experiments without a general Python code loader.
The Sprint 5 discovery CLI keeps the same constraint and exposes only `trend_following`, `mean_reversion`, and
`bollinger_band` strategy families.

## Current limits

- No distributed backtest executor.
- No parallel parameter-sweep job queue.
- No multi-service sharding by symbol universe.
- Single-flight live execution prioritizes safety over throughput.
- The component guarantees clear invocation boundaries and lifecycle records, not strategy quality or venue fill
  realism.
