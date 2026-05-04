# Results and Metrics Component

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

```python
serialize_backtest_result(result)
export_backtest_result_json(result, path)
export_backtest_equity_curve_csv(result, path)
export_backtest_trades_csv(result, path)
```

Research result workflow:

```bash
uv run python run_research_experiment.py configs/reproducible_backtest.yaml --experiment demo_research --run-data-quality
uv run python run_compare_results.py configs/reproducible_backtest.yaml --experiment demo_research --format table
uv run python run_compare_results.py configs/reproducible_backtest.yaml --experiment demo_research --format json
```

Research artifacts are written under `artifacts/research/<experiment_slug>/<run_id>/` by default:

- `result.json`
- `provenance.json`
- `metrics.json`
- `equity_curve.csv`
- `benchmark_curve.csv`
- `positions.csv`
- `trades.csv` when trades exist

Reproducible sample output:

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

```yaml
metrics:
  enable_snapshots: true
  interval_seconds: 30
  window_seconds: null
```

Backtest logging/export behavior is wrapper-owned. The reproducible example writes exports under
`artifacts/reproducible_backtest/` by default and accepts `--output-dir`.

The research CLI reads optional `research.experiment` and `research.sweep` config. Without a sweep it records one
backtest run. With `research.sweep.parameters`, it expands parameter paths deterministically and records every member
under one experiment.

The API/UI backtest path uses the shared serializer, but its request shape does not expose the complete backtest
assumptions surface yet. Wrapper-driven backtests remain the primary research path.

Backtest result payloads include enough context to review:

- assumptions used for execution modeling
- run, experiment, and provenance fields when produced by the research workflow
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

Experiment comparison reads `experiment_runs.result_summary` and warns when compared members have different
assumptions, symbols, timeframe, asset class, or data window. The JSON format is stable so a future tool-agent can use
it without scraping table output.

Sprint 5 recommendations read comparison JSON or persisted experiment rows and write local recommendation artifacts.
They rank candidates with conservative gates for status, data quality, warnings, drawdown, turnover, trade count, and
operator context. A recommendation can be converted into a dry-run promotion packet, but the packet is only a proposal:
it writes YAML/JSON under `artifacts/promotions/<recommendation_id>/` and never starts paper trading.

Tool-facing result commands:

```bash
uv run python run_research_discovery.py configs/reproducible_backtest.yaml --symbols DEMO --strategies trend_following --json
uv run python run_research_recommendations.py configs/reproducible_backtest.yaml --experiment demo_discovery --json
uv run python run_prepare_paper_promotion.py configs/reproducible_backtest.yaml --recommendation-json artifacts/recommendations/demo_discovery.json --recommendation-id rec_... --dry-run --json
```

Backtest metrics are computed from the strategy equity curve and the frictionless buy-and-hold benchmark. Realized PnL
and trade stats use adjusted fill prices and fees. Live metrics are operational observations, not independent
reconciliation against a broker statement.

## Current limits

- No warehouse table model for normalized performance metrics.
- No distributed artifact store.
- Recommendation and promotion artifacts are local files rather than database tables.
- Benchmark remains costless.
- Metrics are only as accurate as stored market data and modeled execution assumptions.
