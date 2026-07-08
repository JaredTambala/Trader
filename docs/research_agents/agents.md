# Research Agent Definitions

This document describes the current agent identities, ownership boundaries, and tool allowlists. The implementation
source of truth is `src/trader_research/agents.py`; artifact ownership is registered in `src/trader_research/domain.py`.

## Agent Map

| Agent | Mission | Current owned artifacts | Current MCP/tool access |
| --- | --- | --- | --- |
| Quant Research Supervisor Agent | Coordinate research workflows and synthesize specialist-owned evidence. | Experiment plans, research suites, strategy candidates, risk-manager candidates, strategy/risk stacks, baseline and portfolio backtest refs, comparison reports, recommendation reports. | Supervisor `research_*` tools plus planned synthesis/experiment tools. |
| Data Agent | Produce trustworthy bounded market-data manifests and quality evidence. | Symbol discovery reports, dataset manifests, data-quality reports, load result envelopes. | `mcp_health`, `mcp_get_config`, `data_discover_symbols`, `data_get_inventory`, `data_summarize_quality`, `data_ensure_loaded`. |
| Quantitative Methods Agent | Produce auditable deterministic methods, method evidence, diagnostics, and statistical inference artifacts. | Knowledge manifests, method cards, implementation manifests, validation reports, diagnostics, multiple-testing reports, method packages, optional kernel manifests. | `mcp_health`, `mcp_get_config`, `knowledge_*`, and current `math_*` tools. |
| ML Agent | Produce versioned feature, model, prediction, and drift artifacts. | Feature dataset manifests, model cards, prediction artifacts, drift reports. | Planned ML tools only. |
| Hypothesis Agent | Produce explicit falsifiable strategy hypothesis cards. | Hypothesis cards. | Planned `hypothesis_create_card`. |
| Evaluation Agent | Produce skeptical critique and performance evidence from research artifacts. | Evaluation reports. | `evaluation_generate_performance_report` and planned broader critique tooling. |
| Adversarial Agent | Produce robustness and stress-test evidence for candidate strategies. | Robustness reports. | Planned robustness tools only. |

## Handoff Rules

- Every handoff includes `agent_owner`, artifact type, artifact path or payload, source inputs, parameters, side-effect
  class, warnings, blockers, and provenance refs.
- The supervisor can request more work, reject insufficient evidence, or mark a path blocked.
- The supervisor must not rewrite specialist artifacts to make a strategy look better.
- Promotion to paper trading remains a human-reviewed proposal, not an autonomous action.

## Current Versus Planned Status

Current registered MCP surfaces include Data Agent tools, Quantitative Methods knowledge/math tools, Supervisor strategy,
risk-manager, strategy/risk stack, baseline/portfolio backtest, and comparison tools, and the first Evaluation
performance-report tool.

ML, Hypothesis, Adversarial, broader Evaluation critique, attribution, recommendation synthesis, experiment running,
and supervisor autonomy remain planned unless the MCP tool catalog marks them registered.

## Identity Checks

Agent display names, allowlists, and output artifacts are executable metadata. Update this document when
`src/trader_research/agents.py` changes, and update the documentation consistency test so every agent remains covered.
