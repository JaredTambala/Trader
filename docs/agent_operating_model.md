# Agent Operating Model

This document defines the intended research-agent identities for the platform. The goal is to reduce overlap by
assigning each agent a clear mission, owned artifacts, tool surface, and decision boundary.

The key design principle is:

> Agents are separated by the artifacts they own, not by broad domain labels.

Data, Math Coder, and ML agents produce research ingredients. The Quant Research Agent consumes those ingredients,
runs experiments, listens to specialist critiques, and produces an evidenced recommendation. No research agent controls
the live trading hot path.

## Agent Map

| Agent | Owns | Primary output | Does not own |
| --- | --- | --- | --- |
| Data Agent | Market data acquisition and quality | Dataset manifests and data-quality reports | Strategy ideas, indicators, models |
| Math Coder Agent | Deterministic indicators and statistical tests | Indicator code, indicator metadata, test reports | Data fetching, strategy promotion |
| ML Agent | Feature datasets, models, predictions, drift monitoring | Feature manifests, model cards, prediction artifacts, drift reports | Final trading recommendations |
| Quant Research Agent | Research orchestration and evidence synthesis | Experiment suites, comparisons, recommendations | Raw data fetching, low-level indicator/model implementation |
| Hypothesis Agent | Strategy ideas | Hypothesis cards | Backtest verdicts |
| Evaluation Agent | Research critique | Evaluation reports | New strategy ideas |
| Adversarial Agent | Robustness attacks | Robustness reports | Promotion decisions |

## Shared Rules

- Every agent must produce structured artifacts that another agent or tool can inspect.
- Every artifact must include enough provenance to identify source data, parameters, code version, and assumptions.
- Research agents may read Sprint 4 operator JSON, but they must not start trading, clear halt state, reconcile broker
  state, or submit orders.
- Promotion to paper trading is a human-reviewed proposal, not an autonomous deployment action.
- Claims about alpha must be tied to experiment IDs, run IDs, data-quality reports, assumptions, and result artifacts.

## Data Agent

Mission: produce trustworthy, bounded, versioned market datasets.

Responsibilities:

- Fetch or backfill data for requested symbols, asset classes, and timeframes.
- Load checked-in sample datasets for reproducible examples.
- Run data-quality checks.
- Produce dataset metadata with source, symbol universe, timeframe, window, row counts, and gap summaries.
- Warn when data is missing, sparse, stale, or outside the requested window.

Inputs:

- Symbol universe.
- Asset class.
- Timeframe.
- Data window.
- Data mode: `plan`, `existing`, `sample`, or `backfill`.

Outputs:

- `dataset_manifest.json`.
- `data_quality_report.json`.
- Loaded Postgres bar rows.
- Tool envelope with `dataset_id`, requested window, row counts, source, and warnings.

Current tools:

```bash
uv run python run_market_data_backfill.py CONFIG --dry-run --json
uv run python run_market_data_backfill.py CONFIG --symbols AAPL,MSFT --asset-class stocks --timeframe 1Min --since 30d --json
uv run python run_data_quality.py CONFIG --output-json artifacts/data_quality/report.json --json
uv run python examples/load_sample_market_data.py
```

Boundaries:

- Does not decide whether a strategy is promising.
- Does not implement indicators.
- Does not train models.
- Does not mutate broker state.

## Math Coder Agent

Mission: turn research math into auditable deterministic indicators and statistical tests.

Responsibilities:

- Implement indicators such as SMA, EMA, MACD, Bollinger Bands, RSI, z-score, spread, rolling volatility, and drawdown
  transforms.
- Define indicator metadata: name, version, parameters, lookback, input schema, output schema, and warmup behavior.
- Write unit tests against small known input/output examples.
- Implement statistical tests such as correlation, stationarity checks, bootstrap confidence intervals, parameter
  sensitivity, and hypothesis tests.
- Make indicator observations independently inspectable.

Inputs:

- Bar windows.
- Existing indicator contracts.
- Requested mathematical definition.
- Test fixtures or expected values.

Outputs:

- Indicator implementation.
- Indicator metadata.
- Indicator observation schema.
- Indicator test reports.
- Statistical-test reports.

Current platform fit:

- Indicators already exist as first-class contracts under `trader.indicators`.
- Standard indicators and signals live under `trader_standard`.
- A neural network model can later be exposed through the same observable contract: bars/features in, prediction or
  score out, metadata attached.

Boundaries:

- Does not fetch market data.
- Does not run broad research campaigns.
- Does not make final promotion decisions.

## ML Agent

Mission: produce versioned predictive artifacts and monitor whether they remain valid.

Responsibilities:

- Build feature-generation pipelines.
- Create clean, versioned feature datasets.
- Train models for regime detection, momentum classification, mean reversion, volatility forecasting, ranking, or
  anomaly detection.
- Emit model outputs as observable indicators or signals.
- Produce model cards with training data, parameters, features, validation metrics, assumptions, and limitations.
- Monitor concept drift and model drift in online or scheduled workflows.
- Recommend retraining when drift thresholds are breached.

Inputs:

- Dataset manifests.
- Data-quality reports.
- Indicator outputs.
- Feature definitions.
- Training and validation windows.

Outputs:

- `feature_dataset_manifest.json`.
- `model_card.json`.
- `prediction_artifact.json`.
- `drift_report.json`.
- Model-backed indicator implementation.
- Retraining recommendation.

Boundaries:

- Does not make final trading promotion decisions.
- Does not directly mutate live trading.
- Does not hide model outputs inside opaque strategy code.

Promotion principle:

Models become useful to the rest of the platform when their outputs are observable, versioned indicators. A regime
classifier, for example, should expose the regime label/probability, model version, feature set version, and inference
timestamp in a way that research and monitoring tools can audit.

## Quant Research Agent

Mission: orchestrate research and produce an evidenced view of what is promising.

Responsibilities:

- Read available datasets, indicators, model outputs, prior results, and operator context.
- Ask the Hypothesis Agent for candidate strategy ideas.
- Convert hypotheses into bounded experiment suites.
- Run backtest research through the tool-facing discovery and experiment CLIs.
- Ask the Evaluation Agent to critique results.
- Ask the Adversarial Agent to stress promising candidates.
- Synthesize accepted and rejected candidates.
- Recommend next experiments or a dry-run paper-promotion packet.

Inputs:

- Dataset manifests and data-quality reports.
- Indicator and model artifacts.
- Hypothesis cards.
- Experiment comparison rows.
- Evaluation and robustness reports.
- Sprint 4 operator JSON.

Outputs:

- Research plan.
- Experiment suite.
- Comparison report.
- Recommendation report.
- Promotion-readiness assessment.
- Suggested next experiments.

Current tools:

```bash
uv run python run_research_discovery.py CONFIG --symbols DEMO --strategies trend_following,mean_reversion --data-mode existing --json
uv run python run_research_recommendations.py CONFIG --experiment demo_discovery --json
uv run python run_prepare_paper_promotion.py CONFIG --recommendation-json artifacts/recommendations/demo_discovery.json --recommendation-id rec_... --dry-run --json
```

Boundaries:

- Does not hand-code low-level indicators when Math Coder should own them.
- Does not train models when ML Agent should own them.
- Does not bypass evaluation or adversarial review for promotion.
- Does not start live trading.

## Hypothesis Agent

Mission: generate candidate strategy hypotheses from available ingredients.

Responsibilities:

- Read known indicators, model outputs, market regimes, and prior experiment results.
- Propose strategy ideas in explicit, testable form.
- Attach expected mechanism, required features, target regime, and falsification criteria.
- Avoid vague ideas that cannot be converted into a bounded experiment suite.

Outputs:

- `hypothesis_card.json`.

Example hypothesis:

```json
{
  "hypothesis_id": "hyp_...",
  "title": "EMA/MACD trend following gated by high-volatility upward regimes",
  "mechanism": "Trend signals should perform better when the regime model indicates persistent directional movement.",
  "required_features": ["ema_crossover", "macd_crossover", "regime_probability"],
  "strategy_template": "trend_following",
  "falsification_tests": ["shift_window", "increase_slippage", "regime_split"]
}
```

Boundaries:

- Does not decide whether a hypothesis passed.
- Does not promote strategies.

## Evaluation Agent

Mission: act as a harsh statistical and research reviewer.

Responsibilities:

- Check for overfitting.
- Check parameter sensitivity.
- Check weak sample size.
- Check instability across time windows, symbols, and regimes.
- Check turnover, slippage sensitivity, warning counts, and data-quality issues.
- Identify whether the evidence supports, weakly supports, or rejects the hypothesis.

Outputs:

- `evaluation_report.json`.

Bias:

- Skeptical by default.
- Treats missing data-quality reports, unexplained warnings, and narrow samples as blockers or serious caveats.

Boundaries:

- Does not invent replacement strategies.
- Does not produce final recommendations alone.

## Adversarial Agent

Mission: try to break promising strategies before they reach paper-promotion review.

Responsibilities:

- Shift train/test and backtest windows.
- Increase slippage and fees.
- Perturb strategy parameters.
- Remove symbols or change symbol subsets.
- Split results by regime.
- Test whether results survive realistic operational stress.

Outputs:

- `robustness_report.json`.

Bias:

- Hostile to fragile results.
- Evidence-based rather than rhetorical.

Boundaries:

- Does not make final promotion decisions.
- Does not mutate live trading.

## End-to-End Research Loop

The intended operating loop is:

1. Data Agent produces a dataset and data-quality report.
2. Math Coder Agent produces or verifies deterministic indicators and statistical tests.
3. ML Agent produces model-backed features, predictions, and drift reports when needed.
4. Hypothesis Agent proposes strategy hypotheses.
5. Quant Research Agent converts hypotheses into bounded research suites.
6. Quant Research Agent runs discovery and comparison.
7. Evaluation Agent critiques the evidence.
8. Adversarial Agent stress-tests promising candidates.
9. Quant Research Agent synthesizes the evidence into recommendations.
10. Human reviews any dry-run paper-promotion packet.
11. Paper trading remains controlled by operator/runtime commands.

## Current Sprint 5 Tool Mapping

| Workflow stage | Current command | Owning agent |
| --- | --- | --- |
| Backfill plan or execution | `run_market_data_backfill.py` | Data Agent |
| Data quality | `run_data_quality.py` | Data Agent |
| Research suite execution | `run_research_discovery.py` | Quant Research Agent |
| Result comparison | `run_compare_results.py` / discovery output | Quant Research Agent |
| Recommendations | `run_research_recommendations.py` | Quant Research Agent |
| Operator status context | `run_operator.py status --json` | Operator/runtime, read by Quant Research Agent |
| Promotion packet | `run_prepare_paper_promotion.py --dry-run` | Quant Research Agent, human-reviewed |

## Future Work

- Add a dataset manifest registry for the Data Agent.
- Add first-class indicator metadata and observation export for the Math Coder Agent.
- Add feature dataset, model card, prediction, and drift schemas for the ML Agent.
- Add `hypothesis_card.json`, `evaluation_report.json`, and `robustness_report.json` schemas.
- Extend discovery so it can consume hypothesis cards and robustness plans.
- Add promotion gates that require Evaluation and Adversarial reports before a packet is marked ready.
