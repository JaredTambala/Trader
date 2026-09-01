# Research Product State

This document is the canonical current-state description of Trader's research product. It explains what the product
can do, how strongly each capability has been qualified, which agent behavior exists today, and which target
capabilities remain open.

It does not define request schemas, repeat historical implementation narratives, or prescribe one linear delivery
sequence. Use the [capability roadmap](../../plans/research_capability_roadmap.md) for remaining work and dependencies.

Last reviewed: 2026-09-01.

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

Trader now has one deterministic orchestration template for the supplied-implementation procedure and a bounded
Research Coordinator policy over it. The coordinator requests missing objectives, protocols, approvals or canonical
inputs; uniquely selects the registered template when ready; and reports matching terminal outcomes. The compiled
workflow is mechanically executed through MCP, checkpointed, resumed and summarized as a canonical outcome.
The Data Agent is a production graph on the common specialist boundary: it validates a bounded market-data
scope, optionally performs approved replay-safe sample loading, persists an exact snapshot, revalidates both canonical
refs, and resumes without repeating accepted actions. A bounded composition runner now connects explicit Data tasks,
an operational Experiment Design specialist, operator-owned protocol approval and the fixed workflow. Experiment
Design consumes a complete structured request over canonical inputs, persists one immutable proposal, and cannot
approve or execute it. Quantitative Methods, ML, general Robustness and final Evaluation specialist routes remain
unimplemented; there is no separate Knowledge Research route.

None of these components currently invokes a language model, chooses tools from model output, interprets a free-form
brief, or replans from observations. The controlled surface is therefore a frozen deterministic orchestration baseline,
not the target agent system.

## Active Agentic Redesign

The target agent control plane is being redesigned from first principles in
[Agentic Research Orchestration Redesign](../../plans/agentic_orchestration_redesign.md). Deterministic replacement
capabilities are now in progress, but the model-backed runtime has not been implemented.
No compatibility is required with existing `trader_agents` imports, graphs, checkpoints, tasks, policies, catalogs, or
fixed workflow state.

The target system uses a model-backed Research Coordinator supervising context-isolated specialist agents. Models
will own research planning, delegation, tool choice, replanning, and synthesis; deterministic Trader and research
services will continue to own data mutation, code admission, backtests, accounting, optimisation, artifact validation,
policy enforcement, and broker isolation. The real-model framework spike selected LangGraph 1.2.2 with its 3.1.x
Postgres checkpointer. Strict Pydantic schemas validate provider-neutral JSON outputs with one bounded repair; the
development profile is Ollama `qwen3.5:9b` with thinking disabled for control decisions. DSPy remains reserved for
later evaluation-driven program optimization, MCP is the capability boundary, and MLflow covers complex-signal plus
agent trace/evaluation lifecycle without becoming product authority.

Every specialist return will rejoin the coordinator. The coordinator is expected to inspect its canonical evidence and
choose explicitly whether to advance, request revision, revisit an earlier responsibility, create a separately tracked
research branch, request operator authority, conclude, or fail closed. Hyperparameter and asset changes must stay
inside the brief and prospective protocol or create new approved lineage; equivalent low-information loops, exhausted
budgets, evaluation contamination, and decisions outside coordinator authority terminate or interrupt rather than
silently continuing.

The redesign now also has a planning decision for research-backed implementations. A Knowledge Research Agent will use
bounded iterative retrieval over approved, structure-preserved textbook sources to produce a multi-source research
dossier with exact claim-span provenance, conflicts, and gaps. A Quantitative Methods Agent will turn only a validated
dossier into an implementation brief that separates source-backed semantics from Trader engineering choices. Strategy
Engineering will author code from an accepted brief, after which normal admission and experimental evidence still
apply. Model-generated source maps and summaries are navigation aids, never citations. Missing or conflicting material
detail blocks or branches the method rather than being guessed. The complete target is in
[Research-Backed Implementation Architecture](../../plans/agentic_orchestration_redesign.md#research-backed-implementation-architecture).

The design/evaluation charter, 12-case `first-agentic-slice-evaluation-v1` dataset, complete first-slice capability
inventory, and framework/observability decision now precede the active production runtime work. The controlled
`verification-orchestration-v1-freeze` record remains valid evidence only for the frozen deterministic surface.

Design review has accepted the complete Research Coordinator, Data Research, and Strategy Engineering records plus the
shared first-slice pattern review. The measured runtime choice implements those boundaries through native Postgres
checkpoints/interrupts, single-writer state, parallel branches with explicit joins, strict model outputs, role-scoped
MCP, and redacted traces. Later specialist records remain under review or parked. The durable working record is
[Agent Designs](../../plans/agent_designs.md); accepted design and spike evidence still do not make the production
model-backed loop operational.

The Data Research Agent architecture is accepted for the first slice. Its requirements cover multi-asset
composite scope, model-selected use of an evolving role-scoped MCP data catalogue, readiness assessment, and bounded
backfill inside a pre-approved acquisition envelope. Work outside that envelope returns through the coordinator for
operator authority.

The Knowledge Research Agent review is now active in the separate
[Knowledge Research design](../../plans/agent_designs/knowledge_research.md). The existing iterative retrieval,
exact-evidence, cross-source dossier, and fail-closed gap decisions have moved into that build-lifecycle record;
model-selected use of MCP source registration and ingestion inside a session-approved source envelope is now accepted.
External acquisition, licensing, and corpus admission remain operator decisions. The remaining Knowledge architecture
record is not yet accepted.

The Quantitative Methods Agent review has started in its own
[Quantitative Methods design](../../plans/agent_designs/quantitative_methods.md). Its responsibility is now accepted as
one pre-code, outcome-blind translation from validated research dossier to implementation-ready quantitative brief.
Experiment statistics, execution, conformance diagnostics, and result interpretation belong to other agents or
deterministic services. Behaviorally material Trader adaptations belong explicitly in the brief, while non-semantic
software design belongs to Strategy Engineering. The remaining Quantitative Methods architecture record is not yet
accepted.

The Strategy Engineering Agent review has started in its own
[Strategy Engineering design](../../plans/agent_designs/strategy_engineering.md). Isolated model-selected coding through
MCP, content-addressed candidate packaging, and independent admission are established constraints. The acceptable
knowledge-backed and operator-specified entry contracts are both accepted and normalize into a typed build contract.
Every target coding attempt must first use MCP to discover and compare relevant maintained or previously admitted
implementations, then explicitly reuse, adapt, or author anew. The current template lists and
registration/validation tools do not yet provide full versioned implementation ingestion, semantic/typed search,
bounded retrieval, or brief-compatibility evidence. Only exact maintained or admitted versions are eligible for direct
reuse; adaptations and untrusted references create new lineage and pass full admission. The target sandbox is now
bounded as an ephemeral container with a pinned read-only Trader snapshot, separate candidate writes, no general
network or credentials, MCP-only commands, policy-gated pinned dependencies, resource limits, and no repository or
deployment authority. Normal authoring is outcome-blind; only a coordinator-authorized defect investigation may expose
bounded execution traces, and any behavioral change requires a successor build contract and research branch. Concrete
sandbox mechanics remain spike-owned. Admission repair is bounded by candidate-attempt, tool, time, and compute budgets;
every revision needs an actionable finding and material source change, while equivalent failures and policy or contract
problems terminate or escalate.

The Experiment Design Agent review has started in its separate
[Experiment Design design](../../plans/agent_designs/experiment_design.md). Prospective immutable protocols, explicit
material assumptions, operator approval, and successor-protocol lineage remain foundational. Experiment Design owns
the research claim, protected-evidence roles, stage gates, overall budgets, and the authority envelope for later work.
Detailed attack and walk-forward plan design belongs to the Robustness & Walk-Forward Agent, which synthesizes
coordinator-supplied canonical outputs from relevant specialists and records whether its plan is prospective, staged-
prospective, or exploratory. The division between the coordinator's research-question authority and Experiment
Design's hypothesis-formulation authority remains under review. A deterministically validated RWFO plan may advance
inside the approved experiment envelope without another operator decision; material assumptions, scope, protected-data
access, cost, or other out-of-envelope decisions interrupt through the coordinator for explicit authority. RWFO
invokes plan-pinned deterministic attack/fold execution capabilities. There is no target Experiment Execution Agent:
the coordinator invokes a specialized deterministic MCP capability for main-protocol baseline, comparison, and
optimisation execution. Code owns protocol compilation, job scheduling, resource enforcement, retries, reconciliation,
and canonical persistence because these operations carry no independent research judgment.

The selected implementation focus is now the first Coordinator–Data–Strategy agentic slice. It will prove real-model
agenda formation, specialist delegation, multi-asset Data tool use and bounded backfill, implementation-catalogue
comparison, isolated reuse/adapt/author decisions, failed-admission revision, canonical evidence return, interrupts,
restart, and fail-closed behavior. The provisional cutoff is an admitted strategy/risk candidate; Experiment Design and
coordinator-invoked deterministic experiment execution follow only after this slice is qualified.

The ML Signal Research Agent and active ML delivery are intentionally parked. Existing controlled ML runtime artifacts
and behavior remain part of current product state. Roadmap `ready` labels on individual ML capabilities continue to
describe dependency state, not selected priority; no new ML agent or ML capability work blocks the non-ML slice.

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

The governance redesign removed agent identity from canonical artifact authority. `research_artifacts` now records a required
`domain_owner` and `producer_tool`, plus nullable `requested_by` and `actor` provenance. Artifact types are mapped to
Data, Knowledge/Methodology, Experiments, ML, Review or Orchestration. The MCP `agent_owner` envelope field remains a
tool-allowlist/stewardship label and is not persisted as artifact authority. Direct pre-orchestration calls honestly
leave requester/actor null. The deterministic workflow executor supplies the workflow ID and `workflow_executor` actor to every
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
| Higher-level orchestration | implemented for the supplied-implementation/Data/design path | controlled | frozen bounded composition library plus registered persistence tools | The exact deterministic surface is accepted under `controlled_orchestration_v1`, but it has no model-backed planning or tool use and is not the target agent architecture. The clean redesign is still planning-only. |
| Live or paper runtime mutation by research agents | intentionally absent | not applicable | prohibited | Research agents cannot place orders, mutate brokers, clear halts or deploy into an active runtime. |

## Implemented Orchestration At A Glance

The implemented orchestration layer combines a bounded Research Coordinator policy with deterministic library
execution. It is not an unrestricted planner or a single high-level MCP command. It separates these cooperating
responsibilities:

| Stage | Current implementation | Boundary |
| --- | --- | --- |
| Declaration contracts | Immutable objective, protocol, approval, capability, artifact-slot, plan, step-result and outcome contracts in the `protocols` and `workflows` modules under `trader_research.governance.orchestration`. | Validates what may run; performs no I/O, MCP calls or checkpointing. |
| Coordinator policy | Strict `CoordinationDecision`, code-owned `WorkflowTemplateCatalog`, deterministic selection policy and one-node graph in `trader_agents.research_coordinator`. | Selects one explicit unaccepted specialist task, requests prerequisites/approvals, selects one registered template or reports terminal state; it cannot express tool arguments, alter protocol scope, call MCP or execute the selected action. |
| Specialist policy shell | Strict specialist task/decision/result contracts, authority-scoped action catalogs and a checkpoint-capable policy/action graph in `trader_agents.specialists`. | Executes only injected registered handlers after validating canonical bindings, authority, side effects, policy gates, task digests and accepted-action replay; it does not decide specialist policy, construct MCP arguments or compose itself with the Coordinator. |
| Data specialist | Strict `DataSpecialistRequest`, deterministic policy and MCP-backed handlers in `trader_agents.data_agent`. | Validates symbols, optionally loads only approved idempotent sample data, captures one exact snapshot, resolves both refs in the canonical store, and returns handoffs or typed issues. It does not use model-selected tools/arguments or expose provider backfill. |
| Experiment Design specialist | Strict `ExperimentDesignRequest`, deterministic one-action policy and MCP-backed proposal handler in `trader_agents.experiment_design_agent`. | Pins supplied implementations and canonical Data evidence into an immutable Experiments-owned proposal with requested approvals. It cannot infer missing design choices, approve assumptions, execute experiments or redesign after results. |
| Composition runner | Strict request/state contracts, code-owned specialist routes and a one-transition resumable graph in `trader_agents.research_composition`. | Executes selected Data and Experiment Design tasks, validates every returned handoff, pauses for operator approval, enters the fixed workflow and feeds the canonical outcome back. It does not infer tasks, author or approve protocols, build MCP arguments or reinterpret specialist findings. |
| Resume shell | A LangGraph shell in `trader_agents.checkpointing` that orders ready plan steps, validates resumed `WorkflowStepResult` values and stores bounded progress. | Performs no research tool call and creates no canonical evidence. |
| Fixed workflow execution | The versioned `supplied_implementation_to_evidence` compiler and executor in `trader_agents.orchestration`. | Compiles only an already approved objective/protocol and mechanically invokes registered MCP tools; it does not design or independently select the workflow. |

The present call flow is:

```text
library caller supplies one approved objective + explicit Data and Experiment Design tasks
  -> composition runner asks the Research Coordinator for one bounded next action
  -> code-owned Data route runs the resumable specialist graph through MCP
  -> composition validates the manifest/quality handoffs against the task and canonical store
  -> code-owned Experiment Design route persists and returns an immutable proposal
  -> composition resolves the proposal and pauses for its requested approvals
  -> operator applies explicit decisions without changing the design
  -> same approved protocol, matching proposal and Data refs: select the registered workflow
  -> compile_supplied_implementation_workflow(...)
       reads and hashes pinned artifacts; returns a ready WorkflowPlan; writes nothing
  -> execute_compiled_research_workflow(...)
       registers objective/protocol/plan through MCP
       -> asks the resume shell for the pending step
       -> calls that step's registered MCP tool
       -> validates the ToolEnvelope and canonical output refs
       -> gives the resume shell one bounded WorkflowStepResult
       -> repeats or resumes until terminal
       records one canonical WorkflowOutcome through MCP
  -> Research Coordinator reports the matching terminal outcome
```

The specialist shell is a reusable library boundary invoked by composition, not by the Coordinator policy itself. A
`SpecialistTask` names one registered decision authority, approved objective, canonical input refs, requested artifact
slots, permitted side effects and satisfied policy gates. Its policy may run a code-registered action, request a typed
prerequisite, complete, or block. Registered handlers parse specialist-specific input and may call MCP; the shell
accepts only canonical handoffs whose owner, producer, requester, actor, type and slot cardinality match the task.

The Data specialist registers three responsibility-named actions: validate scope, optionally ensure approved sample
data, and capture canonical evidence. The final handler resolves the returned manifest and quality URIs through the
same artifact store used by MCP and validates exact request scope, captured status, Data ownership, producer,
requester, actor, payload hashes and shared dataset identity. Incomplete final evidence returns a blocked result with
both refs retained. Checkpoint state holds only bounded task/decision/action summaries, digests, refs and issues.

The deterministic workflow caller must provide the workflow ID, an `McpToolClient`, the same canonical artifact-store view used by the MCP
tools, and a LangGraph checkpointer. The artifact store holds research evidence and the objective/protocol/plan/outcome
records. The checkpointer holds only replaceable cursor, attempt, issue, digest and canonical-ref summaries.
A deliberate pause creates no outcome. Resuming with the same workflow ID, plan and checkpointer revalidates and reuses
matching canonical registration records, then continues at the next unaccepted step. Terminal replay similarly reuses
the matching canonical outcome.

The fixed template always revalidates the supplied strategy and ordered risk implementations, creates and validates
strategy/risk/backtest specifications, and runs a baseline. If optimisation is declared, it also runs selection,
sealed-holdout and Evaluation steps; non-empty robustness requirements add the Adversarial plan, immutable variants and
robustness report. Policy gates, payload drift, invalid envelopes or terminal blockers stop later steps. Completion
returns canonical refs and permitted next actions, never deployment or trading permission.

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

The current operational column describes the frozen implementation. The target column describes the clean model-backed
replacement, not an extension of the existing graphs.

| Agent | Current operational state | Target state | Main gap |
| --- | --- | --- | --- |
| Data Agent | A deterministic resumable specialist graph validates explicit scope, optionally performs separately approved sample loading, captures an exact canonical snapshot, revalidates both refs and returns manifest/quality handoffs or typed issues. The default composition catalog executes it before protocol approval. | Model-backed Data Research Agent that chooses discovery, quality, ingestion, and remediation actions within a role-scoped MCP surface. | Model policy, context/tool program, broader calendar-aware quality, and safely gated provider acquisition. |
| Experiment Design Agent | A deterministic resumable graph validates a complete design task, calls one registered proposal operation, revalidates the canonical proposal and returns a digest-pinned handoff. A pure helper applies exact operator decisions to produce the unchanged approved or blocked protocol. | Model-backed Experiment Design Agent that converts briefs, candidates, and Data slices into prospective experiment charters with protected-evidence roles, stage gates, specialist authority envelopes, and material approval requests. | Free-form interpretation, staged evidence contracts, scientific replanning, structured agent program, and behavioral evaluation. |
| Knowledge Research Agent | No separate current identity. Full-document source ingestion, hybrid retrieval, bounded evidence dereferencing, exact claim spans, and method artifacts are currently assigned to the deterministic Quantitative Methods surface. | Model-backed source investigator that decomposes evidence obligations, navigates structure, iteratively retrieves and expands approved evidence, reconciles sources, and returns a validated research dossier. | Structure-preserving parsing, source maps/resources, dossier artifacts and validation, role-scoped MCP, model program, and textbook benchmark. |
| Quantitative Methods Agent | Allowlist, approved decision boundary and deterministic MCP tools exist. No complete specialist graph coordinates them. | Pre-code, outcome-blind specialist that converts a passed dossier into a validated implementation brief with source-backed and engineering decisions separated. | Model policy, brief contract/validation, role-scoped MCP composition, and measured multi-source handoff quality. |
| Research Coordinator | A deterministic policy selects the first unaccepted explicit specialist task, requests objective/protocol approvals or unresolved canonical inputs, uniquely selects the registered supplied-implementation template and reports matching terminal outcomes. Composition executes those decisions through the Data and Experiment Design routes. | User-facing model-backed supervisor that creates/revises agendas, delegates context-isolated work, requests approvals, reconciles findings, and synthesizes cited conclusions. | The entire existing control plane is replaced; framework spike, runtime foundation, specialist agents, and behavioral qualification are absent. |
| Strategy Engineering Agent | No current agent. Implementation admission accepts externally supplied code. | Model-backed coding specialist that reuses, authors, tests, revises, and submits strategy/risk candidates from an isolated workspace. | Coding Workspace MCP, sandbox policy, model program, and independent admission loop. |
| ML Agent | Ownership and deployment MCP tools exist; no ML Agent graph exists. | Parked future ML Signal Research Agent coordinating point-in-time features, training, evaluation, MLflow registry evidence, runtime parity, and drift. | Intentionally deferred until the first non-ML agentic slice is qualified; deterministic ML lifecycle tools and model-backed qualification remain future gaps. |
| Evaluation Agent | Optimisation Evaluation service/tool exists; no Evaluation graph exists. | Independent model-backed critic of leakage, selection, costs, robustness, completeness, and alternative explanations. | Broader attribution/evaluation tools, isolated context, agent program, and evidence-grounding evaluations. |
| Adversarial Agent | Optimisation audit planning and judgment tools exist; no Adversarial graph exists. | Robustness & Walk-Forward Agent that synthesizes multi-agent evidence into a staged plan, operates it after approval, inspects sensitivity, and requests successors without issuing the final verdict. | General robustness and WFO tools, canonical multi-agent input contract, staged-plan schema, model policy, and behavioral qualification. |
| Hypothesis Agent | Legacy identity/allowlist metadata only. | No initial standalone agent; hypothesis formation belongs to Experiment Design with Strategy Engineering and Quantitative Methods support. | Reconsider only if isolated divergent ideation produces measured benefit. |

## Frozen Decision Architecture

The following decision map describes the controlled deterministic surface and its original intended extension. It is
retained to explain current authority and artifacts, but it is superseded as a target by
[Agentic Research Orchestration Redesign](../../plans/agentic_orchestration_redesign.md).

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

## Target Orchestration Position (Frozen)

This was the deterministic target used to construct the frozen surface. It is not the active multi-agent design.

The frozen intended control flow was:

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

This diagram explains the frozen decision architecture. The implemented composition runner can execute caller-built tasks
through registered specialist routes, and the default catalog currently provides Data and Experiment Design. It
resolves the canonical proposal, pauses for operator decisions, validates the unchanged approved protocol, selects the registered fixed template and returns its terminal outcome to the
Coordinator. It does not infer a task from objective prose, and unavailable specialist routes remain explicit
prerequisites. The fixed template begins only after the objective and protocol are approved. For an optimising protocol it currently creates
the holdout Evaluation before the optional Adversarial branch, then returns both verdict refs for human review; it does
not run a later agent-authored final Evaluation over robustness evidence.

The workflow executor is not an agent. It mechanically calls approved MCP tools, records bounded checkpoints, retries
idempotently and stops on blockers. The Research Coordinator must plan in terms of target artifact types and readiness
conditions, not task numbers. It may select among registered workflow templates and bounded alternatives, but it cannot
invent tools, bypass ownership, repair failed evidence with prose, override the approved experiment protocol, or treat
its own conclusion as specialist approval.

### Implemented Contract Baseline

The provider-neutral declaration layer is implemented in
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

These are immutable JSON-safe contracts, not operational behavior. The declaration layer does not persist these values,
register capabilities from MCP, compile protocols, execute tools or resume workflows. Operational composition lives in
`trader_agents`; the obsolete request/handoff supervisor graph has been removed.

The operational resume boundary is implemented in `trader_agents.checkpointing`. A ready `WorkflowPlan` compiles
into a LangGraph shell that interrupts once per ordered step and waits for an external `WorkflowStepResult`. Its
checkpoint records only plan identity and digest, cursor, retry count, bounded attempt summaries, canonical artifact
refs, issue summaries and idempotency digests. It excludes complete plans, raw tool payloads, arbitrary
`WorkflowStepResult.public_data`, artifact bodies, prompts, credentials and feature matrices. Exact repeated results
are ignored, reused keys with different content fail, and resuming against a changed plan digest fails.

The maintained Postgres saver is configured independently with `TRADER_AGENTS_CHECKPOINT_DSN`. Its LangGraph tables
are replaceable operational state and are not `research_artifacts`, typed research projections or evidence for any
claim. The resume shell contains no MCP calls and creates no canonical workflow outcome.

The fixed `supplied_implementation_to_evidence` compiler and mechanical executor are implemented in
`trader_agents.orchestration`. It pins strategy/risk implementation records and Data snapshots by payload hash,
constructs the capability DAG, invokes only registered MCP tools, validates envelope command/owner/side-effect metadata,
and converts each response into a bounded step result for the resume shell. It executes baseline evidence and, when declared, optimisation,
sealed holdout, Evaluation, Adversarial attack planning, immutable variants and robustness judgment. Payload drift,
disabled runtime gates and terminal tool blockers stop later execution. Accepted steps are not replayed after an
interruption.

`research_create_experiment_protocol_proposal` persists the immutable proposed design before approval.
`research_register_experiment_workflow` persists the objective, separately approved protocol and ready plan before execution.
`research_record_workflow_outcome` persists the terminal refs, blockers and next permitted actions. These records have
typed `research_experiment_protocol_proposals`, `research_objectives`, `research_experiment_protocols`,
`research_workflow_plans` and `research_workflow_outcomes` Postgres projections. The Research Coordinator selects and compiles this registered
workflow through a Python policy/graph API; execution remains an explicit library call rather than a generic high-level
MCP runner.

`trader_agents.research_composition` provides the bounded higher-level library entrypoint. Its request fixes the exact
objective and explicit specialist tasks; its code-owned route catalog registers Data and Experiment Design. It records
accepted result receipts only after task, route and canonical handoff validation, requires the approved protocol to
match the proposal and consume accepted Data refs, and isolates composition, specialist and workflow checkpoint
threads. Exact replay returns saved terminal state, while changed requests, proposals or protocols fail as identity
drift. Composition itself adds no generic MCP command.

### Agentic redesign capability plane in progress

The first replacement-slice capability tranche is registered, but it is not yet an operational model-backed agent
runtime. Strategy Engineering now has its own governance identity and owns implementation discovery, exact-version
comparison, isolated candidate authoring, and strategy/risk admission tools. The frozen deterministic Supervisor
retains specification, backtest, optimisation, and workflow-record tooling; this ownership split does not retrofit an
LLM into the frozen graph.

The implementation catalogue distinguishes maintained discovery metadata, unadmitted canonical versions, and exact
versions with matching passed admission evidence. Bounded search excludes source, exact retrieval exposes source only
when explicitly requested, and deterministic field comparison supports—but cannot make—the future model's
reuse/adapt/author decision.

The Coding Workspace surface separates a pinned read-only Trader snapshot from candidate writes. It provides bounded
repository search/read, complete-file candidate writes, dependency-policy validation without installation,
allowlisted container checks, inert packaging, and exact cleanup. It is disabled by default and fails closed unless
the workspace gate, dedicated root, pinned revision, pinned image, and container runtime are available. Generated code
is never executed on the host, granted network or credentials, admitted by the coding service, backtested, deployed,
or traded.

The Research Coordinator now has deterministic MCP operations for immutable operator-approved sessions,
content-addressed append-only public decision receipts, exact session/decision resolution, and bounded canonical
artifact reads. Session and receipt records have typed Postgres projections. The contracts pin model, agent-program,
tool-catalog, scope, approval, Python-quality, implementation-input, and budget boundaries; receipts revalidate
canonical evidence and enforce per-branch sequence, cumulative budget, and terminal-stop invariants. They deliberately
exclude prompts, hidden reasoning, credentials, raw messages, and complete tool transcripts.

Production composite Data behavior, model programs, dynamic role catalogues, coordinator/specialist loops,
fresh-process Postgres recovery qualification, the production MLflow trace sink, and repeated real-model evaluation
remain outstanding. The operation-by-operation inventory and versioned evaluation cases are complete; active status
and gates are recorded in the capability roadmap.

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

The current Data/design/fixed-workflow composition surface is controlled under the
`controlled_orchestration_v1` profile:

- Git tag: `verification-orchestration-v1-freeze`
- Revision: `b1f49bd2e8f71bedc4bd66724df756a5935f3eca`
- Acceptance authority: `verification_control.orchestration_acceptance_records`
- Acceptance status: `passed`
- Qualified specialists: Data Agent and Experiment Design Agent under bounded deterministic coordination
- Qualified workflow: `supplied_implementation_to_evidence`, with operator approval authority

All seven responsibility-named phase records passed on that revision with empty blockers, matching freeze identity,
passed isolation and unchanged operator fingerprints. The retained call ledger contains 88 calls: 86 accepted calls
plus one deliberately lost response and its one identical retry with matching argument and result identities. Local
bounded-scale evidence covers the eight-explicit-task limit and a three-symbol/1,000-bar baseline; these measurements
are not universal service-level objectives. The acceptance record explicitly excludes prose-to-task inference,
dynamic specialist-task binding, unavailable specialist routes, optional external providers, deployment, paper
trading and live trading.

## Known Product Limits

- No current `trader_agents` component invokes an LLM or satisfies the active definition of a model-backed agent. The
  replacement capability plane has begun, but the model-backed runtime and qualification remain outstanding.
- Research tools do not place live orders or mutate paper/live sessions.
- Complex source-discovered composite methodologies are not represented faithfully. Current page-text extraction and
  local deterministic span assembly do not provide structure-aware, iterative, multi-source dossier research or an
  implementation-brief handoff; the active design is planning-only.
- ML training, model evaluation, registry promotion and monitoring are not an end-to-end toolchain.
- General robustness and walk-forward optimisation are not implemented.
- The supplied-implementation composition path still requires a caller-built approved objective and explicit specialist
  tasks. An Experiment Design task must reference Data evidence that already exists; composition does not dynamically
  rewrite a later task from a Data result. An operator must still decide every material assumption before execution.
- Implementation validation is a bounded admission check, not an operating-system sandbox.
- Backtest, holdout and audit evidence can support a research conclusion; none independently grants deployment
  permission.

## Canonical References

- Target agent control-plane design: [Agentic Research Orchestration Redesign](../../plans/agentic_orchestration_redesign.md)
- Remaining work and dependency graph: [research_capability_roadmap.md](../../plans/research_capability_roadmap.md)
- Package and authority architecture: [architecture.md](architecture.md)
- Agent identities, decision boundaries and artifact authority: [agents.md](agents.md)
- Callable MCP surface: [mcp_tools.md](mcp_tools.md)
- Supported procedures: [workflows.md](workflows.md)
- Request and artifact contracts: [tool_contracts.md](tool_contracts.md)
- Configuration and qualification: [operations.md](operations.md)
- Historical linear tracker: [deprecated tracker](../../plans/mcp_trading_research_tools_plan.md)
