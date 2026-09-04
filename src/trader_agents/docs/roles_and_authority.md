# Agent Roles And Authority

This document describes current agent identities, approved decision boundaries, and tool allowlists. The implementation
source of truth for tool allowlists and decision authorities is `src/trader_research/governance/ownership.py`;
bounded-context artifact authority is registered in `src/trader_research/governance/artifacts.py`.

Ownership definitions do not imply that every named agent has an operational graph. See
[Product State](../../../docs/product_state.md#agent-state) for current graph maturity and the
[Trader Development Roadmap](https://app.notion.com/p/d1453b7a4da6468babead2a5cda7ef84) for remaining agent work.

This document is authoritative for current identities, allowlists, decision boundaries, and artifact authority. The
accepted model-backed responsibilities are defined in [Agent Designs](../../../plans/agent_designs.md). The first
Research Coordinator, Data Research, and Strategy Engineering loops are implemented on the agentic-build branch, but
they remain an unqualified capability until the Notion roadmap's production gates pass.

## Agent Map

| Agent | Mission | Current tool-produced outputs | Current MCP/tool access |
| --- | --- | --- | --- |
| Research Coordinator | Preserve an operator-approved session, create and revise an evidence-led agenda, delegate bounded work, review every return, and choose the next permitted action. | Immutable research-session and append-only agent-decision-receipt records; bounded exact reads of canonical specialist evidence. | Support tools plus the registered session, public-decision, and canonical-evidence-read family through a role-scoped MCP client. The model-backed loop is implemented but not yet qualified. |
| Quant Research Supervisor Agent | Coordinate the frozen deterministic workflows and synthesize specialist-owned evidence. | Immutable strategy/risk/backtest specifications, canonical backtest runs, optimisation plans/runs/trials, tracking projection reports, comparisons, and planned walk-forward runs. Orchestration-domain objective/plan/outcome records are separately produced through its workflow persistence allowlist. | Registered specification/backtest/optimisation/projection `research_*` tools plus `research_register_experiment_workflow` and `research_record_workflow_outcome`. |
| Data Research Agent | Determine whether the complete approved multi-asset data scope is available and suitable, and remediate only within the approved loading envelope. | Symbol discovery reports, dataset manifests, data-quality reports, load result envelopes, and exact research snapshots. | `mcp_health`, `mcp_get_config`, `data_discover_symbols`, `data_get_inventory`, `data_summarize_quality`, `data_create_research_snapshot`, `data_ensure_loaded` through a dynamic role/phase policy. The model-backed loop is implemented but not yet qualified. |
| Strategy Engineering Agent | Compare, construct, check, package, and submit inert strategy or risk candidates without efficacy authority. | Compatibility evidence, candidate packages, implementation versions, and independent admission reports. | Read-only implementation catalogue and repository tools; isolated Coding Workspace tools; strategy/risk registration and validation. |
| Experiment Design Agent | Formulate a fair reproducible test over supplied implementations and canonical Data evidence. | Immutable Experiments-owned protocol proposals carrying requested approvals. | `mcp_health`, `mcp_get_config`, `research_create_experiment_protocol_proposal`. |
| Quantitative Methods Agent | Produce auditable deterministic methods, method evidence, diagnostics, and statistical inference artifacts. | Knowledge manifests, methodology candidates, methodology evidence packets, methodology extraction/validation reports, canonical method cards and derived summaries, implementation manifests, validation reports, diagnostics, multiple-testing reports, method packages, optional kernel manifests. | `mcp_health`, `mcp_get_config`, `knowledge_*`, and current `math_*` tools. |
| ML Agent | Coordinate point-in-time feature engineering, fitting, MLflow recording/registry, model evaluation, deployment evidence, predictions, and drift. | Current deployment manifests and validation reports; planned feature/training/run/evaluation/version/promotion/drift artifacts. Runtime prediction events are platform evidence carrying ML lineage. | Registered `ml_create_deployment_manifest` and `ml_validate_deployment`; remaining lifecycle tools are planned. |
| Hypothesis Agent | Produce explicit falsifiable strategy hypothesis cards. | Hypothesis cards. | Planned `hypothesis_create_card`. |
| Evaluation Agent | Produce skeptical critique and performance evidence from research artifacts. | Untouched-holdout optimisation reports and planned stitched out-of-sample walk-forward reports. | `evaluation_generate_parameter_optimization_report` plus planned broader critique/walk-forward tooling. |
| Adversarial Agent | Produce robustness and stress-test evidence for strategies and research procedures. | Parameter-optimisation audit plans/reports and planned walk-forward audits. | Registered parameter-optimisation audit tools; broader robustness remains planned. |

The table above describes executable identities and their current tool allowlists. An identity may expose only
deterministic evidence capabilities while its target model loop remains absent. The table does not assign canonical
artifact ownership. For example, Strategy-Engineering-allowlisted tools currently produce Experiment-domain records, while
Quantitative-Methods-allowlisted tools can produce either Knowledge/Methodology records or Experiment-domain objective
implementations. The MCP `agent_owner` label records intended tool stewardship, not artifact authority or actual caller
identity.

## Approved Decision Boundaries

The governance registry approves the smallest set of target roles with distinct research decisions. The executable registry is
`DECISION_AUTHORITIES`; registration there does not imply that a role already has an operational graph.

| Target role | Owns this decision | Produces | Must not own or decide |
| --- | --- | --- | --- |
| Research Coordinator | Which approved workflow and prerequisites should happen next? | Research objectives, workflow plans, approval requests, handoff summaries and workflow outcomes. | Implementations, specifications, runs, trials, robustness findings, Evaluation reports or research-quality verdicts. |
| Data Research Agent | Is the complete approved market-data scope available and fit for the requested research, and can an identified gap be repaired inside the loading envelope? | Dataset manifests, quality reports, load evidence, exact snapshots, and explicit unresolved-scope findings through Data tools. | Strategy logic, optimisation design, performance conclusions, or unapproved scope expansion. |
| Strategy Engineering Agent | Should an accepted build contract use an exact admitted implementation, a bounded adaptation, or new inert source? | Compatibility evidence, candidate packages, and submitted implementation/admission refs. | Quantitative semantics, admission verdicts, experiment design, performance conclusions, deployment or trading. |
| Experiment Design Agent | What fair reproducible protocol should test the supplied strategy/risk set? | Approval-aware experiment-protocol proposals. | Executing experiments, approving assumptions, changing the protocol after results or judging strategy quality. |
| Robustness Agent | Which claims and assumptions should be attacked, and what sensitivity did executed variants reveal? | Immutable attack plans and per-attack robustness findings. | Executing variants, mutating the baseline or issuing the overall strategy-quality verdict. |
| Evaluation Agent | What does the complete evidence support after data, holdout, costs, risk and robustness are considered? | Independent attribution and final research-quality assessment. | Repairing the protocol, selecting parameters, executing variants or routing workflows. |
| Quantitative Methods Agent | What optional source-backed or computational-method evidence can be supplied? | Knowledge, methodology and method-validation artifacts. | Concrete data scope, experiment execution or final quality. |
| ML Agent | What optional model lifecycle and predictive evidence can be supplied? | Feature, training, model-version, deployment and drift artifacts. | Trading policy, risk approval or final strategy quality. |

Quantitative Methods and ML are optional producer agents for the core supplied-implementation workflow. A separate
Hypothesis Agent is deferred until it has a decision that is not already represented by the experiment protocol.

Validators, backtest runners, optimisation engines, risk pipelines, specification compilers and workflow executors are
deterministic services, not agents. They execute approved inputs and produce canonical domain artifacts without making
research-design or quality decisions.

## Canonical Artifact Authority

Agent identity and domain ownership are separate:

| Domain authority | Artifact families |
| --- | --- |
| Data | Dataset, quality and loading evidence. |
| Knowledge/Methodology | Source, evidence, method-card and method-validation evidence. |
| Experiments | Protocol proposals, implementation, validation, specification, backtest, comparison, optimisation and tracking evidence. |
| ML | Feature, training, model, deployment and monitoring evidence. |
| Review | Attribution, Evaluation, attack-plan and robustness evidence. |
| Orchestration | Research objective, workflow plan, approval and outcome records only. |

Every canonical artifact record stores `domain_owner`, `producer_tool`, `requested_by` and `actor`. Domain and producer
are required. Direct pre-orchestration service calls may leave `requested_by` and `actor` null. Orchestration contracts
require both on typed objective, workflow, approval and step-result values. The resume shell retains them in bounded
operational state; the workflow executor propagates the workflow ID and `workflow_executor` actor into canonical writes.
Missing identity is represented as null, never inferred from the MCP allowlist label. Requesting a tool does not transfer
artifact authority.

## Handoff Rules

- Every handoff includes `domain_owner`, `producer_tool`, `requested_by`, `actor`, artifact type, DB artifact URI or
  payload, source inputs, warnings, blockers, and provenance refs.
- Handoff construction checks `domain_owner` against the canonical artifact registry. Producer, requester and actor are
  required for a cross-agent handoff even though they are nullable on a direct canonical store record.
- The Research Coordinator can request more work, reject insufficient evidence, request approval, or mark a path
  blocked.
- The Research Coordinator must not rewrite Experiment, Data, ML, Evaluation or Robustness artifacts.
- The Experiment Design Agent must expose material assumptions for approval and cannot silently invent costs, risk
  limits, search spaces, budgets or holdout boundaries.
- Robustness findings feed Evaluation; the Robustness Agent does not issue the final strategy-quality assessment.
- Promotion to paper trading remains a human-reviewed proposal, not an autonomous action.

## Model-Backed Orchestration Boundary

The current first-slice connection contract is explicit and evidence-led:

- `ResearchSession` fixes the operator, objective, scope, approvals, model profile, agent programs, tool catalogue,
  budgets, and implementation inputs before a graph starts.
- `CoordinatorAgenda` is model-proposed but schema-validated. Its task DAG is rejected when dependencies cycle.
- `SpecialistDelegation` carries only the task objective, typed input, approved scope, program/catalog identities,
  branch/attempt identity, limits, and context refs needed by one specialist.
- Data and Strategy model outputs are strict turn values containing either one proposed tool call or one public
  conclusion. Code policy authorizes every call before role-scoped MCP dispatch.
- `SpecialistReturn` carries bounded findings, issues, canonical evidence refs, usage, lineage, and status. It contains
  no raw messages, prompts, hidden reasoning, secrets, or full tool responses.
- Every return rejoins the single-writer Coordinator. The Coordinator resolves each exact ref through
  `research_read_artifact`, then records an append-only `AgentDecisionReceipt` before revising, revisiting, forking,
  asking, stopping, or concluding.
- The deterministic scheduler admits only dependency-ready tasks with reserved budgets and non-conflicting mutation
  keys. Disjoint Data and catalogue investigation may execute concurrently.
- Bounded PostgreSQL checkpoint state supports resume and public inspection but is never canonical research evidence.

Strategy Engineering remains catalogue-first and outcome-blind. It may reuse an exact admitted implementation or use
the isolated Coding Workspace to author, check, package, register, and submit a candidate for independent admission.
Failed checks or admission can create a bounded new attempt; the agent cannot admit itself or execute generated code
on the host. Data Research may load only within the immutable session scope and approval/cost envelope.

### Frozen Deterministic Contract Boundary (Removed)

The remainder of this subsection documents the frozen deterministic baseline for historical interpretation only. Its
coordinator, specialist shell, composition runner, and workflow executor packages have been removed from this branch.

The implemented orchestration contracts are declarative governance values, not new agents:

- the operator supplies a `ResearchObjective`;
- the Experiment Design Agent persists an immutable `ExperimentProtocolProposal`, but only explicit operator
  `Approval` decisions can produce the matching approved `ExperimentProtocol`;
- the Research Coordinator may select an explicit task through a registered specialist route or choose a registered
  workflow template over typed `Prerequisite` and `ArtifactSlot` values;
- the non-agent resume shell accepts external `WorkflowStepResult` values and cannot make experiment or
  review decisions;
- the non-agent compiler instantiates the one approved supplied-implementation template as a plan, and its executor
  mechanically obtains the step results through registered MCP tools.

Capabilities contain producer-tool names and schema metadata only. They do not contain callables, service instances,
MCP clients or provider objects. Workflow plans reject undeclared capabilities and configuration, so an agent cannot
turn prose into an invented action. The resume shell checkpoints plan identity, cursor, retries, bounded attempt/handoff
summaries and canonical refs through the maintained Postgres LangGraph saver. It does not call MCP or own canonical
evidence. The workflow executor connects that shell to registered tool execution through a closed compiler and
`McpToolClient`.

The Research Coordinator graph normalizes objective, explicit specialist tasks and accepted-result receipts, optional
protocol and optional outcome payloads, then emits one typed `CoordinationDecision`. It selects the first unaccepted
task through a unique registered authority route; draft objectives and proposed protocols request approval; absent
protocols or canonical inputs request typed prerequisites; complete approved inputs select the sole registered template
and return its compiler-produced plan; terminal outcomes are reported without reinterpretation. The decision contract
contains no tool-name, argument or experiment-configuration fields, rejects unknown fields, and is revalidated against
the code-owned route or template catalog before execution. The graph itself calls no MCP tool. The separate composition
runner executes the selected route or workflow and returns its bounded result for the next decision.

### Frozen Specialist Graph Boundary (Removed)

`trader_agents.specialists` defines the shared contract for operational specialist graphs:

- `SpecialistTask` fixes one registered `DecisionAuthority`, objective, canonical input refs, requested output slots,
  permitted side effects, satisfied policy gates, requester and routing actor.
- `SpecialistDecision` can run one registered action, request a typed prerequisite, complete or block. It cannot carry
  a tool name or arguments; action input binds only canonical artifact URIs and output binds only declared task slots.
- `SpecialistActionCatalog` is code owned and scoped to one authority. A registered handler parses the task's bounded
  specialist input into a role-specific typed request before it may call MCP. Registrations must be idempotent and
  declare only configuration dependencies already injected at catalog construction.
- `SpecialistResult` returns canonical `SpecialistHandoff` values, exact task-slot bindings, prerequisites, warnings,
  blockers or errors. Successful handoffs must match authority, producer, requester, actor, artifact type and
  cardinality.
- The shared shell enforces decision/action budgets and retains no raw MCP result, action arguments, prompt,
  scratchpad, credentials or hidden reasoning. An injected checkpointer retains the first task digest and accepted
  action-result digests so exact resume does not repeat accepted work and changed task content fails closed.

This is a reusable invocation boundary, not a new universal agent. The frozen deterministic Data registration selects
`validate_market_data_scope`, optional
`ensure_market_data_available`, and `capture_market_data_evidence`; handlers alone construct MCP arguments. The final
handler resolves both snapshot refs from the canonical store and validates scope, ownership, producer, requester,
actor, status, payload digest and matching dataset identity before returning handoffs. The composition runner invokes
this route when the Coordinator selects an explicit Data task, validates the terminal result and handoffs again, and
stores only a bounded accepted-result receipt. Approval requests remain Coordinator-owned: a specialist reports an
approval prerequisite or a proposed artifact but cannot approve its own assumptions.

The frozen deterministic Experiment Design registration carries a complete
`ExperimentDesignRequest` over exact implementation, manifest, quality and optional optimisation-validation refs. Its
one deterministic policy action calls `research_create_experiment_protocol_proposal`, reloads the canonical
Experiments-owned proposal, verifies task/objective/design/provenance identity and returns a digest-pinned handoff. A
missing local-mutation permission becomes a typed prerequisite. The graph cannot decide approvals, execute the
protocol, write the store directly or retain the protocol payload in checkpoint state.

### Frozen Research Composition Boundary (Removed)

The frozen deterministic composition runner is an operational connector, not a new decision authority. Its immutable request
contains an approved objective and ordered caller-built specialist tasks. It may execute only the exact route and
version selected by the Coordinator, and its default catalog registers Data and Experiment Design. A completed result is accepted only
when task, authority, route, output bindings, provenance and canonical payload digests agree. The approved protocol must
match the accepted proposal design and consume accepted Data refs before the fixed workflow may begin.

Composition, specialist and workflow checkpoints use isolated thread identities. Parent state contains task/result
digests, bounded decisions and result summaries, canonical refs, counters and issues—not full tasks, artifacts, MCP
responses, tool arguments, prompts or hidden reasoning. Exact terminal replay returns saved state. Changed objective,
task, proposal, protocol or canonical evidence fails closed. Missing Quantitative Methods, ML, general Robustness and
final Evaluation routes remain typed prerequisites.

## Methodology Decision Boundary

- The Quantitative Methods Agent decides source registration, retrieval and methodology-evidence actions through its
  allowlisted tools. Those tools produce Knowledge/Methodology-domain records for full-document ingestion, candidates,
  evidence assembly, field extraction, validation, method-card drafts and publishing.
- The Quantitative Methods Agent does not create strategies, risk managers, portfolio backtests, or Evaluation reports.
- Approved method cards may be optional provenance for evidence-required implementation producers. Maintained
  computational implementations whose catalog contracts do not require methodology evidence remain provenance-neutral. The Supervisor does
  not edit card evidence, and generated source still passes normal implementation validation.
- Dataset manifests and quality reports remain Data-domain artifacts produced through Data tools. Method cards must not carry
  symbols, timeframes, date windows, source filters, or load decisions.
- The Evaluation Agent consumes backtest and risk evidence after immutable specifications are validated and executed; it
  does not approve methods or repair missing methodology-field citations.

## ML Lifecycle Decision Boundary

- The Data Agent decides whether explicit raw market-data scope is available and fit. The ML Agent consumes explicit
  Data Agent refs and must not silently widen symbols, dates, timeframes, sources, or row scope.
- Quantitative Methods may produce reusable mathematical feature implementations. The ML Agent decides feature-set
  composition, point-in-time availability rules, target construction, training datasets, folds, fitting, and predictive
  model evidence; resulting canonical records have ML domain authority.
- MLflow owns ML training runs, logged model packages, registered-model versions, tags, and aliases. Generic parameter
  optimisation plans, trials, selections, backtests, and audits remain canonical in Trader. ML-domain Trader artifacts
  reconcile and validate those external records against Data, source, and environment refs.
- The ML Agent may execute only registered, validated, bounded training pipelines through explicitly gated tools.
  Handwritten and AI-produced training code receive the same source-hash, dependency, interface, resource, and safety
  validation. Prompt text is never an executable training input.
- The ML Agent may prepare predictive evaluation, promotion, and deployment evidence, but passed model metrics do not
  establish strategy profitability. Evaluation owns the independent research-quality decision after backtesting.
- Alias mutation requires explicit policy and approval. The ML Agent cannot hot-swap a running model, mutate trading
  runtime configuration, place broker orders, or grant live eligibility.
- The Quant Research Supervisor binds a passed, immutable model deployment ref to a strategy and backtest. Every run
  pins the resolved model version; mutable aliases are not followed inside a run.
- Runtime prediction occurs through core platform prediction contracts and an optional MLflow adapter. The trading hot
  path does not call MCP; the ML Agent consumes persisted prediction events later for monitoring and drift.

## Optimisation And Walk-Forward Decisions

The following split is already enforced for single-region parameter optimisation and is reused by later walk-forward
work:

- Current Supervisor-allowlisted tools produce Experiments-domain provider-neutral plans, canonical trial ledgers,
  selections and immutable variant executions. They can use maintained grid/random engines or a configured optional
  engine through the same protocol.
- Quantitative Methods decides and validates versioned closed-input optimisation objectives; the resulting implementation
  and validation records belong to the Experiments domain.
- Evaluation owns the matching sealed-holdout judgment and cannot change the selected specification; its report has
  Review domain authority.
- Robustness owns attack selection and sensitivity judgment. It does not execute the original optimiser; deterministic
  Experiment services execute requested variants and return immutable refs.
- Tracking sinks own no product evidence. Projection reports are non-authoritative Experiments-domain Trader records.

- Deterministic Experiment services produce the immutable optimisation plan and procedural run. The future Research
  Coordinator routes declared folds,
  candidate parameters/models, child specifications, selections, and out-of-sample backtests without issuing a
  performance or robustness verdict.
- The ML Agent participates only where a fold engineers features, fits a model, evaluates predictions, or registers an
  immutable model version. Generic strategy-parameter optimisation is not an ML Agent artifact.
- Evaluation owns the stitched out-of-sample performance decision and must exclude in-sample/selection returns
  from reported walk-forward performance.
- Robustness owns the independent audit decision over fold boundaries, window lengths, neighboring selections,
  parameter/model stability, costs, concentration, degradation, search budget, and selection bias. It does not run the
  original optimiser or rewrite its selections.
- Walk-forward optimisation cannot promote a strategy/model, assign an MLflow alias, change runtime configuration, or
  mutate live trading. Full walk-forward optimisation remains deferred until prospective experiment execution,
  model-backed strategy integration, and robustness boundaries are proven.

## Current Versus Planned Status

Current registered MCP surfaces include Data Agent tools and canonical Data snapshots; ML deployment creation/validation; Quantitative Methods knowledge/math and optimisation-objective
tools; Supervisor implementation registration, immutable specifications, canonical backtests, grid/random/optional
Optuna optimisation, result lookup, immutable variant execution, tracking projection and workflow record persistence; untouched-holdout Evaluation;
and parameter-optimisation Adversarial planning/judgment. Candidate/stack and loose baseline/portfolio backtest tools are
not registered after the cutover.

The model-backed Coordinator, Data Research, and Strategy Engineering loops are implemented but not controlled.
Focused recovery covers specialist reads, Data mutations, candidate packaging/registration/admission/repair, and
coordinator decision-receipt reconciliation. Explicit owning-operator cancellation is proven across fresh processes,
and bounded failed-admission repair is implemented. A real digest-pinned Docker sandbox, redacted MLflow lifecycle
traces, the no-selection real-model campaign, and four bounded-scale profiles now have executable qualification
entry points. Their controlled runs against one candidate freeze remain active work.
Experiment Design, Knowledge Research, Quantitative Methods, Robustness/WFO, Evaluation, recommendation synthesis, and
ML model-backed loops remain planned or parked unless the
[Trader Development Roadmap](https://app.notion.com/p/d1453b7a4da6468babead2a5cda7ef84) says otherwise.

## Identity Checks

Agent display names, allowlists, produced outputs, approved decision authorities and artifact-domain mappings are
executable metadata. Update this document when
`src/trader_research/governance/ownership.py` or `src/trader_research/governance/artifacts.py` changes, and update the
documentation consistency test so every agent remains covered.
