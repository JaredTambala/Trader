# Results And Metrics

The results/metrics component turns runtime history into review artifacts. It covers backtest result objects, JSON/CSV
exports, metrics snapshots, and the API result serializer.

## Component responsibilities

- Build structured `BacktestResult` objects.
- Serialize result payloads consistently for API and exports.
- Export stable JSON, equity-curve CSV, and trade CSV files.
- Export research bundles for experiment runs.
- Compare persisted experiment results from the CLI.
- Generate conservative recommendation artifacts for tool-assisted signal discovery.
- Build dry-run paper-promotion packets linked to recommendation and run IDs.
- Persist metrics snapshots for backtests and live service runs.
- Make run outputs inspectable without reading Python internals.

## Backtest operation

Backtest outputs are centered on `BacktestResult`.

Included result fields:

- assumptions
- warnings
- positions
- strategy performance metrics
- benchmark performance metrics
- relative metrics
- equity curve
- benchmark curve
- trade records
- realized PnL
- total fees
- total slippage

Export helpers:

Call `serialize_backtest_result(result)` for a plain-data payload. Use `export_backtest_result_json`,
`export_backtest_equity_curve_csv`, and `export_backtest_trades_csv` with a result and destination path for reviewable
files.

Canonical research results are stored as Postgres `research_artifacts` with typed backtest, optimization, tracking,
Evaluation, and Adversarial projections. MCP returns `research://postgres/...` refs; a filesystem path is not canonical
research identity or authority.

Reproducible sample output:

<!-- verified: integration:postgres tests/trader/backtest/test_backtest.py tests/trader/runtime/test_runtime_metrics.py -->
```bash
uv run python examples/run_reproducible_backtest.py
```

Exports:

- `artifacts/reproducible_backtest/result.json`
- `artifacts/reproducible_backtest/equity_curve.csv`
- `artifacts/reproducible_backtest/trades.csv`

## Live operation

Live service metrics are optional and controlled by the metrics config. When enabled, the service writes JSON payloads
to `metrics_snapshots`.

Metrics snapshots are review artifacts. They do not replace the durable order/fill/position audit trail.

## Configurability

Metrics config:

<!-- verified: config -->
```yaml
metrics:
  enable_snapshots: true
  interval_seconds: 30
  window_seconds: null
```

Backtest logging/export behavior is wrapper-owned. The reproducible example writes exports under
`artifacts/reproducible_backtest/` by default and accepts `--output-dir`.

The API/UI backtest path uses the shared serializer, but its request shape does not expose the complete backtest
assumptions surface yet. Wrapper-driven backtests remain the primary research path.

Backtest result payloads include enough context to review:

- assumptions used for execution modeling
- run and provenance fields when produced by the research workflow
- warnings from data/execution fallback
- per-trade prices, fees, slippage, and realized PnL
- portfolio state and performance metrics
- benchmark comparison

Persisted metrics snapshots include:

- timestamp
- `run_id`
- optional `session_id`
- optional `cycle_id`
- JSON payload

For legal or operational review, metrics should be used together with raw event tables. The result payload is a
summary; `order_events`, `fill_events`, and `position_snapshots` are the detailed audit trail.

JSON/CSV exports are simple local files. Metrics snapshots are schema-less JSON payloads in Postgres. Serialization is
shared between API and wrapper export paths, which keeps result shape consistent without building a separate warehouse
model yet.

Canonical comparison and optimization result tools resolve immutable Postgres refs and preserve mismatched-scope
warnings, complete trial ledgers, and selected-specification lineage. Evaluation and Adversarial reports remain
independent interpretations rather than recommendation or promotion mutations.

Backtest metrics are computed from the strategy equity curve and the frictionless buy-and-hold benchmark. Realized PnL
and trade stats use adjusted fill prices and fees. Live metrics are operational observations, not independent
reconciliation against a broker statement.

## Current limits

- No warehouse table model for normalized performance metrics.
- No distributed artifact store beyond the configured Postgres authority.
- Benchmark remains costless.
- Metrics are only as accurate as stored market data and modeled execution assumptions.
