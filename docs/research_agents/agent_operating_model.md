# Agent Operating Model

This document defines the intended research-agent identities for the platform. The goal is to reduce overlap by
assigning each agent a clear mission, owned artifacts, tool surface, and decision boundary.

The key design principle is:

> Agents are separated by the artifacts they own, not by broad domain labels.

MCP tools provide deterministic capabilities. LangGraph provides agent identity, state, tool allowlists, and
supervision. The Quant Research Supervisor Agent is the overarching supervisor graph for research workflows, but it
does not own the specialist artifacts produced by Data, Math Coder, ML, Hypothesis, Evaluation, or Adversarial agents.

No research agent controls the live trading hot path.

## Supervisor Hierarchy

The research system is a supervised hierarchy:

```text
Quant Research Supervisor Agent
  -> Data Agent
  -> Math Coder Agent
  -> ML Agent
  -> Hypothesis Agent
  -> Evaluation Agent
  -> Adversarial Agent
```

The Quant Research Supervisor coordinates the loop, requests specialist work, consumes specialist artifacts, and
produces final research synthesis. It must not forge or bypass specialist outputs. If a workflow needs data evidence,
indicator evidence, model evidence, hypothesis cards, critique, or robustness reports, the supervisor routes to the
agent that owns that artifact.

## Agent Map

| Agent | Owns | Primary output | Does not own |
| --- | --- | --- | --- |
| Quant Research Supervisor Agent | Research orchestration, experiment planning, synthesis, recommendation state | Experiment plans, research suites, comparison reports, recommendation reports | Raw data fetching, low-level indicator/model implementation, critique artifacts, robustness reports |
| Data Agent | Market data acquisition and quality | Dataset manifests and data-quality reports | Strategy ideas, indicators, models, verdicts |
| Math Coder Agent | Deterministic indicators and statistical tests | Indicator code, indicator metadata, statistical-test reports | Data fetching, broad research orchestration, promotion decisions |
| ML Agent | Feature datasets, models, predictions, drift monitoring | Feature manifests, model cards, prediction artifacts, drift reports | Final trading recommendations |
| Hypothesis Agent | Strategy ideas | Hypothesis cards | Backtest verdicts, promotion decisions |
| Evaluation Agent | Research critique | Evaluation reports | New strategy ideas, final recommendations |
| Adversarial Agent | Robustness attacks | Robustness reports | Promotion decisions |

## Shared Rules

- Every agent must produce structured artifacts that another agent or tool can inspect.
- Every artifact must include enough provenance to identify source data, parameters, code version, and assumptions.
- The Quant Research Supervisor may request specialist work, but it must preserve the owning agent on each artifact.
- Supervisor state stores artifact references, decisions, public status, and tool evidence, not hidden reasoning.
- Research agents may read operator/runtime context, but they must not start trading, clear halt state, reconcile broker
  state, submit orders, or run raw SQL.
- Promotion to paper trading is a human-reviewed proposal, not an autonomous deployment action.
- Claims about alpha must be tied to experiment IDs, run IDs, data-quality reports, assumptions, and result artifacts.

## LangGraph Responsibility Split

Each agent has its own LangGraph identity:

- identity and role policy
- state schema
- MCP tool allowlist
- required output artifact contract
- handoff contract to the Quant Research Supervisor

The same MCP server can expose all tools, but each graph decides which tools are callable. A graph must not call core
platform internals directly when an MCP tool exists for that operation.

## Quant Research Supervisor Agent

Mission: coordinate research and produce an evidenced view of what is promising.

Responsibilities:

- Accept a research request and decompose it into specialist work.
- Request dataset manifests and quality reports from the Data Agent.
- Request indicator/statistical-test artifacts from the Math Coder Agent when deterministic research logic is missing
  or needs verification.
- Request feature, model, prediction, or drift artifacts from the ML Agent when a hypothesis depends on model output.
- Request hypothesis cards from the Hypothesis Agent.
- Convert accepted hypotheses into bounded experiment plans and research suites.
- Run strategy validation, baseline backtests, result lookup, attribution, and comparison through Quant Research MCP
  tools.
- Request Evaluation Agent critique and Adversarial Agent robustness reports before final recommendation.
- Produce recommendation reports and paper-promotion readiness assessments.

Inputs:

- Dataset manifests and data-quality reports.
- Indicator metadata, indicator observations, and statistical-test reports.
- Feature manifests, model cards, prediction artifacts, and drift reports.
- Hypothesis cards.
- Experiment plans, backtest results, attribution summaries, evaluation reports, and robustness reports.
- Operator/runtime context as read-only evidence.

Outputs:

- `experiment_plan.json`.
- Research suite artifact.
- Comparison report.
- Recommendation report.
- Promotion-readiness assessment.
- Suggested next experiments.

Boundaries:

- Does not fetch raw data directly when Data Agent tools can produce the required artifacts.
- Does not hand-code low-level indicators when Math Coder Agent should own them.
- Does not train models when ML Agent should own them.
- Does not invent critique or robustness artifacts.
- Does not bypass Evaluation or Adversarial review for promotion readiness.
- Does not start live trading.

## Data Agent

Mission: produce trustworthy, bounded, versioned market datasets.

Responsibilities:

- Fetch or backfill data for requested symbols, asset classes, and timeframes when policy permits.
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
- Loaded local bar rows when explicitly permitted.
- Tool envelope with `dataset_id`, requested window, row counts, source, and warnings.

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

- Bar windows or dataset references.
- Existing indicator contracts.
- Requested mathematical definition.
- Test fixtures or expected values.

Outputs:

- Indicator implementation.
- Indicator metadata.
- Indicator observation schema.
- Indicator test reports.
- Statistical-test reports.

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

## Hypothesis Agent

Mission: generate candidate strategy hypotheses from available ingredients.

Responsibilities:

- Read known indicators, model outputs, market regimes, and prior experiment results.
- Propose strategy ideas in explicit, testable form.
- Attach expected mechanism, required features, target regime, data requirements, and falsification criteria.
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
- Does not run backtests.
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

## Handoff Contracts

Every specialist handoff to the Quant Research Supervisor should include:

- `agent_owner`
- artifact type and artifact path or structured payload
- source inputs and parameters
- warnings and blockers
- side-effect class
- provenance references

The supervisor can reject an artifact as insufficient, request more work, or mark a research path blocked. It should not
rewrite specialist outputs to make a strategy look better.

## End-to-End Research Loop

The intended operating loop is:

1. Quant Research Supervisor accepts a bounded research request.
2. Data Agent produces a dataset manifest and data-quality report.
3. Math Coder Agent produces or verifies deterministic indicators and statistical tests.
4. ML Agent produces model-backed features, predictions, and drift reports when needed.
5. Hypothesis Agent proposes strategy hypotheses.
6. Quant Research Supervisor converts accepted hypotheses into bounded research suites.
7. Quant Research tools validate candidates, run baselines, look up results, and produce attribution/comparison evidence.
8. Evaluation Agent critiques the evidence.
9. Adversarial Agent stress-tests promising candidates.
10. Quant Research Supervisor synthesizes the evidence into recommendations.
11. Human reviews any dry-run paper-promotion packet.
12. Paper trading remains controlled by operator/runtime commands.

## Planned MCP and LangGraph Mapping

| Workflow stage | MCP/tool surface | LangGraph owner |
| --- | --- | --- |
| Research request decomposition | Supervisor graph state and handoffs | Quant Research Supervisor Agent |
| Data inventory and quality | `data_get_inventory`, `data_summarize_quality`, `data_ensure_loaded` | Data Agent |
| Indicator/stat-test verification | planned Math Coder tools | Math Coder Agent |
| Feature/model/drift artifacts | planned ML tools | ML Agent |
| Hypothesis card creation | `hypothesis_create_card` | Hypothesis Agent |
| Strategy catalog and validation | `research_list_strategy_templates`, `research_validate_strategy_candidate` | Quant Research Supervisor Agent |
| Baseline backtests and result lookup | `research_run_backtest`, `research_get_backtest_results` | Quant Research Supervisor Agent |
| Attribution and comparison | `research_analyze_return_attribution` | Quant Research Supervisor Agent |
| Evidence critique | `evaluation_generate_report` | Evaluation Agent |
| Robustness testing | `adversarial_run_robustness` | Adversarial Agent |
| Recommendation synthesis | `research_generate_recommendation`, later `research_run_experiment` | Quant Research Supervisor Agent |

## Future Work

- Add a dataset manifest registry for the Data Agent.
- Add first-class indicator metadata and observation export for the Math Coder Agent.
- Add feature dataset, model card, prediction, and drift schemas for the ML Agent.
- Add `hypothesis_card.json`, `evaluation_report.json`, and `robustness_report.json` schemas.
- Extend research suite generation so it consumes hypothesis cards and robustness plans.
- Add promotion gates that require Evaluation and Adversarial reports before a packet is marked ready.
