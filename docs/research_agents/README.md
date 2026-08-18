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

One part of that path is now coordinated. The Research Coordinator accepts a typed objective, optional protocol and
optional terminal outcome, then emits exactly one bounded action: request a prerequisite, request approval, select a
registered workflow, report terminal state or stop with a blocker. When the approved inputs are complete, it selects
and compiles the fixed `supplied_implementation_to_evidence` template for execution through MCP with resumable
checkpoints:

```text
objective + optional protocol/outcome
  -> Research Coordinator selects one bounded next action
  -> [when ready] approved objective + protocol + pinned implementation/Data refs
  -> deterministic compiler creates one ready, immutable workflow plan
  -> workflow executor registers the plan and asks the resume shell for the next step
  -> executor calls the registered MCP tool and validates its ToolEnvelope
  -> resume shell accepts a bounded WorkflowStepResult and checkpoints progress
  -> repeat until the executor records a canonical terminal WorkflowOutcome
```

The coordinator policy, declaration contracts, non-executing resume shell, and closed compiler/executor are separate
architectural responsibilities. The coordinator does not author protocols, call specialist agents, change approved
scope, or invent tools; missing state becomes a typed request for its owning domain. The checkpoint database is
replaceable operational state; canonical data, experiment, review, and workflow artifacts remain in the research
artifact store.

Trader Postgres is canonical for implementations, specifications, runs, trial ledgers, Evaluation, and Adversarial
evidence. MCP is the control-plane API over deterministic services. LangGraph agents constrain tool access and preserve
artifact authority. Research tools cannot place live orders, mutate broker state, clear halts, or expose raw SQL.

## Start Here

Read the active documentation in this order. Do not read `architecture.md` from top to bottom before establishing the
product flow.

| Step | Read | Question it answers |
| ---: | --- | --- |
| 1 | [product_state.md](product_state.md) | What works now, how strongly is it qualified, and what can agents orchestrate? |
| 2 | [architecture.md](architecture.md#bounded-context-architecture) | Which package owns each responsibility, and which dependencies are allowed? |
| 3 | [agents.md](agents.md) | Which agent owns each artifact and decision boundary? |
| 4 | [workflows.md](workflows.md) | How do tools compose into useful evidence-producing procedures? |
| 5 | [mcp_tools.md](mcp_tools.md) | Which MCP tools are actually registered and callable? |
| 6 | [tool_contracts.md](tool_contracts.md) | What are the exact request, envelope, artifact, and fail-closed contracts? |
| 7 | [operations.md](operations.md) | How is MCP configured, gated, persisted, inspected, and verified? |

The [active capability roadmap](../../plans/research_capability_roadmap.md) records remaining work, hard dependencies,
parallel workstreams and compact delivery lineage. The [deprecated linear tracker](../../plans/mcp_trading_research_tools_plan.md)
is a migration pointer only. Files under [history/](history/) explain superseded designs and should not be used to infer
current tools or import paths.

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

### Higher-Level Orchestration

1. [product_state.md: Implemented Orchestration At A Glance](product_state.md#implemented-orchestration-at-a-glance)
2. [architecture.md: Higher-Level Orchestration Architecture](architecture.md#higher-level-orchestration-architecture)
3. [workflows.md: Target Orchestrated Supplied-Strategy Workflow](workflows.md#target-orchestrated-supplied-strategy-workflow)
4. [operations.md: Deterministic Workflow Execution](operations.md#deterministic-workflow-execution)
5. [tool_contracts.md: Orchestration Contracts](tool_contracts.md#orchestration-contracts)
6. [agents.md: Approved Decision Boundaries](agents.md#approved-decision-boundaries)
7. [Active capability roadmap: Orchestration](../../plans/research_capability_roadmap.md#orchestration)

## Document Roles

| Document | Use it for | Do not use it for |
| --- | --- | --- |
| [product_state.md](product_state.md) | Current capability, qualification, availability, agent state and product limits. | Detailed schemas or historical delivery sequencing. |
| [architecture.md](architecture.md) | Current package boundaries, authority, persistence, safety, and subsystem designs. | Tool availability or historical refactor sequencing. |
| [agents.md](agents.md) | Agent missions, decision authority, tool allowlists, artifact domains, and handoffs. | Detailed request schemas. |
| [mcp_tools.md](mcp_tools.md) | Registered tool catalog, owners, side effects, and capability gates. | Service internals. |
| [workflows.md](workflows.md) | End-to-end procedures and artifact flow. | Exact field-level contracts. |
| [tool_contracts.md](tool_contracts.md) | Request fields, envelopes, validation, and artifact contracts. | Introductory reading. |
| [operations.md](operations.md) | Startup, environment, Postgres, policy gates, and qualification. | Conceptual domain ownership. |
| [semantic_extraction.md](semantic_extraction.md) | Claim-level methodology evidence and method-card extraction semantics. | Generic strategy execution. |

## Current Product State

The canonical capability, qualification, availability and agent-orchestration baseline is
[product_state.md](product_state.md). It deliberately separates implemented behavior from controlled acceptance and
from agent automation. Do not duplicate its capability matrix in this README.

## Sources Of Truth

When documentation and implementation disagree, inspect these current sources and then correct the documentation:

- Registered MCP tools and capability flags: `src/trader_mcp/constants.py`.
- MCP transport envelopes and side-effect classification: `src/trader_mcp/contracts.py`.
- Agent identities, tool ownership, and allowlists: `src/trader_research/governance/ownership.py`.
- Artifact types and ownership: `src/trader_research/governance/artifacts.py`.
- Public research application surfaces: the `__init__.py` facade in each `trader_research` bounded context.
- Canonical Postgres persistence and projection registration: `src/trader_research/infrastructure/postgres/`.
- Orchestration declarations and persistence services: `src/trader_research/governance/orchestration/`.
- Resumable workflow state: `src/trader_agents/checkpointing/`.
- Fixed workflow compilation and MCP execution: `src/trader_agents/orchestration/`.
- Current capability and qualification baseline: `docs/research_agents/product_state.md`.
- Remaining work and dependencies: `plans/research_capability_roadmap.md`.
