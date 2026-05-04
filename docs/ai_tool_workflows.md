# AI-Toolable Research Workflows

Sprint 5 adds a research-only surface for AI systems and scripts. The intended interaction is:

1. Prepare or inspect recent data for a bounded symbol universe.
2. Run a deterministic research suite against stored data.
3. Compare experiment outputs.
4. Recommend candidates with explicit conservative gates.
5. Optionally build a dry-run Alpaca paper-promotion packet for human review.

The workflow is deliberately outside the hot trading path. It can read Sprint 4 operator state, but it does not control
live execution.

For the longer-term division of labor between Data, Math Coder, ML, Quant Research, Hypothesis, Evaluation, and
Adversarial agents, see [agent_operating_model.md](agent_operating_model.md).

## Discovery Workflow

Use discovery when the tool client has a research request such as “pull recent data for these symbols and research
trend-following and mean-reversion strategies.”

```bash
uv run python run_research_discovery.py configs/reproducible_backtest.yaml \
  --symbols DEMO \
  --asset-class stocks \
  --timeframe 1Min \
  --since 1d \
  --strategies trend_following,mean_reversion \
  --data-mode existing \
  --operator-context artifacts/operator_status.json \
  --json
```

Data modes:

- `plan`: returns the data/suite plan only.
- `existing`: uses bars already present in Postgres.
- `sample`: loads the checked-in synthetic sample dataset before research.
- `backfill`: calls the Alpaca backfill path with explicit bounded overrides.

`--dry-run` is equivalent to planning from a side-effect perspective: no bars are written and no backtests run.

Discovery writes:

- `artifacts/discovery/<experiment_slug>/comparison.json`
- `artifacts/discovery/<experiment_slug>/data_quality.json`
- `artifacts/research/<experiment_slug>/<run_id>/...` for research bundles
- `artifacts/recommendations/<experiment_slug>.json`

## Suite Expansion

Discovery exposes only maintained `trader_standard` strategy families:

- `trend_following`
- `mean_reversion`
- `bollinger_band`

The suite expands deterministically. Strategy family order follows the request/config, parameter paths are sorted, and
YAML list order is preserved. Guardrails default to `max_runs=25`, `max_symbols=20`, a conservative cost profile, and
`risk_profile=default`.

Optional `research.suite` config can define parameter lists:

```yaml
research:
  suite:
    strategies:
      - id: trend_following
        parameters:
          strategy.trend_following.ema_fast_period: [2, 3]
          strategy.trend_following.ema_slow_period: [4, 6]
```

Existing `research.sweep` remains supported by `run_research_experiment.py`; Sprint 5 suite expansion is additive.

## Recommendations

Recommendations are conservative by default:

```bash
uv run python run_research_recommendations.py configs/reproducible_backtest.yaml \
  --experiment demo_discovery \
  --json
```

Hard gates reject failed runs, missing result summaries, missing data-quality reports, missing gaps, excessive warnings,
drawdown above 15%, turnover above 10, and too few trades when trade count is present.

The score is deterministic from return, Sharpe, drawdown, turnover, fees/slippage, data quality, warnings, and operator
safety. Missing optional metrics can be neutral for ranking, but required safety context still blocks promotion
readiness.

## Operator Context

AI/tool clients can read Sprint 4 command outputs:

```bash
uv run python run_operator.py configs/example.yaml status --json > artifacts/operator_status.json
uv run python run_operator.py configs/example.yaml open-orders --json > artifacts/open_orders.json
```

These files can be passed into recommendation and promotion commands. A halted runtime, unhealthy status, stale market
data, or stale local open orders blocks promotion readiness. The tool client must not use discovery commands to clear
halt, reconcile broker state, or start trading.

## Promotion Packet

Promotion packet generation is a proposal, not deployment:

```bash
uv run python run_prepare_paper_promotion.py configs/reproducible_backtest.yaml \
  --recommendation-json artifacts/recommendations/demo_discovery.json \
  --recommendation-id rec_... \
  --operator-context artifacts/operator_status.json \
  --output-dir artifacts/promotions \
  --dry-run \
  --json
```

The packet contains:

- proposed paper config YAML
- strategy artifact metadata JSON
- dry-run validation JSON
- promotion packet JSON

Validation checks that the broker config is paper-safe, recommendation context matches, operator blockers are surfaced,
and the command does not start trading.

## Manual Acceptance

```bash
docker compose -f docker-compose.postgres.yml up -d
uv run python examples/load_sample_market_data.py
uv run python run_operator.py configs/example.yaml status --json > artifacts/operator_status.json
uv run python run_research_discovery.py configs/reproducible_backtest.yaml \
  --symbols DEMO \
  --asset-class stocks \
  --timeframe 1Min \
  --since 1d \
  --strategies trend_following,mean_reversion \
  --data-mode existing \
  --operator-context artifacts/operator_status.json \
  --json
uv run python run_research_recommendations.py configs/reproducible_backtest.yaml --experiment demo_discovery --json
```

The final promotion command requires a specific accepted candidate `recommendation_id` from the recommendation JSON.
