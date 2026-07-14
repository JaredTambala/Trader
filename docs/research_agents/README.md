# Research Agents And MCP Documentation

This directory contains the current operating documentation for Trader research agents, MCP tools, and LangGraph
orchestration. It is intentionally split by concern so agents do not have to infer current behavior from old plans.

## Authoritative Current References

- [architecture.md](architecture.md): package boundaries, layer responsibilities, and safety model.
- [semantic_extraction.md](semantic_extraction.md): claim-level methodology evidence, semantic extraction, validation,
  and execution design.
- [agents.md](agents.md): agent identities, owned artifacts, tool allowlists, and handoff rules.
- [mcp_tools.md](mcp_tools.md): current registered MCP tool catalog and planned tool ownership.
- [workflows.md](workflows.md): supported research workflows and near-term portfolio/risk workflow direction.
- [operations.md](operations.md): local MCP server startup, policy gates, persistence expectations, and verification.
- [tool_contracts.md](tool_contracts.md): detailed request/response and artifact contract appendix.

## Current Capability Baseline

The knowledge-base and methodology work is now a maintained subsystem rather than the active delivery focus. The
following distinctions are important when assessing what the platform can do today:

| Area | Functionally available | Current boundary | Delivery posture |
| --- | --- | --- | --- |
| Data Agent | Symbol discovery, bounded inventory, quality reports, dataset manifests, and gated loading evidence. | Calendar-aware equity quality remains a backlog item; agents do not choose hidden data scope. | Maintain and fix regressions. |
| Knowledge-base creation | Postgres-first source registration, full-document PDF/Markdown/text ingestion, schema-v2 evidence units, lexical/vector indexes, semantic retrieval, bounded dereferencing, ingestion status, and source listing. | OCR is not provided for image-only pages; registration alone does not ingest a document. | Maintain and protect stored-data integrity. |
| Methodology evidence | Open-world identity discovery, claim spans, target-bound evidence packets, rich-field extraction, semantic validation, stable method-card sets, drafts, approval, and lineage. | Reliable for bounded locally identifiable methods; book-scale composite frameworks and source-discovered ontologies are not represented faithfully. Real sources can and should block before card creation. | Paused after 33AB; composite-method work is deferred. |
| Method implementations | Maintained indicator/signal contracts, fixture validation, implementation manifests, diagnostics, method packages, and quarantined Python generation. | Existing strategy creation is maintained-template driven and generally emits generated candidate source. There is no first-class registration path for arbitrary handwritten strategy or risk-manager implementations. | Shift toward direct maintained methods and external implementation intake. |
| Backtesting | Validated baseline and multi-asset strategy/risk stacks, gated backtest execution, comparisons, portfolio risk evidence, and performance reports. | Entry is coupled to current strategy-candidate and stack artifacts; reusable backtest specifications for independently supplied strategy code are not yet implemented. | Active next focus. |
| ML | Agent ownership and preliminary feature/model/prediction/drift artifact names exist. | No MLflow adapter or registered feature engineering, time-series fitting, run reconciliation, model evaluation/versioning, deployment, prediction, or drift MCP tools exist yet; the trading runtime has no model inference contract. | Planned 39A-39J lifecycle after implementation intake/backtest specifications. |
| Robustness and adversarial evaluation | Ownership and planned report contracts exist. | No registered perturbation, cost-sensitivity, split-stability, concentration, or adversarial MCP tool exists yet. | Active next focus after reproducible backtest specifications. |
| Walk-forward optimisation | Chronological fold concepts are planned inside ML dataset/evaluation tasks. | No optimisation plan/runner, parameter/model selection loop, stitched OOS report, or independent walk-forward audit tool exists. | Deferred tasks 58-59 after task 57, model-backed strategy integration through 39I, and robustness 44/46. |

The immediate product direction is implementation-to-evidence: register and validate handwritten or AI-produced
indicator, strategy, and risk-manager code; bind it to explicit method and data provenance where available; run
reproducible backtests; then implement the 39A-39J MLflow lifecycle for point-in-time feature engineering, fitting,
recording, evaluation, immutable model versioning, deployment evidence, strategy inference, predictions, and drift.
Robustness/adversarial evidence follows those reproducible baselines. Knowledge and Data Agent tools remain supported
dependencies, but further autonomous methodology-understanding work is not on the current critical path.

## Historical Context

Older briefs, implementation notes, and superseded user guides live under [history/](history/). They can be useful for
context, but they are not authoritative for current tool availability, agent boundaries, or operation.

## Sources Of Truth

When the docs and implementation disagree, resolve the docs from the implementation:

- Registered MCP tools and capability flags: `src/trader_mcp/constants.py`.
- Agent identities and allowlists: `src/trader_research/agents.py`.
- Artifact types and ownership: `src/trader_research/domain.py`.
- Implementation status and roadmap: `plans/mcp_trading_research_tools_plan.md`.
