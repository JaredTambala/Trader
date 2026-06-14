# Agent Operating Model

This document defines the intended research-agent identities for the platform. The goal is to reduce overlap by
assigning each agent a clear mission, owned artifacts, tool surface, and decision boundary.

The key design principle is:

> Agents are separated by the artifacts they own, not by broad domain labels.

MCP tools provide deterministic capabilities. LangGraph provides agent identity, state, tool allowlists, and
supervision. The Quant Research Supervisor Agent is the overarching supervisor graph for research workflows, but it
does not own the specialist artifacts produced by Data, Quantitative Methods, ML, Hypothesis, Evaluation, or
Adversarial agents.

No research agent controls the live trading hot path.

## Supervisor Hierarchy

The research system is a supervised hierarchy:

```text
Quant Research Supervisor Agent
  -> Data Agent
  -> Quantitative Methods Agent
  -> ML Agent
  -> Hypothesis Agent
  -> Evaluation Agent
  -> Adversarial Agent
```

The Quantitative Methods Agent replaces the earlier "Math Coder Agent" role. Existing implementation plans, file names,
or compatibility aliases may still use the `math_*` namespace during migration, but the agent identity and artifact
boundary should be understood as deterministic quantitative methods rather than narrow indicator coding.

The Quant Research Supervisor coordinates the loop, requests specialist work, consumes specialist artifacts, and
produces final research synthesis. It must not forge or bypass specialist outputs. If a workflow needs data evidence,
deterministic method evidence, model evidence, hypothesis cards, critique, or robustness reports, the supervisor routes
to the agent that owns that artifact.

## Agent Map

| Agent | Owns | Primary output | Does not own |
| --- | --- | --- | --- |
| Quant Research Supervisor Agent | Research orchestration, experiment planning, synthesis, recommendation state | Experiment plans, research suites, comparison reports, recommendation reports | Raw data fetching, low-level indicator/model implementation, critique artifacts, robustness reports |
| Data Agent | Market data acquisition and quality | Dataset manifests and data-quality reports | Strategy ideas, indicators, models, verdicts |
| Quantitative Methods Agent | Source-backed deterministic quantitative methods: indicators, transforms, statistical tests, signal diagnostics, multiple-testing controls, method cards, citation validation, and optional compiled kernels | Knowledge manifests, method cards, method contracts, validation reports, signal diagnostic reports, multiple-testing reports, kernel manifests, parity reports | Data fetching, strategy ideas, model training, broad research orchestration, promotion decisions |
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
- Request deterministic method, diagnostic, and statistical-inference artifacts from the Quantitative Methods Agent when
  research logic is missing or needs verification.
- Request feature, model, prediction, or drift artifacts from the ML Agent when a hypothesis depends on model output.
- Request hypothesis cards from the Hypothesis Agent.
- Convert accepted hypotheses into bounded experiment plans and research suites.
- Run strategy validation, baseline backtests, result lookup, attribution, and comparison through Quant Research MCP
  tools.
- Request Evaluation Agent critique and Adversarial Agent robustness reports before final recommendation.
- Produce recommendation reports and paper-promotion readiness assessments.

Inputs:

- Dataset manifests and data-quality reports.
- Method contracts, method cards, retrieval/citation evidence, indicator observations, signal diagnostics,
  multiple-testing reports, and statistical-test reports.
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
- Does not hand-code low-level indicators or deterministic method logic when the Quantitative Methods Agent should own
  them.
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

## Quantitative Methods Agent

Mission: turn research math into source-backed, auditable deterministic methods, statistical inference procedures, and
operational numerical kernels.

Legacy name: Math Coder Agent. The legacy name may remain in historical plans, compatibility aliases, or transitional
file names, but new agent-facing documentation should use Quantitative Methods Agent.

Responsibilities:

- Define deterministic method contracts for indicators, transforms, statistical tests, signal diagnostics,
  multiple-testing controls, and numerical kernels.
- Maintain and query a curated Quant Methods Knowledge Base for approved sources, source manifests, locator-preserving
  chunks, method cards, evidence retrieval reports, and citation-validation reports.
- Treat the vector store as retrieval infrastructure, not as authority. The authority is the approved source registry
  plus approved method cards.
- Implement and validate maintained indicators such as SMA, EMA, MACD, Bollinger Bands, RSI, z-score, spread, rolling
  volatility, drawdown, cross-sectional ranks, and regime/session-aware transforms.
- Define method metadata: name, version, family, parameters, lookback, warmup behavior, input schema, output schema,
  NaN/inf policy, dtype policy, alignment, and no-lookahead guarantee.
- Write deterministic fixture tests against small known input/output examples and seeded generated cases.
- Implement statistical methods such as correlation and rank IC, stationarity checks, dependence-aware bootstrap
  confidence intervals, HAC-style standard errors, parameter sensitivity, and hypothesis tests.
- Produce signal diagnostics such as IC, rank IC, hit rate, quantile monotonicity, forward-return decay, horizon
  sensitivity, turnover proxy, and symbol/session/regime breakdowns.
- Produce multiple-testing and data-snooping controls that record candidate families, parameter grids, raw p-values,
  adjusted p-values, selection rules, accepted/rejected candidates, warnings, and blockers.
- Require approved method-card references and passing citation validation for sophisticated statistical-test and
  multiple-testing contracts. Simple maintained arithmetic transforms may be allowed from the maintained registry
  without external retrieval.
- Own optional template-restricted C++ kernel artifacts and Python/C++ parity reports for deterministic methods.
- Make method outputs independently inspectable and reproducible.

Inputs:

- Dataset manifests and data-quality report references.
- Approved method cards, retrieved evidence reports, and citation-validation reports.
- Existing method contracts.
- Indicator observations or deterministic method output references.
- Forward-return label references when running signal diagnostics.
- Declared candidate-family manifests when running multiple-testing controls.
- Requested mathematical definition.
- Test fixtures or expected values.
- Optional approved C++ template references.

Outputs:

- `indicator_contract.json`.
- `statistical_test_contract.json`.
- `indicator_validation_report.json`.
- `signal_diagnostic_report.json`.
- `multiple_testing_report.json`.
- `cxx_kernel_manifest.json`.
- `python_cpp_parity_report.json`.
- `method_package_manifest.json`.
- `knowledge_source_manifest.json`.
- `knowledge_ingestion_report.json`.
- `knowledge_chunk_manifest.json`.
- `knowledge_embedding_manifest.json`.
- `method_card_draft.json`.
- `method_card.json`.
- `evidence_retrieval_report.json`.
- `citation_validation_report.json`.

Boundaries:

- Does not fetch market data.
- Does not generate strategy hypotheses.
- Does not train fitted ML models or own prediction artifacts.
- Does not run broad research campaigns.
- Does not make final promotion decisions.
- Does not emit arbitrary runtime code or compiled kernels outside approved templates and parity checks.
- Does not use unresolved data-quality warnings, undeclared candidate families, or unadjusted search results as proof of
  alpha.
- Does not create production method contracts from unapproved method cards, uncited retrieved chunks, or invalid
  locators.
- Does not expose arbitrary filesystem access, execute code from documents, or reproduce large source passages in
  artifacts.

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
- Deterministic method outputs and indicator observations.
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

- Read known deterministic method outputs, model outputs, market regimes, and prior experiment results.
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
3. Quantitative Methods Agent produces or verifies deterministic methods, diagnostics, and statistical tests.
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
| Knowledge-backed method contracts, diagnostics, and multiple-testing verification | planned `knowledge_*` and `math_*` tools | Quantitative Methods Agent |
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
- Add first-class knowledge source manifests, approved method cards, citation-validation reports, method contracts,
  signal diagnostics, multiple-testing reports, and optional parity-checked numerical kernels for the Quantitative
  Methods Agent.
- Add feature dataset, model card, prediction, and drift schemas for the ML Agent.
- Add `hypothesis_card.json`, `evaluation_report.json`, and `robustness_report.json` schemas.
- Extend research suite generation so it consumes hypothesis cards and robustness plans.
- Add promotion gates that require Evaluation and Adversarial reports before a packet is marked ready.
