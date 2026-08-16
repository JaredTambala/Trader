# Research Product State

This document is the canonical current-state description of Trader's research product. It explains what the product
can do, how strongly each capability has been qualified, which agent behavior exists today, and which target
capabilities remain open.

It does not define request schemas, repeat historical implementation narratives, or prescribe one linear delivery
sequence. Use the [capability roadmap](../../plans/research_capability_roadmap.md) for remaining work and dependencies.

Last reviewed: 2026-07-27.

## How To Read Capability State

Three independent dimensions describe a capability:

| Dimension | Values | Meaning |
| --- | --- | --- |
| Implementation | `absent`, `partial`, `implemented` | Whether the deterministic product behavior exists. |
| Qualification | `none`, `focused`, `integration`, `controlled` | The strongest evidence run against the implementation. |
| Availability | `unregistered`, `registered`, `gated`, `operator_only`, `deferred` | Whether the behavior is exposed and under what operational policy. |

`Implemented` does not mean autonomously orchestrated. `Registered` does not mean enabled. `Integration` does not mean
the implementation is part of the last controlled release. These distinctions are deliberate.

## Executive State

Trader currently provides a strong deterministic research control plane:

```text
explicit Data Agent scope and quality evidence
  -> content-addressed implementation versions
  -> immutable strategy, risk-stack, and backtest specifications
  -> canonical Postgres backtest evidence
  -> optional provider-neutral parameter optimisation
  -> sealed untouched-holdout execution
  -> independent Evaluation and Adversarial evidence
```

It also provides bounded source ingestion and methodology extraction, plus a newly implemented runtime path for
consuming immutable predictive models in strategies and synchronized-universe backtests.

Trader now has one deterministic orchestration template for the supplied-implementation procedure. An approved
objective/protocol can be compiled and mechanically executed through MCP, checkpointed, resumed and summarized as a
canonical outcome. The principal remaining orchestration gap is bounded planning: the Quant Research Supervisor does
not yet formulate protocols, select the template or resolve prerequisites autonomously. The Data Agent remains the only
specialist with an operational tool-calling graph.

## Product Authority

| Concern | Authority |
| --- | --- |
| Market data, events, portfolio behavior, backtest runtime, risk and broker interfaces | Core `trader` runtime |
| Maintained indicators, signals, strategies, risk managers, feature providers and prediction mappers | `trader_standard` |
| Research implementations, specifications, runs, trials, selections, reviews and deployment evidence | Trader Postgres |
| Source text, evidence units, embeddings and canonical method cards | Trader Postgres knowledge store |
| ML training telemetry, packaged models and registry records | Configured MLflow instance, once the planned training lifecycle exists |
| MCP registration, transport envelopes and coarse policy gates | `trader_mcp` |
| Agent planning, allowed tool use, handoffs and operational checkpoints | `trader_agents` and its configured checkpointer |

Operational graph checkpoints are not research evidence. A workflow may be resumed from a checkpoint, but downstream
claims must still be supported by immutable product artifacts and their bounded-context authority.

ORCH-GOV removed agent identity from canonical artifact authority. `research_artifacts` now records a required
`domain_owner` and `producer_tool`, plus nullable `requested_by` and `actor` provenance. Artifact types are mapped to
Data, Knowledge/Methodology, Experiments, ML, Review or Orchestration. The MCP `agent_owner` envelope field remains a
tool-allowlist/stewardship label and is not persisted as artifact authority. Direct pre-orchestration calls honestly
leave requester/actor null. The ORCH-3 executor supplies the workflow ID and `workflow_executor` actor to every
orchestrated canonical write through a contextual artifact-store boundary.

## Capability Matrix

| Capability | Implementation | Qualification | Availability | Product position |
| --- | --- | --- | --- | --- |
| Data discovery, inventory and quality | implemented | controlled | registered; loading gated | Produces exact dataset manifests, quality reports and bounded load evidence. `data_create_research_snapshot` persists an exact manifest/quality pair for resumable workflows. Calendar-aware equity gap classification remains open. |
| Knowledge source registration and ingestion | implemented | integration | registered | Full-document text ingestion, evidence units, embeddings, lexical/vector retrieval and bounded dereferencing are operational. |
| Methodology extraction and method cards | implemented | integration | registered | Reliable for bounded, locally evidenced methods. Composite book-scale frameworks remain outside the represented model. |
| Implementation admission | implemented | controlled | registered | Handwritten, maintained, AI-produced and method-produced strategy/risk/objective source enters one content-addressed validation path. |
| Strategy and risk specifications | implemented | controlled | registered | Parameters and ordered risk behavior are immutable and separate from data scope. |
| Backtest specifications and execution | implemented | controlled | registered; execution gated | Runs exact Data Agent scope with costs, initial state, risk evidence and canonical Postgres results. |
| Parameter optimisation | implemented | controlled for built-in grid/random | registered; execution gated | Complete trial ledgers, deterministic selection, sealed holdout, optional lazy Optuna and non-authoritative tracking projection. |
| Optimisation Evaluation and Adversarial audit | implemented | controlled | registered | Evaluation judges matching holdout evidence; Adversarial plans and judges immutable optimisation variants. |
| General robustness attacks | partial | focused | partially registered | Optimisation-specific attacks exist. General cost, window, concentration, perturbation and regime attacks remain open. |
| Runtime prediction contracts | implemented | integration | library capability | Point-in-time feature batches, immutable model identity, typed predictions, failure policy and bounded prediction evidence. |
| ML deployment and strategy binding | implemented | integration | registered; model loading gated | Loads a pinned local MLflow pyfunc model, validates parity, maps compatible outputs through strategy policy and supports synchronized-universe backtests. |
| ML feature, training, evaluation and registry lifecycle | absent | none | deferred | MCP cannot yet engineer feature sets, build training datasets, fit models, reconcile runs, evaluate versions or produce immutable registry refs end to end. |
| Prediction monitoring and drift | absent | none | deferred | Prediction events exist, but summarisation, realized-target joining and drift reports do not. |
| Walk-forward optimisation | absent | none | deferred | Provider-neutral optimisation can be reused inside folds, but fold planning, locked OOS execution, stitching and audit are not implemented. |
| Attribution and broad performance critique | partial | focused | partially registered | Backtest and optimisation reports contain substantial measures; general attribution and skeptical evaluation tools remain open. |
| Higher-level orchestration | partial | integration | library executor plus registered persistence tools | One approved supplied-implementation template compiles and executes baseline, optional optimisation, sealed holdout and optimisation-specific review through MCP with checkpoints and canonical outcomes. Bounded coordinator planning and general robustness/review composition remain open. |
| Live or paper runtime mutation by research agents | intentionally absent | not applicable | prohibited | Research agents cannot place orders, mutate brokers, clear halts or deploy into an active runtime. |

## Supported Research Workflows

### Supplied Strategy To Evidence

This is the strongest current end-to-end workflow:

```text
Data Agent manifest and quality report
  -> strategy and risk implementation registration
  -> implementation validation
  -> strategy and ordered risk-stack specifications
  -> backtest specification and validation
  -> canonical multi-asset backtest
  -> result retrieval and comparison
```

The source may be handwritten or produced by an external AI or methodology workflow. Method-card provenance is
optional and cannot weaken validation.

### Parameter Selection And Independent Review

```text
passed selection-region backtest specification
  -> validated closed-input objective
  -> provider-neutral optimisation plan
  -> complete grid, seeded-random or configured Optuna trial ledger
  -> exploratory selected specification
  -> separately executed sealed holdout
  -> Evaluation report
  -> Adversarial attack plan
  -> Supervisor-executed immutable variants
  -> Adversarial report
```

The optimiser proposes parameters but cannot change data identity, implementation identity, costs, holdout boundaries
or fold boundaries to obtain a favorable score.

### Source-Backed Methodology

```text
approved source reference
  -> complete-document ingestion
  -> evidence retrieval and bounded text dereferencing
  -> methodology candidate
  -> target-conditioned evidence packet
  -> cited field extraction and validation
  -> canonical draft
  -> explicit publication
  -> optional implementation producer
  -> normal implementation admission
```

Blocked extraction is valid product output. The system must not invent unsupported detail to force a method card.

### Model-Backed Backtest

The currently implemented portion starts after model and feature artifacts already exist:

```text
immutable model-version ref and passed feature-set evidence
  -> deployment manifest
  -> gated adapter parity validation
  -> strategy implementation with typed prediction requirements
  -> strategy specification with prediction bindings
  -> backtest specification
  -> model-backed per-symbol or universe-snapshot backtest
  -> prediction -> strategy input -> order -> risk -> fill lineage
```

There is no registered MCP-only path producing the prerequisite model and feature artifacts yet.

## Agent State

| Agent | Current operational state | Target state | Main gap |
| --- | --- | --- | --- |
| Data Agent | Tool-calling deterministic and bounded LLM policy graphs exist for discovery, inventory, quality and gated loading. | Reliable specialist subgraph producing accepted Data Agent handoffs for larger research workflows. | Integration into a resumable Supervisor workflow and broader calendar-aware quality. |
| Experiment Design Agent | Decision boundary and typed protocol/approval contracts exist, but no executable identity, graph or protocol writer exists. Experiment-design decisions are currently distributed across operator inputs, Supervisor-allowlisted tools and optimisation contracts. | Formulate an explicit, approval-aware experiment protocol from supplied strategy/risk implementations and Data requirements. | Protocol persistence, specialist graph and deterministic specification compiler. |
| Quantitative Methods Agent | Allowlist, approved decision boundary and deterministic MCP tools exist. No complete specialist graph coordinates them. | Optional source/evidence/methodology and computational-method producer that returns canonical refs and blockers. | Bounded planning and handoff graph; composite-method representation remains deferred. It is not a prerequisite for supplied implementations. |
| Quant Research Supervisor | The legacy request skeleton remains, while a separate ORCH-3 deterministic compiler/executor can run an already approved supplied-implementation protocol through MCP and record a canonical outcome. | Narrow Research Coordinator that selects bounded workflows, resolves prerequisites, requests approvals and reports terminal state without Experiment or Review decision authority. | Bounded template-selection policy, protocol/prerequisite routing and specialist composition; deterministic execution itself is implemented. |
| ML Agent | Ownership and deployment MCP tools exist; no ML Agent graph exists. | Optional producer coordinating point-in-time features, training, evaluation, registry evidence, deployment validation and monitoring for model-backed strategies. | Deterministic ML lifecycle tools must be built before the graph can be useful. |
| Evaluation Agent | Optimisation Evaluation service/tool exists; no Evaluation graph exists. | Determine what the complete data, baseline, selection, holdout, cost, risk and robustness evidence supports. | Broader evaluation tools and specialist graph. |
| Adversarial Agent | Optimisation audit planning and judgment tools exist; no Adversarial graph exists. | Robustness specialist that identifies attacks and reports sensitivity findings without issuing the overall strategy-quality verdict. | General robustness tools and specialist graph. |
| Hypothesis Agent | Legacy identity/allowlist metadata only. | Not required by the current supplied-strategy workflow; reconsider only when it has a decision not represented in the experiment protocol. | No active core-agent work. |

## Target Decision Architecture

Agent boundaries are defined by exclusive research decisions, not by Python package boundaries or by which tools an
identity can call:

| Role | Exclusive question | Must not decide |
| --- | --- | --- |
| Research Coordinator | What approved workflow and prerequisites should happen next? | Experiment parameters, data fitness, robustness findings or strategy quality. |
| Data Agent | Is the explicit market-data scope available and fit for the requested protocol? | Strategy logic, optimisation dimensions or performance conclusions. |
| Experiment Design Agent | What fair reproducible protocol should test the supplied strategy and risk stack? | Execution results, selected winner after the fact or final quality. |
| Robustness Agent | Which assumptions and claims should be attacked, and what sensitivity did the executed variants reveal? | Baseline mutation, variant execution or overall quality verdict. |
| Evaluation Agent | What does the complete evidence support after data, costs, holdout, risk and robustness are considered? | Protocol repair, parameter selection, variant execution or workflow routing. |
| Quantitative Methods Agent | What optional source-backed or computational-method evidence can be produced? | Concrete data scope, backtest execution or quality verdict. |
| ML Agent | What optional model lifecycle and predictive evidence can be produced for a model-backed strategy? | Trading policy, risk approval or final strategy quality. |

Backtest execution, validation, optimisation suggestions, risk processing and workflow step execution are deterministic
services. They are not agents and do not own research decisions.

Canonical evidence follows bounded-context authority:

| Domain owner | Canonical artifacts |
| --- | --- |
| Data | Dataset manifests, quality reports and load evidence. |
| Knowledge/Methodology | Source, evidence, method-card and method-validation artifacts. |
| Experiments | Implementations, validations, specifications, backtests, comparisons, optimisation plans/runs/trials and tracking projections. |
| ML | Feature, training, model-version, deployment and drift artifacts. |
| Review | Attribution, Evaluation, attack-plan and robustness artifacts. |
| Orchestration | Research objectives, workflow plans, approval requests, bounded handoff summaries and workflow outcomes only. |

Artifact provenance must distinguish `domain_owner`, `producer_tool`, `requested_by` and `actor`. An agent may request
or route an artifact without becoming its domain owner.

## Target Orchestration Position

Orchestration is a cross-cutting capability, not a final delivery slice. It can begin over the deterministic tools that
already exist while ML, robustness and review capabilities continue independently.

The target control flow is:

```text
operator research brief with supplied strategy/risk refs
  -> Research Coordinator resolves prerequisites
  -> Data Agent produces scope and quality evidence
  -> deterministic services validate supplied implementations
  -> Experiment Design Agent proposes an experiment protocol
  -> operator approves material assumptions
  -> deterministic compiler creates immutable specifications
  -> workflow executor runs baseline, optimisation and sealed holdout
  -> Robustness Agent declares attacks
  -> workflow executor runs immutable variants
  -> Robustness Agent reports sensitivity findings
  -> Evaluation Agent issues the final research-quality assessment
  -> Research Coordinator returns refs, blockers and permitted next actions
```

The workflow executor is not an agent. It mechanically calls approved MCP tools, records bounded checkpoints, retries
idempotently and stops on blockers. The Research Coordinator must plan in terms of target artifact types and readiness
conditions, not task numbers. It may select among registered workflow templates and bounded alternatives, but it cannot
invent tools, bypass ownership, repair failed evidence with prose, override the approved experiment protocol, or treat
its own conclusion as specialist approval.

### Implemented Contract Baseline

ORCH-1 implements the provider-neutral declaration layer in
`src/trader_research/governance/orchestration/`:

- `ResearchObjective` records the operator's statement, success criteria, constraints, supplied canonical refs,
  requester and actor.
- `ExperimentProtocol` records supplied strategy/risk implementation refs, role-labelled Data requirements, explicit
  costs and initial state, optional provider-neutral optimisation intent, robustness requirements, evaluation and
  falsification questions, and assumption-specific approvals. An `approved` protocol cannot contain a missing,
  requested or rejected material approval; optimisation requires both a selection region and sealed holdout.
- `CapabilityDefinition`, `Prerequisite` and `ArtifactSlot` describe available deterministic actions, their
  policy/configuration requirements, canonical artifact authority and bounded resolution evidence. Research
  capabilities cannot declare broker side effects.
- `WorkflowPlan` validates a capability-and-artifact DAG. Unknown capabilities, undeclared configuration, mismatched
  slot type/owner/cardinality, missing bindings, unknown prerequisites/approvals, dependency cycles and falsely
  `ready` plans fail at construction.
- `WorkflowStepResult` exposes command identity, requester/actor, idempotency key, canonical artifact refs, bounded
  public data, issues and explicit retry classification. It is not a checkpoint or a raw tool-call transcript.

These are immutable JSON-safe contracts, not operational behavior. ORCH-1 does not persist these values, register
capabilities from MCP, compile protocols, execute tools, resume workflows or replace the current lightweight
Supervisor request/handoff skeleton.

ORCH-2 implements the operational resume boundary in `trader_agents.checkpointing`. A ready `WorkflowPlan` compiles
into a LangGraph shell that interrupts once per ordered step and waits for an external `WorkflowStepResult`. Its
checkpoint records only plan identity and digest, cursor, retry count, bounded attempt summaries, canonical artifact
refs, issue summaries and idempotency digests. It excludes complete plans, raw tool payloads, arbitrary
`WorkflowStepResult.public_data`, artifact bodies, prompts, credentials and feature matrices. Exact repeated results
are ignored, reused keys with different content fail, and resuming against a changed plan digest fails.

The maintained Postgres saver is configured independently with `TRADER_AGENTS_CHECKPOINT_DSN`. Its LangGraph tables
are replaceable operational state and are not `research_artifacts`, typed research projections or evidence for any
claim. ORCH-2 contains no MCP calls and creates no canonical workflow outcome.

ORCH-3 implements the fixed `supplied_implementation_to_evidence` compiler and mechanical executor in
`trader_agents.orchestration`. It pins strategy/risk implementation records and Data snapshots by payload hash,
constructs the capability DAG, invokes only registered MCP tools, validates envelope command/owner/side-effect metadata,
and converts each response into an ORCH-2 step result. It executes baseline evidence and, when declared, optimisation,
sealed holdout, Evaluation, Adversarial attack planning, immutable variants and robustness judgment. Payload drift,
disabled runtime gates and terminal tool blockers stop later execution. Accepted steps are not replayed after an
interruption.

`research_register_experiment_workflow` persists the objective, approved protocol and ready plan before execution.
`research_record_workflow_outcome` persists the terminal refs, blockers and next permitted actions. These records have
typed `research_objectives`, `research_experiment_protocols`, `research_workflow_plans` and
`research_workflow_outcomes` Postgres projections. This is an operator/library execution API, not yet an autonomous
Research Coordinator or a generic high-level MCP runner.

## Qualification Baselines

The strongest controlled baseline is the 56/57 implementation, specification, backtest and optimisation release:

- Git tag: `verification-57i-freeze-v6`
- Revision: `3cd5928533bb678cd387955a0efd7dd19f6d046a`
- Acceptance authority: `verification_control.acceptance_records`
- Qualified providers: built-in grid and seeded-random optimisation
- Explicitly not qualified in that release: Optuna and MLflow provider profiles

Runtime prediction and model-backed strategy integration were subsequently implemented in commit `577c774`. They have
focused, broad-regression, real local MLflow and isolated Postgres integration evidence, but they are not part of the
v6 controlled acceptance record. A future qualification task must preserve that distinction.

## Known Product Limits

- Research tools do not place live orders or mutate paper/live sessions.
- Complex source-discovered composite methodologies are not represented faithfully.
- ML training, model evaluation, registry promotion and monitoring are not an end-to-end toolchain.
- General robustness and walk-forward optimisation are not implemented.
- The supplied-implementation orchestration template is executable, but an operator must still provide an approved
  objective/protocol and invoke the compiler/executor; bounded coordinator planning is not implemented.
- Implementation validation is a bounded admission check, not an operating-system sandbox.
- Backtest, holdout and audit evidence can support a research conclusion; none independently grants deployment
  permission.

## Canonical References

- Remaining work and dependency graph: [research_capability_roadmap.md](../../plans/research_capability_roadmap.md)
- Package and authority architecture: [architecture.md](architecture.md)
- Agent identities, decision boundaries and artifact authority: [agents.md](agents.md)
- Callable MCP surface: [mcp_tools.md](mcp_tools.md)
- Supported procedures: [workflows.md](workflows.md)
- Request and artifact contracts: [tool_contracts.md](tool_contracts.md)
- Configuration and qualification: [operations.md](operations.md)
- Historical linear tracker: [deprecated tracker](../../plans/mcp_trading_research_tools_plan.md)
