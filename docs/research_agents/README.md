# Research Agents And MCP Documentation

This is the starting point for understanding Trader's research system. The research layer turns bounded data and
supplied executable code into deterministic, inspectable evidence. It sits above the core trading runtime and outside
the live trading hot path.

## What Trader Research Does

The primary implemented path is:

```text
Data Agent scope and quality evidence
  -> content-addressed strategy and risk implementation versions
  -> immutable strategy, risk-stack, and backtest specifications
  -> canonical Postgres backtest run
  -> optional provider-neutral parameter optimisation
  -> separately executed untouched-holdout backtest
  -> Evaluation-owned performance report
  -> Adversarial-owned robustness report
```

The Knowledge and Methodology contexts provide an optional source-backed route into implementation authoring:

```text
registered and ingested source
  -> citeable evidence units and methodology evidence
  -> approved method card
  -> optional implementation producer
  -> normal implementation registration and validation path
```

A method card is provenance, not an execution identity. Handwritten, AI-produced, maintained, and methodology-produced
code receives the same implementation validation. Data Agent artifacts remain the only source of symbols, timeframe,
date bounds, provider scope, and market-data quality.

Trader Postgres is canonical for implementations, specifications, runs, trial ledgers, Evaluation, and Adversarial
evidence. MCP is the control-plane API over deterministic services. LangGraph agents constrain tool access and preserve
artifact ownership. Research tools cannot place live orders, mutate broker state, clear halts, or expose raw SQL.

## Start Here

Read the active documentation in this order. Do not read `architecture.md` from top to bottom before establishing the
product flow.

| Step | Read | Question it answers |
| ---: | --- | --- |
| 1 | [Current Capability Baseline](#current-capability-baseline) | What works now, what is maintained, and what is only planned? |
| 2 | [architecture.md](architecture.md#bounded-context-architecture) | Which package owns each responsibility, and which dependencies are allowed? |
| 3 | [agents.md](agents.md) | Which agent owns each artifact and decision boundary? |
| 4 | [workflows.md](workflows.md) | How do tools compose into useful evidence-producing procedures? |
| 5 | [mcp_tools.md](mcp_tools.md) | Which MCP tools are actually registered and callable? |
| 6 | [tool_contracts.md](tool_contracts.md) | What are the exact request, envelope, artifact, and fail-closed contracts? |
| 7 | [operations.md](operations.md) | How is MCP configured, gated, persisted, inspected, and verified? |

The [active tracker](../../plans/mcp_trading_research_tools_plan.md) records delivery lineage and acceptance evidence.
It is not the introductory product manual. Files under [history/](history/) explain superseded designs and should not be
used to infer current tools or import paths.

## Topic Reading Paths

### Strategy Implementation And Backtesting

1. [workflows.md: Worked Implementation-To-Evidence Walkthrough](workflows.md#worked-implementation-to-evidence-walkthrough)
2. [tool_contracts.md: Canonical Implementation, Specification, And Optimisation Contracts](tool_contracts.md#canonical-implementation-specification-and-optimisation-contracts)
3. [mcp_tools.md: Quant Research Supervisor Tools](mcp_tools.md#quant-research-supervisor-tools)
4. [../core/first_strategy.md](../core/first_strategy.md) and [../core/backtesting.md](../core/backtesting.md) for the
   underlying runtime interfaces and backtest engine

### Knowledge Ingestion And Method Cards

1. [semantic_extraction.md](semantic_extraction.md)
2. [workflows.md: Methodology Operator Workflow](workflows.md#methodology-operator-workflow)
3. [operations.md: Methodology Operating Checklist](operations.md#methodology-operating-checklist)
4. [architecture.md: Canonical Method Card Architecture](architecture.md#canonical-method-card-architecture)

### Parameter Optimisation And Review

1. [architecture.md: Experiment Tracking And Optimisation Architecture](architecture.md#experiment-tracking-and-optimisation-architecture)
2. [workflows.md: Parameter Optimisation And Independent Audit](workflows.md#parameter-optimisation-and-independent-audit)
3. [tool_contracts.md: Canonical Implementation, Specification, And Optimisation Contracts](tool_contracts.md#canonical-implementation-specification-and-optimisation-contracts)
4. [operations.md: Controlled Verification Procedure](operations.md#controlled-verification-procedure)

### ML Lifecycle And Runtime Prediction

1. [architecture.md: ML Lifecycle Architecture](architecture.md#ml-lifecycle-architecture)
2. [workflows.md: MLflow Model Lifecycle And Runtime Integration](workflows.md#mlflow-model-lifecycle-and-runtime-integration)
3. [agents.md: ML Lifecycle Ownership](agents.md#ml-lifecycle-ownership)
4. [mcp_tools.md: ML Agent Tools](mcp_tools.md#ml-agent-tools)

Runtime prediction, deployment validation, and strategy binding are implemented by 39H-I. Feature engineering,
training, model evaluation/registration, and drift remain the 39A-G/J roadmap.

## Document Roles

| Document | Use it for | Do not use it for |
| --- | --- | --- |
| [architecture.md](architecture.md) | Current package boundaries, authority, persistence, safety, and subsystem designs. | Tool availability or historical refactor sequencing. |
| [agents.md](agents.md) | Agent missions, artifact ownership, allowlists, and handoffs. | Detailed request schemas. |
| [mcp_tools.md](mcp_tools.md) | Registered tool catalog, owners, side effects, and capability gates. | Service internals. |
| [workflows.md](workflows.md) | End-to-end procedures and artifact flow. | Exact field-level contracts. |
| [tool_contracts.md](tool_contracts.md) | Request fields, envelopes, validation, and artifact contracts. | Introductory reading. |
| [operations.md](operations.md) | Startup, environment, Postgres, policy gates, and qualification. | Conceptual domain ownership. |
| [semantic_extraction.md](semantic_extraction.md) | Claim-level methodology evidence and method-card extraction semantics. | Generic strategy execution. |

## Current Capability Baseline

The knowledge-base and methodology work is now a maintained subsystem rather than the active delivery focus. The
following distinctions are important when assessing what the platform can do today:

| Area | Functionally available | Current boundary | Delivery posture |
| --- | --- | --- | --- |
| Data Agent | Symbol discovery, bounded inventory, quality reports, dataset manifests, and gated loading evidence. | Calendar-aware equity quality remains a backlog item; agents do not choose hidden data scope. | Maintain and fix regressions. |
| Knowledge-base creation | Postgres-first source registration, full-document PDF/Markdown/text ingestion, schema-v2 evidence units, lexical/vector indexes, semantic retrieval, bounded dereferencing, ingestion status, and source listing. | OCR is not provided for image-only pages; registration alone does not ingest a document. | Maintain and protect stored-data integrity. |
| Methodology evidence | Open-world identity discovery, claim spans, target-bound evidence packets, rich-field extraction, semantic validation, stable method-card sets, drafts, approval, and lineage. | Reliable for bounded locally identifiable methods; book-scale composite frameworks and source-discovered ontologies are not represented faithfully. Real sources can and should block before card creation. | Paused after 33AB; composite-method work is deferred. |
| Method implementations | Maintained indicator/signal contracts plus content-addressed strategy, risk-manager, and optimisation-objective registration/validation. | Supplied, maintained, AI-produced, and methodology-produced source receives identical eligibility checks; no method card is required. | Maintain the decoupled registry boundary. |
| Backtesting | Immutable strategy/risk/backtest specifications, gated canonical DB-backed execution, comparisons, and multi-asset risk evidence. | Candidate/stack and filesystem run contracts are retired; Data Agent quality and exact source hashes fail closed. | Foundation complete for ML and robustness work. |
| ML | Provider-neutral feature/prediction contracts, lazy local MLflow pyfunc inference, DB-backed deployment manifests/validations, typed strategy bindings, maintained prediction mappers/strategy, bounded prediction/signal/order lineage, and synchronized-universe execution. | Upstream feature-set, training, evaluation, registry-version, and monitoring tools are not implemented; deployment MCP calls therefore require already persisted passed feature/model evidence. Live eligibility and runtime mutation are excluded. | 39H-I implemented; complete 39A-G and 39J around this boundary. |
| Parameter optimisation and tracking | Provider-neutral plans/trial ledgers, deterministic grid/random engines, optional lazy Optuna TPE, explicit non-authoritative tracking projection, sealed-holdout Evaluation. | First slice is sequential, finite, single-objective, and has no pruning; Optuna/MLflow are optional. | Implemented foundation. |
| Robustness and adversarial evaluation | Independent parameter-optimisation attack planning and judgment are registered. | Broader cost/data perturbation execution remains tasks 44/46. | Active next focus. |
| Walk-forward optimisation | Provider-neutral optimisation contracts now exist for composition inside folds. | Fold construction, stitched OOS report, and walk-forward audit remain deferred tasks 58-59. | Build after ML integration and broader robustness primitives. |

The implementation-to-evidence, parameter-optimisation, and model-backed execution foundations are present. The next ML
work is 39A-G/J: point-in-time feature engineering, fitting, recording, evaluation, immutable model versioning, and
prediction monitoring around the implemented runtime boundary. Knowledge and Data Agent tools remain supported
dependencies, but further autonomous methodology-understanding work is not on the current critical path.

## Sources Of Truth

When documentation and implementation disagree, inspect these current sources and then correct the documentation:

- Registered MCP tools and capability flags: `src/trader_mcp/constants.py`.
- MCP transport envelopes and side-effect classification: `src/trader_mcp/contracts.py`.
- Agent identities, tool ownership, and allowlists: `src/trader_research/governance/ownership.py`.
- Artifact types and ownership: `src/trader_research/governance/artifacts.py`.
- Public research application surfaces: the `__init__.py` facade in each `trader_research` bounded context.
- Canonical Postgres persistence and projection registration: `src/trader_research/infrastructure/postgres/`.
- Implementation status and roadmap: `plans/mcp_trading_research_tools_plan.md`.
