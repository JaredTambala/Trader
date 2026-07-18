# Research Agent Definitions

This document describes the current agent identities, ownership boundaries, and tool allowlists. The implementation
source of truth is `src/trader_research/agents.py`; artifact ownership is registered in `src/trader_research/domain.py`.

## Agent Map

| Agent | Mission | Current owned artifacts | Current MCP/tool access |
| --- | --- | --- | --- |
| Quant Research Supervisor Agent | Coordinate research workflows and synthesize specialist-owned evidence. | Strategy/risk implementation versions, immutable strategy/risk/backtest specifications, canonical backtest runs, optimisation plans/runs/trials, tracking projection reports, comparisons, and planned walk-forward runs. | Registered implementation/specification/backtest/optimisation/projection `research_*` tools. |
| Data Agent | Produce trustworthy bounded market-data manifests and quality evidence. | Symbol discovery reports, dataset manifests, data-quality reports, load result envelopes. | `mcp_health`, `mcp_get_config`, `data_discover_symbols`, `data_get_inventory`, `data_summarize_quality`, `data_ensure_loaded`. |
| Quantitative Methods Agent | Produce auditable deterministic methods, method evidence, diagnostics, and statistical inference artifacts. | Knowledge manifests, methodology candidates, methodology evidence packets, methodology extraction/validation reports, legacy projections and canonical method cards, implementation manifests, validation reports, diagnostics, multiple-testing reports, method packages, optional kernel manifests. | `mcp_health`, `mcp_get_config`, `knowledge_*`, and current `math_*` tools. |
| ML Agent | Coordinate point-in-time feature engineering, fitting, MLflow recording/registry, model evaluation, deployment evidence, predictions, and drift. | Planned feature-set specs, training datasets/splits/pipelines/specs, MLflow run refs, model evaluations and immutable version refs, promotion reports, deployment manifests, prediction artifacts, and drift reports. | Planned 39A-39J ML tools only; no ML tools are currently registered. |
| Hypothesis Agent | Produce explicit falsifiable strategy hypothesis cards. | Hypothesis cards. | Planned `hypothesis_create_card`. |
| Evaluation Agent | Produce skeptical critique and performance evidence from research artifacts. | Untouched-holdout optimisation reports and planned stitched out-of-sample walk-forward reports. | `evaluation_generate_parameter_optimization_report` plus planned broader critique/walk-forward tooling. |
| Adversarial Agent | Produce robustness and stress-test evidence for strategies and research procedures. | Parameter-optimisation audit plans/reports and planned walk-forward audits. | Registered parameter-optimisation audit tools; broader robustness remains planned. |

## Handoff Rules

- Every handoff includes `agent_owner`, artifact type, DB artifact URI or payload, source inputs, parameters, side-effect
  class, warnings, blockers, and provenance refs.
- The supervisor can request more work, reject insufficient evidence, or mark a path blocked.
- The supervisor must not rewrite specialist artifacts to make a strategy look better.
- Promotion to paper trading remains a human-reviewed proposal, not an autonomous action.

## Rich Methodology Ownership

- The Quantitative Methods Agent owns source registration, full-document ingestion, retrieval, methodology candidate
  discovery, family-role evidence assembly, rich field extraction, candidate validation, rich method-card drafts, and
  method-card publishing.
- The Quantitative Methods Agent does not create strategies, risk managers, portfolio backtests, or Evaluation reports.
- Approved rich method cards may be optional provenance for maintained implementation producers. The Supervisor does
  not edit card evidence, and generated source still passes normal implementation validation.
- The Data Agent remains the only owner of dataset manifests and quality reports. Rich method cards must not carry
  symbols, timeframes, date windows, source filters, or load decisions.
- The Evaluation Agent consumes backtest and risk evidence after immutable specifications are validated and executed; it
  does not approve methods or repair missing rich-field citations.

## ML Lifecycle Ownership

- The Data Agent owns raw market-data scope, dataset manifests, and quality evidence. The ML Agent consumes explicit
  Data Agent refs and must not silently widen symbols, dates, timeframes, sources, or row scope.
- The Quantitative Methods Agent may own reusable mathematical feature implementations. The ML Agent owns feature-set
  composition, point-in-time availability rules, target construction, training datasets, folds, fitting, and ML model
  evidence.
- MLflow owns ML training runs, logged model packages, registered-model versions, tags, and aliases. Generic parameter
  optimisation plans, trials, selections, backtests, and audits remain canonical in Trader. The ML Agent owns
  Trader artifacts that reconcile and validate those external records against Data Agent, source, and environment refs.
- The ML Agent may execute only registered, validated, bounded training pipelines through explicitly gated tools.
  Handwritten and AI-produced training code receive the same source-hash, dependency, interface, resource, and safety
  validation. Prompt text is never an executable training input.
- The ML Agent may prepare evaluation, promotion, and deployment evidence, but passed model metrics do not establish
  strategy profitability. The Evaluation Agent owns trading-performance conclusions after backtesting.
- Alias mutation requires explicit policy and approval. The ML Agent cannot hot-swap a running model, mutate trading
  runtime configuration, place broker orders, or grant live eligibility.
- The Quant Research Supervisor binds a passed, immutable model deployment ref to a strategy and backtest. Every run
  pins the resolved model version; mutable aliases are not followed inside a run.
- Runtime prediction occurs through core platform prediction contracts and an optional MLflow adapter. The trading hot
  path does not call MCP; the ML Agent consumes persisted prediction events later for monitoring and drift.

## Walk-Forward Optimisation Ownership

The following split is already enforced for single-region parameter optimisation and is reused by later walk-forward
work:

- The Quant Research Supervisor owns provider-neutral plans, canonical trial ledgers, selections, and immutable variant
  execution. It can use maintained grid/random engines or a configured optional engine through the same protocol.
- The Quantitative Methods Agent owns versioned closed-input optimisation objectives and their validation reports.
- The Evaluation Agent owns the matching sealed-holdout report and cannot change the selected specification.
- The Adversarial Agent owns attack plans and final robustness judgment. It does not execute the original optimiser;
  the Supervisor executes requested variants and returns immutable refs.
- Tracking sinks own no product evidence. Their projection reports remain Supervisor-owned, non-authoritative Trader
  records.

- The Quant Research Supervisor owns the immutable optimisation plan and procedural run. It coordinates declared folds,
  candidate parameters/models, child specifications, selections, and out-of-sample backtests without issuing a
  performance or robustness verdict.
- The ML Agent participates only where a fold engineers features, fits a model, evaluates predictions, or registers an
  immutable model version. Generic strategy-parameter optimisation is not an ML Agent artifact.
- The Evaluation Agent owns the stitched out-of-sample performance report and must exclude in-sample/selection returns
  from reported walk-forward performance.
- The Adversarial Agent owns the independent audit of fold boundaries, window lengths, neighboring selections,
  parameter/model stability, costs, concentration, degradation, search budget, and selection bias. It does not run the
  original optimiser or rewrite its selections.
- Walk-forward optimisation cannot promote a strategy/model, assign an MLflow alias, change runtime configuration, or
  mutate live trading. Tasks 58-59 remain deferred until task 57, model-backed strategy integration through 39I, and
  robustness tasks 44/46 are proven.

## Current Versus Planned Status

Current registered MCP surfaces include Data Agent tools; Quantitative Methods knowledge/math and optimisation-objective
tools; Supervisor implementation registration, immutable specifications, canonical backtests, grid/random/optional
Optuna optimisation, result lookup, immutable variant execution, and tracking projection; untouched-holdout Evaluation;
and parameter-optimisation Adversarial planning/judgment. Candidate/stack and loose baseline/portfolio backtest tools are
not registered after the cutover.

ML, Hypothesis, broader Adversarial/Evaluation critique, attribution, recommendation synthesis,
and supervisor autonomy remain planned unless the MCP tool catalog marks them registered. The planned ML scope is the
full 39A-39J MLflow lifecycle, not only model-card registration; task 40 remains deferred until those deterministic tools
are proven.

## Identity Checks

Agent display names, allowlists, and output artifacts are executable metadata. Update this document when
`src/trader_research/agents.py` changes, and update the documentation consistency test so every agent remains covered.
