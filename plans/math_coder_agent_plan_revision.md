# Quantitative Methods Agent Revision: Deterministic Quant Methods Agent

## Purpose

This document proposes a revision to the former Math Coder Agent plan. The existing plan correctly separates agents by
owned artifacts, but the planned scope is too narrow if it is limited to indicator listing and validation. The canonical
identity should become Quantitative Methods Agent: owner of deterministic quantitative methods, mathematical transforms,
statistical tests, signal diagnostics, multiple-testing controls, and optional compiled C++ kernels that can be called
from Python.

The revised agent remains meaningfully distinct from the ML Agent and Hypothesis Agent. Its boundary is not “all quantitative thinking.” Its boundary is deterministic, auditable mathematical machinery and inference artifacts.

Recommended identity:

```text
Quantitative Methods Agent
  legacy source name: Math Coder Agent
  conceptual role: deterministic quant methods owner
  tool namespace: math_*
```

## Design Principle

The agent boundary should remain artifact-based:

```text
If the output is a formula, transform, statistical test, method contract,
or compiled deterministic kernel -> Quantitative Methods Agent.

If the output is a fitted model, prediction series, feature dataset,
model card, or drift report -> ML Agent.

If the output is a falsifiable market claim using available ingredients
-> Hypothesis Agent.

If the output is a critique/verdict on research quality -> Evaluation Agent.

If the output is a final research plan, comparison, or recommendation
-> Quant Research Supervisor Agent.
```

This preserves the existing architecture: MCP tools provide deterministic capabilities, LangGraph provides identity and orchestration, and the Quant Research Supervisor consumes specialist artifacts without forging or rewriting them.

## Revised Mission

Current mission:

> Turn research math into auditable deterministic indicators and statistical tests.

Recommended expanded mission:

> Turn research math into auditable deterministic methods, statistical inference procedures, and operational numerical kernels. The Quantitative Methods Agent owns indicator contracts, transform contracts, statistical-test contracts, signal diagnostics, multiple-testing reports, and Python/C++ parity reports. It does not fetch data, generate strategy hypotheses, train ML models, run broad research campaigns, or make promotion decisions.

## Why Expand the Definition

Indicator implementation is the easiest part. The harder and more valuable responsibility is preventing the research system from mistaking noise, leakage, parameter mining, and data snooping for alpha.

A large indicator universe creates hidden statistical risk:

```text
symbols x timeframes x indicators x parameter grids x horizons x regimes x cost assumptions
```

If the system only reports the winning configuration, it will produce false confidence. The Quantitative Methods Agent should therefore record the full candidate family and produce inference artifacts that downstream agents can inspect.

The agent should never return only:

```text
best_indicator = "ema_cross_12_48"
```

It should return:

```text
candidate_family_id
candidate_count
full_parameter_grid
selection_rule
all tested metrics
raw p_values
adjusted_p_values
data_quality_references
cost_or_label_assumptions
warnings
accepted_candidates
rejected_candidates
```

## Agent Distinction

| Agent | Core question | Owns | Must not own |
| --- | --- | --- | --- |
| Quantitative Methods Agent | Is this deterministic mathematical object correctly defined, implemented, and statistically testable? | Indicators, transforms, statistical tests, multiple-testing methods, signal diagnostics, Python/C++ parity reports | Strategy ideas, model training, broad research campaigns, final verdicts |
| ML Agent | Can a learned model produce a versioned predictive artifact? | Feature manifests, model cards, fitted models, prediction artifacts, drift reports | Hand-coded deterministic method ownership, hypothesis generation, final recommendations |
| Hypothesis Agent | What is the tradable claim or mechanism worth testing? | Hypothesis cards with mechanism, required features, target regime, falsification criteria | Implementation, statistical-test ownership, model training, backtests, verdicts |
| Evaluation Agent | Does the evidence survive skeptical review? | Evaluation reports, blockers, caveats, weak-sample findings, overfit warnings | New methods, new strategy ideas, final recommendations |
| Quant Research Supervisor Agent | What should run next, and what does the evidence collectively imply? | Experiment plans, research suites, comparisons, recommendations | Specialist artifact creation, low-level indicators, model training, critique fabrication |

The same object can move through several agents without blurring ownership:

```text
rolling_volatility_30
  -> Quantitative Methods artifact as a deterministic transform

rolling_volatility_30 used as model input
  -> ML Agent feature input

"High-volatility regimes alter trend-following performance"
  -> Hypothesis Agent hypothesis card

"Strategy performance is unstable across volatility regimes"
  -> Evaluation Agent critique
```

## Owned Artifact Families

The Quantitative Methods Agent should own the following artifacts.

| Artifact | Purpose |
| --- | --- |
| `indicator_contract.json` | Defines a deterministic indicator or transform: inputs, parameters, lookback, warmup, output schema, NaN convention, no-lookahead guarantee, and implementation backend. |
| `statistical_test_contract.json` | Defines null hypothesis, alternative, statistic, assumptions, sample requirements, dependence handling, p-value method, correction method, and failure modes. |
| `indicator_validation_report.json` | Captures fixture tests, edge cases, warmup/NaN behavior, lookahead checks, deterministic replay status, and Python/C++ parity status. |
| `signal_diagnostic_report.json` | Captures predictive association diagnostics such as IC, rank IC, hit rate, quantile monotonicity, forward-return decay, turnover proxy, horizon sensitivity, and symbol/session/regime breakdowns. |
| `multiple_testing_report.json` | Captures tested family size, raw metrics, raw p-values, adjusted p-values, false discovery controls, data-snooping checks, accepted/rejected candidates, warnings, and blockers. |
| `cxx_kernel_manifest.json` | Captures compiled kernel identity, source/template provenance, ABI/build metadata, wrapper information, supported input/output schemas, and benchmark summary. |
| `python_cpp_parity_report.json` | Captures seeded parity fixtures, tolerance policy, mismatches, numerical warnings, and whether the compiled implementation is safe for downstream use. |
| `method_package_manifest.json` | Bundles contracts, implementations, tests, reports, provenance, and artifact references for supervisor handoff. |

## Method Contract Schema Sketches

### Indicator Contract

```json
{
  "artifact_type": "indicator_contract",
  "agent_owner": "Quantitative Methods Agent",
  "method_id": "ema_cross",
  "method_version": "1.0.0",
  "family": "trend_transform",
  "description": "Difference or sign relationship between two exponential moving averages.",
  "inputs": {
    "required_columns": ["timestamp", "close"],
    "index": "timestamp",
    "frequency_policy": "bar_aligned"
  },
  "parameters": {
    "fast_window": {"type": "integer", "minimum": 2},
    "slow_window": {"type": "integer", "minimum": 3, "must_exceed": "fast_window"}
  },
  "warmup": {
    "minimum_bars": "slow_window",
    "output_before_warmup": "null"
  },
  "outputs": {
    "columns": ["ema_fast", "ema_slow", "ema_diff", "ema_cross_signal"],
    "dtype_policy": "float64_except_signal_int8"
  },
  "numerical_policy": {
    "nan_policy": "propagate",
    "inf_policy": "reject",
    "tolerance": 1e-10
  },
  "lookahead_policy": {
    "uses_future_data": false,
    "alignment": "output_at_bar_close"
  },
  "implementations": {
    "python_reference": "trader_standard.indicators.python.ema_cross",
    "cpp_kernel": "optional"
  },
  "provenance": {
    "created_by": "Quantitative Methods Agent",
    "source_request_id": "req_...",
    "code_version": "git_sha_or_build_id"
  }
}
```

### Statistical Test Contract

```json
{
  "artifact_type": "statistical_test_contract",
  "agent_owner": "Quantitative Methods Agent",
  "method_id": "rank_ic_test",
  "method_version": "1.0.0",
  "family": "signal_diagnostic",
  "null_hypothesis": "Indicator ranks have no association with future return ranks.",
  "alternative": "Indicator ranks are associated with future return ranks.",
  "required_inputs": [
    "indicator_observation_reference",
    "forward_return_label_reference",
    "data_quality_report_reference"
  ],
  "statistic": "spearman_rank_correlation",
  "dependence_handling": {
    "method": "block_bootstrap_or_hac",
    "required_config": ["block_length", "num_resamples"]
  },
  "multiple_testing": {
    "supported_corrections": ["bonferroni", "holm", "benjamini_hochberg", "white_reality_check", "hansen_spa"]
  },
  "sample_requirements": {
    "minimum_observations": 500,
    "minimum_symbols": 1,
    "minimum_non_null_fraction": 0.95
  },
  "failure_modes": [
    "candidate_family_not_declared",
    "insufficient_effective_observations",
    "unresolved_data_quality_warnings",
    "overlapping_forward_returns_without_dependence_adjustment"
  ]
}
```

## Statistical Method Knowledge Base

The Quantitative Methods Agent should use a structured registry of methods, not free-form memory. Each method entry should define purpose, inputs, outputs, assumptions, failure modes, and whether the method is approved for MCP execution.

### Registry Entry Sketch

```json
{
  "method_id": "white_reality_check",
  "family": "multiple_testing",
  "status": "planned",
  "purpose": "Adjust performance inference for data-snooping across a declared candidate strategy or signal family.",
  "inputs": [
    "candidate_return_matrix",
    "benchmark_return_series",
    "block_bootstrap_config",
    "candidate_family_manifest"
  ],
  "outputs": [
    "test_statistic",
    "p_value",
    "candidate_family_size",
    "warnings"
  ],
  "assumptions": [
    "candidate family is fully declared before inference",
    "return series are suitable for dependence-aware resampling"
  ],
  "failure_modes": [
    "family not fully recorded",
    "too few effective observations",
    "unstable bootstrap configuration",
    "unresolved data quality warnings"
  ],
  "artifact_outputs": ["multiple_testing_report.json"]
}
```

### Initial Method Families

| Area | Initial methods |
| --- | --- |
| Core transforms | SMA, EMA, WMA, returns, log returns, cumulative returns, rolling mean, rolling standard deviation, z-score, min/max range, drawdown, rolling drawdown. |
| Trend and momentum | EMA cross, MACD, rate of change, Donchian breakout, slope over window, rolling regression beta/slope. |
| Mean reversion | RSI, Bollinger Band distance, rolling z-score, distance from moving average, spread/z-score transforms for pairs or baskets. |
| Volatility and range | ATR, Parkinson-style range proxy, realized volatility, rolling absolute return, volatility-of-volatility, gap/range diagnostics. |
| Cross-sectional transforms | Cross-sectional rank, percentile rank, demeaned value, sector/group neutralization if metadata exists, winsorization, robust z-score. |
| Dependence diagnostics | Autocorrelation, partial autocorrelation, Ljung-Box-style checks, overlapping-label warnings, HAC/Newey-West-style standard errors where applicable. |
| Stationarity and regime instability | ADF-style unit-root checks, KPSS-style stationarity checks, rolling statistic stability, structural-break flags. |
| Signal diagnostics | Pearson IC, Spearman rank IC, hit rate, quantile bucket returns, monotonicity score, forward-return decay, horizon sensitivity, turnover proxy. |
| Resampling | IID bootstrap only when valid, block bootstrap, stationary bootstrap, bootstrap confidence intervals. |
| Multiple testing | Bonferroni, Holm, Benjamini-Hochberg FDR, White Reality Check, Hansen SPA. |
| Backtest-overfitting diagnostics | Deflated Sharpe Ratio, Probability of Backtest Overfitting, combinatorially symmetric cross-validation, parameter stability surfaces. |
| Operational numerics | Streaming rolling windows, online mean/variance, warmup semantics, NaN propagation, finite precision tolerance, deterministic replay. |

## Expanded MCP Tool Surface

The existing planned tools should remain as the first slice, but they should be generalized from “indicator contracts” to “method contracts.”

### Initial Tools

| Tool | Owner | Side effect | Purpose |
| --- | --- | --- | --- |
| `math_list_method_contracts` | Quantitative Methods Agent | `read_only` | List maintained indicators, transforms, statistical tests, diagnostics, and multiple-testing procedures. |
| `math_validate_method_contract` | Quantitative Methods Agent | `read_only` | Validate method parameters, input schema, warmup behavior, assumptions, and fixture expectations. |

Backward-compatible aliases may be kept initially:

```text
math_list_indicator_contracts -> math_list_method_contracts filtered to indicator/transform families
math_validate_indicator_contract -> math_validate_method_contract filtered to indicator/transform families
```

### Follow-on Tools

| Tool | Owner | Side effect | Purpose |
| --- | --- | --- | --- |
| `math_create_indicator_contract` | Quantitative Methods Agent | `local_mutating` | Create a structured indicator contract from an approved template family. |
| `math_run_indicator_fixtures` | Quantitative Methods Agent | `local_mutating` | Run deterministic fixture tests and produce `indicator_validation_report.json`. |
| `math_run_signal_diagnostics` | Quantitative Methods Agent | `local_mutating` | Given declared signal observations and forward-return labels, produce `signal_diagnostic_report.json`. |
| `math_run_multiple_testing_report` | Quantitative Methods Agent | `local_mutating` | Given a declared candidate family and metric matrix, produce `multiple_testing_report.json`. |
| `math_generate_cpp_kernel` | Quantitative Methods Agent | `local_mutating` | Generate C++ only from approved templates and produce draft kernel metadata. |
| `math_compile_kernel` | Quantitative Methods Agent | `local_mutating` | Compile the generated/maintained kernel locally and return build evidence. |
| `math_run_python_cpp_parity` | Quantitative Methods Agent | `local_mutating` | Compare Python reference output against C++ output on fixtures and seeded generated cases. |
| `math_package_method_artifact` | Quantitative Methods Agent | `local_mutating` | Bundle contracts, implementation refs, validation reports, parity reports, and provenance for handoff. |

## C++ Kernel Policy

The C++ path is valuable, but it should be template-restricted. The Quantitative Methods Agent should not emit arbitrary runtime code into the trading system.

Recommended flow:

```text
Python reference implementation
  -> deterministic fixtures
  -> approved C++ template selection
  -> C++ implementation
  -> Python binding
  -> Python/C++ parity tests
  -> benchmark report
  -> cxx_kernel_manifest.json
  -> supervisor handoff
```

### C++ Guardrails

- No arbitrary includes outside an allowlist.
- No network, filesystem mutation, broker access, SQL access, or process execution from generated kernels.
- No dynamic code loading in the live trading hot path.
- All generated kernels must compile in an isolated build directory.
- All compiled kernels must pass Python/C++ parity tests before registration.
- All kernels must declare warmup, NaN, alignment, dtype, and lookahead policies.
- All kernels must support deterministic replay.
- Failed parity blocks downstream operational use.

### Suggested Package Placement

Stable maintained kernels should live in `trader_standard`, while research orchestration and artifact reporting should live in `trader_research`.

```text
src/trader_standard/
  indicators/
    python/
    cpp/
    bindings/
    contracts/

src/trader_research/
  math_tools.py
  math_registry.py
  signal_diagnostics.py
  multiple_testing.py
  cpp_kernel_artifacts.py

src/trader_agents/
  quant_methods_agent.py
  quant_methods_policy.py
```

This keeps the core `trader` package free of agent/MCP schemas and keeps maintained reusable implementations separate from research artifact production.

## Quantitative Methods LangGraph Identity

The Quantitative Methods Agent graph should have its own state, policy, allowlist, and artifact contract.

### State Sketch

```python
class QuantMethodsState(TypedDict, total=False):
    agent_identity: str
    request_id: str
    bounded_request: dict
    input_artifact_refs: list[dict]
    method_contract_refs: list[dict]
    validation_report_refs: list[dict]
    signal_diagnostic_report_refs: list[dict]
    multiple_testing_report_refs: list[dict]
    cxx_kernel_manifest_refs: list[dict]
    parity_report_refs: list[dict]
    warnings: list[str]
    blockers: list[str]
    called_tools: list[dict]
    public_status: str
```

### Allowed Tool Pattern

The graph may call:

```text
mcp_health
mcp_get_config
math_list_method_contracts
math_validate_method_contract
math_create_indicator_contract
math_run_indicator_fixtures
math_run_signal_diagnostics
math_run_multiple_testing_report
math_generate_cpp_kernel
math_compile_kernel
math_run_python_cpp_parity
math_package_method_artifact
```

The graph must not call:

```text
data_*
ml_*
hypothesis_*
evaluation_*
adversarial_*
research_run_backtest
research_generate_recommendation
place_order
cancel_order
raw_sql
broker_mutating_tools
```

## LLM Policy for Quantitative Methods

The Quantitative Methods Agent may eventually use an LLM inside a bounded LangGraph control-policy node, but the LLM must not directly execute code or bypass deterministic tools.

Allowed LLM decisions:

```text
select_method_contract
request_missing_input
validate_method_contract
run_fixtures
run_signal_diagnostics
run_multiple_testing
request_cpp_kernel
run_parity_check
package_artifact
block
finish
```

Every proposed action must be validated by a deterministic router against:

- tool allowlist
- side-effect policy
- input artifact ownership
- required data-quality references
- candidate family declaration
- loop limit
- artifact output contract
- no raw prompt or hidden reasoning persistence

## Supervisor Handoff Contract

Every Quantitative Methods handoff to the Quant Research Supervisor should include:

```json
{
  "agent_owner": "Quantitative Methods Agent",
  "handoff_type": "math_method_artifact",
  "artifact_refs": [
    {
      "artifact_type": "indicator_contract",
      "path": "artifacts/research/.../indicator_contract.json"
    },
    {
      "artifact_type": "indicator_validation_report",
      "path": "artifacts/research/.../indicator_validation_report.json"
    },
    {
      "artifact_type": "multiple_testing_report",
      "path": "artifacts/research/.../multiple_testing_report.json"
    }
  ],
  "source_inputs": [
    "dataset_manifest_ref",
    "data_quality_report_ref",
    "candidate_family_manifest_ref"
  ],
  "warnings": [],
  "blockers": [],
  "side_effect": "local_mutating",
  "provenance": {
    "request_id": "req_...",
    "code_version": "git_sha_or_build_id",
    "created_at": "iso8601_timestamp"
  }
}
```

The supervisor may accept, reject, request more work, or block the research path. It must not rewrite Quantitative Methods artifacts to make a result look better.

## Revised Backlog Chunks

Replace the current chunks 23-26 with the expanded sequence below. This keeps the existing delivery pattern: deterministic MCP evidence first, LangGraph identity second, supervisor handoff third.

### 23A. Math Method Domain Schemas

Description:

Define schemas for:

- `indicator_contract.json`
- `statistical_test_contract.json`
- `indicator_validation_report.json`
- `signal_diagnostic_report.json`
- `multiple_testing_report.json`
- `cxx_kernel_manifest.json`
- `python_cpp_parity_report.json`
- `method_package_manifest.json`

Files affected:

```text
src/trader_research/math_domain.py
src/trader_research/domain.py
tests/test_math_domain.py
```

Acceptance criteria:

- Schemas serialize to JSON-safe dictionaries.
- Every schema includes `agent_owner = "Quantitative Methods Agent"`.
- Every schema includes provenance fields.
- Validation rejects missing input references, missing parameters, missing version, and unknown artifact types.
- Schemas preserve artifact boundaries between Quantitative Methods, ML, Hypothesis, Evaluation, and Supervisor.

### 23B. Math Method Registry

Description:

Create a maintained registry of approved indicator, transform, statistical-test, diagnostic, and multiple-testing method contracts.

Files affected:

```text
src/trader_research/math_registry.py
src/trader_research/math_tools.py
tests/test_math_registry.py
```

Acceptance criteria:

- Registry lists maintained methods by family.
- Unsupported methods fail closed.
- Each method declares inputs, outputs, assumptions, failure modes, side-effect class, and artifact outputs.
- Registry can filter to legacy indicator-only views for compatibility.

### 23C. Indicator Contract and Fixture Validation

Description:

Implement deterministic indicator/transform validation.

Files affected:

```text
src/trader_research/math_tools.py
src/trader_standard/indicators/python/*
tests/test_math_indicator_contracts.py
tests/fixtures/math_indicators/*
```

Acceptance criteria:

- Contract validation checks parameter bounds, warmup behavior, NaN policy, output schema, and no-lookahead metadata.
- Fixture tests cover small known input/output cases.
- Validation returns `indicator_validation_report.json` or an embedded equivalent envelope.
- Unsupported indicators and invalid parameter grids fail closed.

### 23D. Signal Diagnostics

Status: implemented for the revised 23L signal-composition slice in `9924922`.

Description:

Implement first-pass signal-composition diagnostics for declared signal candidates against caller-supplied
forward-return labels. Indicators may appear as explanatory metadata, but the primary tested unit is a signal candidate
that emits trade intent (`-1/0/+1`) or a continuous signal score.

Files affected:

```text
src/trader_research/signal_diagnostics.py
src/trader_research/math_tools.py
tests/test_signal_diagnostics.py
```

Acceptance criteria:

- Computes IC and rank IC where valid.
- Requires approved method-card evidence for `rank_ic`.
- Computes action hit rate with sample counts.
- Computes action-conditioned returns for discrete trade-intent signals.
- Computes quantile bucket summaries and monotonicity scores for continuous signal scores.
- Computes horizon decay when multiple forward horizons are supplied.
- Breaks results down by symbol and optionally session/regime if columns exist.
- Records implementation references when a candidate declares a validated `trader.signals.Signal` manifest.
- Warns when a candidate is observational because no executable implementation is declared.
- Produces `signal_diagnostic_report.json` with warnings for weak sample size, missing labels, or unresolved data-quality issues.

### 23E. Multiple Testing and Data-Snooping Controls

Status: implemented for Benjamini-Hochberg candidate-family correction in `9924922`; broader data-snooping controls
remain follow-on work.

Description:

Implement first-pass multiple-testing reports for declared candidate families.

Files affected:

```text
src/trader_research/multiple_testing.py
src/trader_research/math_tools.py
tests/test_multiple_testing.py
```

Acceptance criteria:

- Requires a declared candidate family manifest.
- Records full candidate count and parameter grid.
- Requires approved method-card evidence for `benjamini_hochberg`.
- Computes raw and adjusted p-values with Benjamini-Hochberg correction.
- Reports rejection flags, accepted candidate IDs, and rejected candidate IDs.
- Fails closed on missing family manifests, duplicate candidates, unknown metric rows, duplicate p-value rows, invalid
  p-values, and missing candidate p-values.
- Bonferroni, Holm, White Reality Check, Hansen SPA, Deflated Sharpe Ratio, and PBO are follow-on methods.
- Produces `multiple_testing_report.json` with accepted/rejected candidates, warnings, and blockers.

### 23F. C++ Kernel Path

Description:

Implement a controlled compiled-kernel path for approved deterministic transforms.

Files affected:

```text
src/trader_research/cpp_kernel_artifacts.py
src/trader_research/math_tools.py
src/trader_standard/indicators/cpp/*
src/trader_standard/indicators/bindings/*
tests/test_cpp_kernel_artifacts.py
tests/test_python_cpp_parity.py
```

Acceptance criteria:

- C++ generation is template-based only.
- Compilation occurs in an isolated local build directory.
- Kernel manifest records build settings, ABI/binding info, source/template provenance, and benchmark summary.
- Python/C++ parity tests run on deterministic fixtures and seeded generated cases.
- Failed compile or failed parity returns a blocking Quantitative Methods envelope.
- No generated kernel has access to broker mutation, SQL, network, or live trading controls.

### 24. Register Quantitative Methods MCP Tools

Description:

Expose the Quantitative Methods deterministic tool surface through MCP.

Files affected:

```text
src/trader_mcp/server.py
src/trader_mcp/schemas.py
tests/test_mcp_math_tools.py
tests/test_mcp_server.py
```

Acceptance criteria:

- MCP exposes `math_list_method_contracts` and `math_validate_method_contract` first.
- Backward-compatible aliases for `math_list_indicator_contracts` and `math_validate_indicator_contract` may exist.
- Follow-on tools are registered only after their direct services pass tests.
- Every tool returns a shared envelope with `agent_owner = "Quantitative Methods Agent"`.
- Every tool declares side-effect class.
- MCP rejects unbounded inputs and unknown methods.

### 25. Quantitative Methods Agent Graph

Description:

Create the Quantitative Methods LangGraph identity and state model.

Files affected:

```text
src/trader_agents/quant_methods_agent.py
src/trader_agents/quant_methods_policy.py
src/trader_agents/state.py
tests/test_quant_methods_agent.py
tests/test_langgraph_agents.py
```

Acceptance criteria:

- Quantitative Methods graph has a distinct identity and state schema.
- Graph calls Quantitative Methods MCP tools only.
- Graph cannot fetch data, create hypotheses, train models, run backtests, call evaluation tools, or promote strategies.
- Graph returns method artifact references and structured blockers.
- No raw prompts, hidden reasoning, or scratchpads are persisted.

### 26. Supervisor Consumes Quantitative Methods Handoff

Description:

Allow the Quant Research Supervisor to consume Quantitative Methods artifacts without rewriting them.

Files affected:

```text
src/trader_agents/quant_research.py
src/trader_research/domain.py
tests/test_supervisor_quant_methods_handoff.py
```

Acceptance criteria:

- Supervisor accepts valid Quantitative Methods handoffs.
- Supervisor rejects handoffs with wrong `agent_owner`, missing provenance, missing artifact refs, or unresolved blockers.
- Supervisor can require Quantitative Methods artifacts before strategy planning when a hypothesis depends on deterministic indicators or statistical tests.
- Supervisor stores references, warnings, blockers, and public status only.
- Supervisor does not modify Quantitative Methods artifacts.

## Revised Slice 5 and Slice 6 Text

### Slice 5: Quantitative Methods MCP Tool Creation

Implement chunks 23A-24. This creates and proves the first Quantitative Methods MCP tools before the Quantitative Methods LangGraph identity exists.

Evidence target:

```text
math_list_method_contracts
math_validate_method_contract
math_run_indicator_fixtures
  -> returns method metadata or validation reports
  -> declares agent_owner = Quantitative Methods Agent
  -> records assumptions, warmup behavior, fixture status, and failure modes
```

Implemented 23L evidence:

```text
math_run_signal_diagnostics
math_run_multiple_testing_report
  -> returns signal-composition diagnostics and Benjamini-Hochberg multiple-testing reports
  -> requires approved method-card evidence for rank_ic and benjamini_hochberg
  -> records candidate family size, tested parameter grid, raw p-values, adjusted p-values, accepted/rejected candidates, warnings, and blockers
```

### Slice 6: Quantitative Methods Agent Identity and Handoff

Implement chunks 25-26. This proves that the Quantitative Methods graph has its own identity and that the supervisor consumes, but does not rewrite, Quantitative Methods artifacts.

Evidence target:

```text
Quantitative Methods graph starts
  -> graph state includes Quantitative Methods identity
  -> graph calls only Quantitative Methods MCP tools
  -> graph returns method artifact references
  -> supervisor consumes Quantitative Methods handoff
  -> supervisor preserves ownership/provenance and blocks unresolved method warnings
```

## End-to-End Example

```text
Data Agent
  -> dataset_manifest.json
  -> data_quality_report.json

Quantitative Methods Agent
  -> indicator_contract.json for rolling_volatility_30
  -> indicator_validation_report.json
  -> signal_diagnostic_report.json against 1h/1d forward returns
  -> multiple_testing_report.json for volatility-window grid
  -> optional cxx_kernel_manifest.json
  -> optional python_cpp_parity_report.json

Hypothesis Agent
  -> hypothesis_card.json:
     "Trend-following signals perform better in persistent high-volatility regimes."

ML Agent, if needed
  -> regime_model_card.json
  -> prediction_artifact.json
  -> drift_report.json

Quant Research Supervisor
  -> experiment_plan.json
  -> strategy validation
  -> backtest suite
  -> comparison report

Evaluation Agent
  -> evaluation_report.json

Adversarial Agent
  -> robustness_report.json

Quant Research Supervisor
  -> recommendation_report.json
```

## Non-Goals

The Quantitative Methods Agent should not:

- fetch or backfill market data
- choose the trading universe
- invent strategy hypotheses
- train ML models
- run broad strategy campaigns
- execute backtests except tiny deterministic method fixtures
- decide that a strategy passed or failed overall
- make promotion recommendations
- mutate broker state
- expose raw SQL
- place, cancel, or modify orders
- compile arbitrary unreviewed code into the live trading runtime

## Acceptance Criteria for the Expanded Quantitative Methods Release

1. Method contracts exist for deterministic indicators, transforms, statistical tests, diagnostics, and multiple-testing procedures.
2. Unsupported methods fail closed.
3. Indicator validation includes fixture tests, warmup behavior, NaN policy, output schema, and no-lookahead metadata.
4. Signal diagnostics are artifact-producing and include sample-size warnings.
5. Multiple-testing reports require a declared candidate family and record the full tested universe.
6. Raw and adjusted p-values are stored together with the correction method and assumptions.
7. Python reference implementations exist before C++ operational kernels are promoted.
8. C++ kernels are template-restricted, compiled locally, and parity-tested against Python.
9. Failed fixture, failed compile, or failed parity creates a blocker.
10. Quantitative Methods MCP tools return shared envelopes with `agent_owner = "Quantitative Methods Agent"` and explicit side-effect class.
11. The Quantitative Methods LangGraph graph can call only Quantitative Methods MCP tools.
12. Supervisor handoffs preserve Quantitative Methods ownership and provenance.
13. No Quantitative Methods output claims final alpha or promotion readiness.

## Practical First Implementation Order

The smallest useful version is:

```text
1. Define math artifact schemas.
2. Build method registry.
3. Register list/validate MCP tools.
4. Implement deterministic fixtures for a tiny indicator set:
   - SMA
   - EMA
   - rolling volatility
   - z-score
   - RSI
5. Add signal diagnostics:
   - IC
   - rank IC
   - action-conditioned returns
   - quantile buckets
   - horizon decay
6. Add multiple-testing report:
   - candidate family manifest
   - raw p-values
   - Benjamini-Hochberg
   - Bonferroni and Holm as follow-on corrections
7. Add Quantitative Methods LangGraph identity.
8. Add supervisor handoff consumption.
9. Add C++ path only after Python contracts and reports are stable.
```

This avoids building a premature C++ system before the artifact contracts and statistical evidence layer are stable.

## Summary

The Quantitative Methods Agent should not be a strategy generator and should not be a generic ML substitute. It should be the system’s deterministic quant methods owner.

Its job is to answer:

```text
Is this transform mathematically defined?
Is it implemented correctly?
Does it avoid lookahead?
Does it have deterministic fixture coverage?
Does the signal show predictive association under valid assumptions?
Did we account for the number of things we tested?
Can the same calculation run consistently in Python research and C++ runtime?
Can another agent inspect the artifact and challenge the evidence?
```

That makes it meaningfully distinct from the ML Agent and Hypothesis Agent while giving the overall trading research system a much stronger statistical foundation.
