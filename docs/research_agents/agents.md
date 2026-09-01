# Research Agent Definitions

This document describes current agent identities, approved decision boundaries, and tool allowlists. The implementation
source of truth for tool allowlists and decision authorities is `src/trader_research/governance/ownership.py`;
bounded-context artifact authority is registered in `src/trader_research/governance/artifacts.py`.

Ownership definitions do not imply that every named agent has an operational graph. See
[product_state.md](product_state.md#agent-state) for current graph maturity and the
[capability roadmap](../../plans/research_capability_roadmap.md#target-agent-capability-map) for remaining agent work.

This document remains authoritative for the current frozen identities, allowlists, and artifact authority only. The
planning-only model-backed supervisor and specialist responsibilities are defined in
[Agent Designs](../../plans/agent_designs.md). They replace rather than
extend the current agent control plane, and become current here only when implemented.

## Agent Map

| Agent | Mission | Current tool-produced outputs | Current MCP/tool access |
| --- | --- | --- | --- |
| Research Coordinator | Preserve an operator-approved model-backed session boundary and append public evidence-constrained coordination decisions. | Immutable research-session and agent-decision-receipt records; bounded exact reads of canonical specialist evidence. | Support tools plus the registered session, public-decision, and canonical-evidence-read family. The model-backed coordinator loop is not implemented yet. |
| Quant Research Supervisor Agent | Coordinate the frozen deterministic workflows and synthesize specialist-owned evidence. | Immutable strategy/risk/backtest specifications, canonical backtest runs, optimisation plans/runs/trials, tracking projection reports, comparisons, and planned walk-forward runs. Orchestration-domain objective/plan/outcome records are separately produced through its workflow persistence allowlist. | Registered specification/backtest/optimisation/projection `research_*` tools plus `research_register_experiment_workflow` and `research_record_workflow_outcome`. |
| Data Agent | Produce trustworthy bounded market-data manifests and quality evidence. | Symbol discovery reports, dataset manifests, data-quality reports, load result envelopes. | `mcp_health`, `mcp_get_config`, `data_discover_symbols`, `data_get_inventory`, `data_summarize_quality`, `data_create_research_snapshot`, `data_ensure_loaded`. |
| Strategy Engineering Agent | Compare, construct, check, package, and submit inert strategy or risk candidates without efficacy authority. | Compatibility evidence, candidate packages, implementation versions, and independent admission reports. | Read-only implementation catalogue and repository tools; isolated Coding Workspace tools; strategy/risk registration and validation. |
| Experiment Design Agent | Formulate a fair reproducible test over supplied implementations and canonical Data evidence. | Immutable Experiments-owned protocol proposals carrying requested approvals. | `mcp_health`, `mcp_get_config`, `research_create_experiment_protocol_proposal`. |
| Quantitative Methods Agent | Produce auditable deterministic methods, method evidence, diagnostics, and statistical inference artifacts. | Knowledge manifests, methodology candidates, methodology evidence packets, methodology extraction/validation reports, canonical method cards and derived summaries, implementation manifests, validation reports, diagnostics, multiple-testing reports, method packages, optional kernel manifests. | `mcp_health`, `mcp_get_config`, `knowledge_*`, and current `math_*` tools. |
| ML Agent | Coordinate point-in-time feature engineering, fitting, MLflow recording/registry, model evaluation, deployment evidence, predictions, and drift. | Current deployment manifests and validation reports; planned feature/training/run/evaluation/version/promotion/drift artifacts. Runtime prediction events are platform evidence carrying ML lineage. | Registered `ml_create_deployment_manifest` and `ml_validate_deployment`; remaining 39A-G/J tools are planned. |
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
| Data Agent | Is the explicit market-data scope available and fit for the proposed protocol? | Dataset manifests, quality reports and load evidence through Data tools. | Strategy logic, optimisation design or performance conclusions. |
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

## Orchestration Contract Boundary

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

## Specialist Graph Boundary

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

This is a reusable invocation boundary, not a new universal agent. `trader_agents.data_agent` is one production
registration. Its deterministic policy selects `validate_market_data_scope`, optional
`ensure_market_data_available`, and `capture_market_data_evidence`; handlers alone construct MCP arguments. The final
handler resolves both snapshot refs from the canonical store and validates scope, ownership, producer, requester,
actor, status, payload digest and matching dataset identity before returning handoffs. The composition runner invokes
this route when the Coordinator selects an explicit Data task, validates the terminal result and handoffs again, and
stores only a bounded accepted-result receipt. Approval requests remain Coordinator-owned: a specialist reports an
approval prerequisite or a proposed artifact but cannot approve its own assumptions.

`trader_agents.experiment_design_agent` is the second production registration. Its strict task carries a complete
`ExperimentDesignRequest` over exact implementation, manifest, quality and optional optimisation-validation refs. Its
one deterministic policy action calls `research_create_experiment_protocol_proposal`, reloads the canonical
Experiments-owned proposal, verifies task/objective/design/provenance identity and returns a digest-pinned handoff. A
missing local-mutation permission becomes a typed prerequisite. The graph cannot decide approvals, execute the
protocol, write the store directly or retain the protocol payload in checkpoint state.

## Research Composition Boundary

`trader_agents.research_composition` is the operational connector, not a new decision authority. Its immutable request
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
  mutate live trading. Tasks 58-59 remain deferred until task 57, model-backed strategy integration through 39I, and
  robustness tasks 44/46 are proven.

## Current Versus Planned Status

Current registered MCP surfaces include Data Agent tools and canonical Data snapshots; ML deployment creation/validation; Quantitative Methods knowledge/math and optimisation-objective
tools; Supervisor implementation registration, immutable specifications, canonical backtests, grid/random/optional
Optuna optimisation, result lookup, immutable variant execution, tracking projection and workflow record persistence; untouched-holdout Evaluation;
and parameter-optimisation Adversarial planning/judgment. Candidate/stack and loose baseline/portfolio backtest tools are
not registered after the cutover.

ML feature engineering, training, evaluation, registry management, and drift; Hypothesis; broader
Adversarial/Evaluation critique; attribution; recommendation synthesis; and supervisor autonomy remain planned unless
the MCP tool catalog marks them registered. Task 40 remains deferred until the full deterministic ML lifecycle is
proven.

## Identity Checks

Agent display names, allowlists, produced outputs, approved decision authorities and artifact-domain mappings are
executable metadata. Update this document when
`src/trader_research/governance/ownership.py` or `src/trader_research/governance/artifacts.py` changes, and update the
documentation consistency test so every agent remains covered.
