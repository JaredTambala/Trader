# Research Capability Roadmap

This is the canonical active roadmap for Trader's research product. It tracks remaining capability work as a dependency
graph rather than a presumed linear sequence.

Read [Research Product State](../docs/research_agents/product_state.md) first for the current operational baseline.
Architecture, agent ownership, MCP registration and tool contracts remain canonical in their respective documents.

Last reviewed: 2026-08-18.

## Roadmap Rules

- A work item represents a product capability or qualification outcome, not a chronological slice.
- `Hard dependencies` are required contracts. `Optional inputs` improve a capability but do not block its delivery.
- Workstreams may proceed concurrently when their hard dependencies are satisfied.
- Implementation, qualification and availability are reported independently.
- Completed legacy task IDs remain immutable lineage labels; they are not reused or renumbered.
- `ORCH-*` identifiers are roadmap work-item labels only. Product architecture names stable responsibilities such as
  declaration contracts, resume state, compilation and execution; it never names components after delivery checkpoints.
- A capability is not complete until implementation, active documentation and its declared acceptance evidence agree.
- Git commits/tags and canonical Postgres acceptance records retain detailed execution history. This roadmap does not
  duplicate command transcripts or failed-attempt journals.

## Status Vocabulary

| Field | Values |
| --- | --- |
| Work status | `ready`, `in_progress`, `blocked`, `deferred`, `complete` |
| Implementation | `absent`, `partial`, `implemented` |
| Qualification | `none`, `focused`, `integration`, `controlled` |
| Availability | `unregistered`, `registered`, `gated`, `operator_only`, `deferred` |

## Capability Dependency Graph

```text
DATA ───────────────────────────────┐
IMPLEMENTATION + SPECIFICATIONS ────┼──> EXPERIMENT EXECUTION ──> REVIEW
KNOWLEDGE ── optional provenance ────┘              │
                                                   ├──> ROBUSTNESS ──> WFO CORE
ML FEATURES + TRAINING ──> MODEL VERSION ──> ML DEPLOYMENT ─┘          │
                                                                      └──> WFO ML EXTENSION

ORCHESTRATION FOUNDATION ──> CURRENT WORKFLOW ORCHESTRATION
             │                         │
             └──> SPECIALIST AGENTS ───┴──> MULTI-AGENT SUPERVISION

QUALIFICATION applies independently to every implemented capability frontier.
```

Orchestration depends on stable tool and artifact contracts, not on every future capability being complete. New
specialist capabilities can be added to the capability registry after their deterministic tools are proven.
Orchestration is a cross-cutting capability and may advance in parallel with ML, robustness and review work.

## Accepted Baseline

| ID | Capability | Implementation | Qualification | Availability | Evidence |
| --- | --- | --- | --- | --- | --- |
| BASE-KNOW | Knowledge ingestion and bounded methodology extraction through 33AB | implemented | integration | registered | Controlled source/evidence regressions and canonical Postgres lineage. |
| BASE-IMPL | Knowledge-independent implementation admission through 56A-D | implemented | controlled | registered | Included in `verification-57i-freeze-v6`. |
| BASE-EXP | Strategy, risk-stack and backtest specifications through 57A-C | implemented | controlled | registered; execution gated | Included in `verification-57i-freeze-v6`. |
| BASE-OPT | Provider-neutral optimisation and independent review through 57D-H | implemented | controlled for built-in engines | registered; execution gated | Included in `verification-57i-freeze-v6`; provider profiles remained independently unqualified. |
| BASE-DATA | Data Agent manifests, quality and controlled evidence-graph scope | implemented | controlled | registered; loading gated | Used by the v6 realistic Postgres and MCP qualification graphs. |
| BASE-ARCH | `trader_research` bounded-context cutover through TRR-12 | implemented | controlled | operational | Requalified as part of the v6 baseline. |
| BASE-ML-RUNTIME | Runtime prediction and model-backed strategies through 39H-I | implemented | integration | registered; model loading gated | Commit `577c774`; focused, regression, local MLflow and isolated Postgres evidence. Not in the v6 acceptance record. |

## Active Work Graph

### Orchestration

| ID | Capability | Status | Hard dependencies | Optional inputs | Enables | Acceptance |
| --- | --- | --- | --- | --- | --- | --- |
| ORCH-0 | Product-state and roadmap cutover | complete | None | Existing tracker lineage | All orchestration planning | Legacy tracker deprecated; current-state document, capability graph, links and documentation tests pass. |
| ORCH-GOV | Decision authority and domain ownership redesign | complete | ORCH-0, BASE-ARCH | Current agent/artifact ownership map | ORCH-1 | Canonical records and handoffs separate domain authority, producer tool, requesting workflow and actor; approved decision boundaries are executable governance metadata; old Postgres schema fails closed with no compatibility reader. |
| ORCH-1 | Capability and workflow contracts | complete | ORCH-GOV | ML and robustness target contracts | ORCH-2, ORCH-3, AGENT-1 | Immutable JSON-safe contracts now cover research objectives, experiment protocols, material approvals, capability snapshots, prerequisites, artifact slots, workflow-plan DAGs and bounded step results. Construction rejects unresolved approved protocols, unsafe side-effect classes, invalid authority/cardinality, unknown bindings/configuration, cycles and falsely ready plans without importing service implementations. |
| ORCH-2 | Operational checkpoint and handoff model | complete | ORCH-1 | Postgres LangGraph checkpointer | ORCH-3, recovery | A provider-maintained Postgres LangGraph saver now resumes a bounded coordinator shell across connection lifetimes. Checkpoints retain plan identity/digest, cursor, attempt summaries, canonical artifact refs and issues only; duplicate results are idempotent, conflicts and plan drift fail closed, and public state is explicitly projected. |
| ORCH-3 | Deterministic implementation-to-evidence workflow | complete | ORCH-1, ORCH-2, BASE-DATA, BASE-EXP, BASE-OPT | Knowledge provenance, model deployment refs | ORCH-4 | A fixed supplied-implementation template compiles approved protocols into typed MCP capability DAGs and mechanically executes validation, specifications, baseline, optional optimisation, sealed holdout, Evaluation and Adversarial handoffs. Canonical Data snapshots, objective/protocol/plan/outcome records, payload-hash revalidation, bounded retries, typed stops and resume without accepted-step replay are implemented. |
| ORCH-4 | Bounded Research Coordinator planning policy | complete | ORCH-3 | LLM provider | ORCH-5, ORCH-6 | A deterministic policy and one-node graph select exactly one code-registered workflow or emit typed prerequisite, approval, terminal-report or blocker actions. Strict decisions cannot express tool calls or experiment overrides; missing canonical inputs, unknown/ambiguous templates, identity drift and ownership/content violations fail closed. |
| ORCH-5 | Multi-specialist composition | ready | ORCH-4, AGENT-1, AGENT-DATA | AGENT-DESIGN, AGENT-QUANT, AGENT-ML, REV-3 | Incremental specialist coordination, ORCH-6 | A resumable composition runner accepts explicit bounded specialist tasks, selects only code-registered authority routes, validates results against the original task and canonical store, and continues into registered workflow execution without replay. Acceptance includes a real Data specialist to operator-approved protocol to terminal fixed-workflow path; unavailable specialists remain typed prerequisites. |
| ORCH-6 | Controlled orchestration qualification | blocked | ORCH-3, ORCH-4 | ORCH-5 | Release-ready orchestration | Fresh-process MCP graph, interruption/resume, approval, policy, failure, bounded-scale and operator-isolation evidence. |

The `ORCH-GOV` work item was an architecture and governance gate, not an agent rename exercise. It removed the assumption that an
agent identity owns every artifact produced by tools on its allowlist. Canonical metadata now distinguishes:

```text
domain_owner
producer_tool
requested_by
actor
```

Canonical implementation, specification, backtest, comparison, optimisation and trial artifacts belong to the
Experiments domain. Data artifacts belong to Data; methodology artifacts to Knowledge/Methodology; model artifacts to
ML; evaluation and robustness artifacts to Review. The Research Coordinator owns only bounded workflow objective,
plan, approval and outcome records. The workflow executor owns no research claim and is not an agent.

Implementation evidence: `ResearchArtifactRecord` and Postgres use required `domain_owner`/`producer_tool` plus nullable
`requested_by`/`actor`; every current canonical writer declares its operation; typed handoffs require all four;
`DOMAIN_OWNER_BY_ARTIFACT_TYPE` replaces the agent-owner map; `DECISION_AUTHORITIES` records approved target decisions
and exclusions. MCP `agent_owner` remains transport allowlist metadata. Legacy `research_artifacts(agent_owner)` tables
fail fast and require an explicit destructive reset; there is no migration or compatibility reader.

Implementation evidence for `ORCH-1`: `trader_research.governance.orchestration` is a dependency-light declarative contract
module. `ExperimentProtocol` carries supplied implementation refs, role-labelled Data requirements, costs, initial
state, provider-neutral optimisation intent, robustness requirements, evaluation/falsification questions and
assumption-specific approvals. `WorkflowPlan` pins capability metadata and validates a typed artifact-slot DAG,
prerequisites, policy gates, approvals and configuration keys before execution. `WorkflowStepResult` exposes only
bounded public data, canonical artifact refs, issues and retry classification. The module imports no Data, Experiment,
ML, Review, MCP, agent or service implementation. The declaration-contract work added no executor, checkpointer,
persistence service or MCP tool. Checkpointing and deterministic execution remain separate responsibilities.

Implementation evidence for `ORCH-2`: `trader_agents.checkpointing` compiles a ready `WorkflowPlan` into a deterministic
LangGraph coordinator shell. Each step interrupts with bounded capability metadata and accepts an externally produced
`WorkflowStepResult`; it does not import MCP, Data, Experiment, ML or Review services and does not execute a tool.
Operational state is stored through the maintained `langgraph-checkpoint-postgres` saver configured only by
`TRADER_AGENTS_CHECKPOINT_DSN`. The state contains plan identity/digest, cursor, attempt summaries, canonical artifact
refs, issue summaries and result digests, never raw MCP payloads, complete artifacts, prompts, credentials or feature
matrices. Reopening the saver can resume the same thread; exact duplicate result keys are ignored, conflicting content,
plan drift and invalid output cardinality fail closed. Checkpoint tables are replaceable operational state, not
`research_artifacts` or research evidence.

Implementation evidence for `ORCH-3`: `trader_agents.orchestration` provides one closed
`supplied_implementation_to_evidence` compiler and a non-agent executor over the `McpToolClient` protocol. The compiler
pins exact strategy/risk implementation records, canonical Data manifest/quality refs, optional objective validation,
execution settings, search space and review requirements into a typed capability DAG. The executor calls only registered tools,
validates command/owner/side-effect envelopes, hashes every input/output payload, adapts results into bounded
`WorkflowStepResult` values and drives the resume shell. The new `data_create_research_snapshot` tool makes
inventory/quality evidence resumable; `research_register_experiment_workflow` and
`research_record_workflow_outcome` persist the governance records. Workflow writes are stamped with the workflow ID and
`workflow_executor` actor. Disabled policy, payload drift and terminal tool blockers stop the graph without executing
later nodes; interruption resumes from the next unaccepted step. This is deterministic execution, not an autonomous
planner or a high-level MCP experiment runner.

The Git lineage preserves the same separation: `e3f7d85` completed roadmap item `ORCH-1` with declaration and authority
contracts, `6cbc886` completed `ORCH-2` with the non-executing resume shell, and `28c1d33` completed `ORCH-3` with the
fixed compiler, mechanical MCP executor and canonical workflow persistence. The current product requires the
declaration, checkpoint and execution responsibilities together; none of those commits independently represents an
autonomous Research Coordinator.

Implementation evidence for `ORCH-4`: `trader_agents.research_coordinator` separates strict decision contracts,
code-owned template registration, deterministic lifecycle/readiness policy and JSON-boundary graph wiring. The policy
accepts a typed objective, optional protocol/outcome and injected artifact store; it requests objective/protocol
approval, requests an absent protocol or unresolved canonical artifact, uniquely selects the registered
`supplied_implementation_to_evidence` template, reports a matching terminal outcome or emits a bounded blocker. An
executable decision pins objective, protocol, template version and compiler-produced plan identity but contains no tool
name, arguments or experiment configuration. Recompilation rejects unregistered templates, changed identities and plan
drift. The graph makes no MCP call or canonical write, and specialist invocation remains separate composition work.

#### Planned Research Coordinator-Specialist Composition

The composition layer will connect the existing Coordinator, specialist shell and fixed workflow executor without
turning any of them into a second authority. Its execution plan is:

1. **Land one production specialist first.** Adapt the Data Agent to the shared specialist task/result contract, use
   registered MCP-backed handlers, return canonical snapshot and quality refs, and resume through the operational
   checkpointer. The composition work cannot be accepted using only fake handlers.
2. **Add a code-owned specialist route catalog.** Registrations expose stable authority, supported output types and
   runner version while retaining task builders, graph callables, clients and configuration in code. Unknown,
   unavailable or ambiguous routes fail closed before specialist execution.
3. **Extend the Coordinator with one bounded specialist action.** The decision pins the original task ID, authority and
   task digest. The caller or a role-owned task builder supplies the complete `SpecialistTask`; the Coordinator does
   not infer symbols, windows, costs, experiment parameters or tool arguments from objective prose.
4. **Run and resume the composition loop.** A thin runner invokes the registered specialist, validates the terminal
   `SpecialistResult` against the original task, resolves every handoff from the canonical artifact store, records only
   bounded task/result summaries and canonical refs, and asks the Coordinator for the next action. Completed task and
   workflow digests make exact replay idempotent and conflicting replay terminal.
5. **Reuse the fixed workflow boundary.** When the Coordinator selects the registered workflow, the runner calls the
   existing compiler/executor and feeds the canonical outcome back for terminal reporting. It does not create MCP
   arguments, execute research services directly, rewrite the approved protocol or synthesize specialist verdicts.
6. **Register later specialists independently.** Experiment Design, Quantitative Methods, ML, Robustness and Evaluation
   routes become available only when their own specialist capabilities are complete. Missing registrations remain
   explicit prerequisites; optional producers cannot block a supplied-implementation workflow unless the approved
   objective or protocol requires their artifact type.

Acceptance requires deterministic contract tests for route selection and result validation; failure tests for forged,
missing, conflicting and over-budget results; interruption/resume evidence with no repeated accepted specialist or MCP
mutation; and one integration path that runs the real Data specialist through MCP, pauses for an operator-supplied
approved protocol, executes the existing fixed workflow and records one matching terminal outcome. Graph/checkpoint
state must exclude raw MCP responses, complete artifact payloads, prompts, credentials, model reasoning and tool
arguments. Fresh-process, bounded-scale and release evidence remain controlled qualification work.

### ML Lifecycle

| ID | Capability | Status | Hard dependencies | Optional inputs | Enables | Legacy lineage |
| --- | --- | --- | --- | --- | --- | --- |
| ML-1 | MLflow runtime and mutation policy | ready | BASE-OPT | ORCH-1 | ML-4, ML-6 | 39A |
| ML-2 | Point-in-time feature-set engineering | ready | BASE-DATA, BASE-IMPL | Quant Methods provenance | ML-3, ML-4 | 39B |
| ML-3 | Training datasets and chronological split plans | blocked | ML-2 | Calendar-aware quality | ML-4, WFO-ML | 39C |
| ML-4 | Training pipeline admission, fitting and run reconciliation | blocked | ML-1, ML-3 | Optimisation protocol for model hyperparameters | ML-5 | 39D-E |
| ML-5 | Predictive evaluation and comparison | blocked | ML-4 | Adversarial data attacks | ML-6 | 39F |
| ML-6 | Immutable model versions and promotion evidence | blocked | ML-5 | Human promotion approval | Complete MCP model-to-strategy chain | 39G |
| ML-7 | Prediction monitoring and drift | ready | BASE-ML-RUNTIME | ML-5 for richer realized-target baselines | ML Agent operations | 39J |
| QUAL-ML-RUNTIME | Controlled qualification of 39H-I | ready | BASE-ML-RUNTIME | ML-1 | Controlled ML runtime baseline | New qualification item |

ML-7 can begin from existing prediction events and pre-seeded immutable models. It does not need to wait for Trader to
produce models itself. ML-3 through ML-6 remain the path to an end-to-end MCP-owned model lifecycle.

### Robustness And Review

| ID | Capability | Status | Hard dependencies | Optional inputs | Enables | Legacy lineage |
| --- | --- | --- | --- | --- | --- | --- |
| ROB-1 | General immutable attack and variant contracts | ready | BASE-EXP, BASE-OPT | ML deployment refs | ROB-2, WFO-1 | 44, 46 |
| ROB-2 | Cost, window, concentration, perturbation and regime execution/judgment | blocked | ROB-1 | ML-5, attribution | REV-3, WFO-2, ORCH-5 | 44, 46 |
| REV-1 | General return attribution | ready | BASE-EXP | ROB-1 | REV-2 | 41 |
| REV-2 | Broader skeptical Evaluation | blocked | REV-1 | ROB-2 | REV-3, recommendation | 42 |
| REV-3 | Evaluation and Adversarial specialist graphs | blocked | ORCH-1, REV-2, ROB-2 | ORCH-4 | ORCH-5 | 43, 45 |
| REC-1 | Recommendation and synthesis contracts | blocked | REV-2, ROB-2, ORCH-3 | Hypothesis and ML evidence | Operator-facing research conclusions | 47, 48 |

Evaluation and Robustness decisions must remain independent from execution. Experiment services may execute requested variants,
but it cannot author the specialist verdict or rewrite the baseline.

### Walk-Forward Optimisation

| ID | Capability | Status | Hard dependencies | Optional inputs | Enables | Legacy lineage |
| --- | --- | --- | --- | --- | --- | --- |
| WFO-1 | Strategy walk-forward core | blocked | BASE-OPT, ROB-1 | ML model refs | WFO-2, WFO-ML | 58 |
| WFO-2 | Stitched OOS Evaluation and independent audit | blocked | WFO-1, ROB-2 | Attribution | Audited strategy WFO | 59 |
| WFO-ML | Model-training walk-forward extension | blocked | WFO-1, ML-4, ML-6 | ML-7 | Audited model-aware WFO | 58-59 ML extension |

Generic strategy WFO does not require the complete ML lifecycle. The ML extension does. Both reuse the existing
optimisation protocols rather than creating a provider-specific WFO optimiser.

### Specialist Agents And Operations

| ID | Capability | Status | Hard dependencies | Optional inputs | Enables | Legacy lineage |
| --- | --- | --- | --- | --- | --- | --- |
| AGENT-1 | Specialist graph contract and common policy shell | complete | ORCH-1 | Existing Data Agent graph | AGENT-DATA, AGENT-DESIGN, REV-3, ML Agent, Quant Methods graph | 35, 40, 43, 45 |
| AGENT-DATA | Integrate Data Agent as a resumable specialist | complete | ORCH-2, AGENT-1 | DATA-1 | ORCH-5 | Existing Data Agent tasks |
| AGENT-DESIGN | Experiment protocol proposal and specialist graph | ready | AGENT-1, BASE-IMPL, BASE-DATA, BASE-EXP | AGENT-DATA, BASE-OPT | ORCH-5 | New |
| AGENT-QUANT | Quant Methods specialist graph | deferred | AGENT-1 | KNOW-1 | ORCH-5 | 35 |
| AGENT-ML | ML specialist graph | blocked | AGENT-1, ML-6, ML-7 | ORCH-4 | ORCH-5 | 40 |
| AGENT-HYP | Hypothesis artifact and graph | deferred | ORCH-1 | Knowledge, ML and experiment evidence | ORCH-5 | 37-38 |
| DATA-1 | Calendar-aware market-data quality | ready | BASE-DATA | Exchange calendars | Better equity data evidence | 60 |
| KNOW-1 | Composite methodology representation | deferred | BASE-KNOW | Claim-relationship graph design | Better book-scale methodology extraction | 33AC |

Implementation evidence for the specialist graph contract: `trader_agents.specialists` provides strict task,
decision, action-outcome and terminal-result values; a code-owned action catalog scoped to one registered
`DecisionAuthority`; provider-neutral policy and action-handler protocols; and a bounded LangGraph shell. Policies can
select only registered action IDs and bind canonical input refs to declared capability slots. The shell validates
authority, artifact domains, side-effect permission, policy gates, cardinality, canonical handoff provenance and loop
budgets before accepting a result. Catalog construction also rejects non-idempotent actions and unavailable declared
configuration dependencies. Public and graph state exclude tool arguments, raw MCP responses, prompts,
credentials and hidden reasoning. Data-shaped conformance tests prove completion, prerequisite, blocker, forged-state,
invented-action, policy-gate, input-binding, handoff-authority and loop-limit paths without migrating the existing Data
Agent graph or invoking specialists from the Research Coordinator.

#### Implemented Data Specialist Cutover

The production Data specialist answers one bounded question: whether an explicit market-data scope is available
and fit, with canonical evidence that a later protocol can pin. It returns exactly one `dataset_manifest` and one
matching `data_quality_report` handoff when evidence can be captured, or typed prerequisites, blockers or errors when
it cannot. Symbol discovery, inventory, quality and loading remain deterministic MCP responsibilities.

The implemented responsibility sequence is:

1. **Normalize one Data-specific request.** Add a strict immutable request over the existing `DataRequirement` with
   provider, instrument/bar context, discovery source and optional loading intent. A task factory accepts only an
   approved objective, creates the two required Data output slots, derives a stable task ID and rejects unknown fields,
   unbounded windows, unsupported loading modes and contradictory policy input before any MCP call.
2. **Register three responsibility-named actions.** `validate_market_data_scope` calls symbol discovery and produces no
   artifact; optional `ensure_market_data_available` calls the existing gated loading tool and produces no handoff;
   `capture_market_data_evidence` calls `data_create_research_snapshot` and produces the manifest/quality handoffs.
   The loading action is registered only for modes whose replay idempotency is proven; an unavailable non-idempotent
   loader becomes a capability prerequisite rather than a falsely safe action.
3. **Keep policy separate from transport.** A deterministic Data policy selects only the registered action IDs and
   declared output bindings. Missing local-mutation permission or loading approval produces a typed prerequisite. MCP
   handlers alone build tool arguments, validate command/owner/side-effect envelopes and translate failures. No model
   output may provide a tool name or argument body.
4. **Verify canonical evidence before handoff.** The snapshot handler resolves each returned URI through the same
   injected artifact-store authority and checks artifact type, Data ownership, producer, requester, actor, status,
   scope and matching dataset identity. It adds bounded provenance including the payload digest, then discards the MCP
   response and artifact payload. Incomplete final quality returns a blocked result with the canonical evidence refs
   retained so an operator can inspect the failure.
5. **Make the shared shell operationally resumable.** Add an injected checkpointer option, stable task digest and
   specialist thread configuration to the common shell. Reopening a saver with the same task resumes after accepted
   actions; changed content under the same task ID and conflicting action/result replay fail closed. Checkpoints retain
   only the task boundary, decisions, action summaries, canonical handoffs, bindings, counters and structured issues.
6. **Cut over instead of adding a compatibility path.** Replace the monolithic Data graph module with a focused Data
   specialist package and remove `DataAgentState`, the legacy graph builders, the LLM policy that emitted tool names and
   arguments, raw-envelope checkpoint fields, payload-to-handoff conversion and their obsolete tests/exports. Direct
   Data MCP tools remain available for explicit operator use; no legacy import alias is added.

Implementation evidence: `trader_agents.data_agent` provides the strict request/task factory, deterministic policy,
three responsibility-named action handlers and production catalog/graph assembly. The shared shell accepts an injected
checkpointer, retains stable task and accepted-action digests, and exposes a resume helper that rejects task drift.
Focused tests cover contracts, permission and loading prerequisites, forged command/owner/side-effect envelopes,
missing refs, scope drift, incomplete quality with retained refs, action budgets, exact replay, task conflicts, and
in-process MCP execution for existing and permitted sample-loaded data. The sample path proves no duplicate market rows
or canonical records. A Postgres-marked restart test covers fresh-saver resumption without repeating accepted actions
when the verification database is configured.
Package-boundary checks keep the shared shell free of Data/MCP dependencies and restrict the Data package to public
governance, artifact-store, MCP-client and tool-constant boundaries. The legacy `DataAgentState`, monolithic graph
builders, model-selected tool arguments, raw-envelope fields, payload-to-handoff helper, tests and exports were removed
without compatibility aliases. Direct Data MCP tools remain registered for operator use.

### Final Composition And Performance

| ID | Capability | Status | Hard dependencies | Optional inputs | Enables | Legacy lineage |
| --- | --- | --- | --- | --- | --- | --- |
| RUNNER-1 | High-level experiment runner | blocked | ORCH-3, REV-2, ROB-2 | ORCH-5 | One bounded operator entrypoint | 49 |
| PERF-1 | Compiled-kernel conformance and acceleration | deferred | None | Profiling evidence and method contracts | Runtime optimisation | 50 |

The experiment runner is a composition layer. It must not become a second implementation, backtest, optimisation or
review authority.

## Current Ready Queue

These work items have no unmet hard product dependency:

1. ORCH-5: compose the Research Coordinator, production Data specialist and fixed workflow executor without replay.
2. AGENT-DESIGN: add approval-aware protocol proposal and an Experiment Design specialist graph.
3. ML-1: establish the MLflow runtime and mutation policy.
4. ML-2: implement point-in-time feature-set specifications.
5. ML-7: summarize existing prediction evidence and establish the drift contract.
6. QUAL-ML-RUNTIME: place 39H-I under a new controlled qualification baseline.
7. ROB-1: define general robustness attacks and immutable variants.
8. REV-1: add general return attribution.
9. DATA-1: make quality reports calendar aware.

This is a choice of parallel frontiers, not an instruction to execute the list in order.

## Target Agent Capability Map

| Agent | Target decisions | Required deterministic capabilities | Decision outputs |
| --- | --- | --- | --- |
| Data Agent | Resolve explicit market-data requirements and quality blockers. | DATA and DATA-1 | Dataset manifests, quality reports, loading evidence. |
| Experiment Design Agent | Formulate a fair reproducible protocol for supplied strategy/risk implementations and Data requirements; identify assumptions requiring approval. | BASE-IMPL, BASE-DATA, BASE-EXP, BASE-OPT, ORCH-1 | Experiment-protocol proposals, not implementation/specification/run artifacts. |
| Research Coordinator | Select bounded workflows, resolve prerequisites, request approvals and report terminal state. | ORCH-1 through ORCH-5 | Research objectives, workflow plans, approval requests, handoff summaries and workflow outcomes only. |
| Robustness Agent | Identify assumptions and claims to attack, define immutable variants and report sensitivity findings. | ROB-1, ROB-2, WFO-2 | Attack plans and per-attack robustness findings; no overall strategy-quality verdict. |
| Evaluation Agent | Determine what the complete data, baseline, selection, holdout, cost, risk and robustness evidence supports. | REV-1, REV-2, WFO-2 | Independent evaluation and attribution reports, including the final research-quality assessment. |
| Quantitative Methods Agent | Optionally produce source-backed method and computational evidence. | Knowledge and Methodology; optional KNOW-1 | Source, evidence, method-card and method-validation artifacts. It is not required for supplied implementations. |
| ML Agent | Optionally produce feature, training, model-version, deployment and monitoring evidence for model-backed strategies. | ML-1 through ML-7 | Feature, dataset, training, model, deployment and drift artifacts. |
| Hypothesis role | Optional future producer of explicit hypothesis inputs when it has a decision not already represented by the experiment protocol. | AGENT-HYP | No core agent is required for the present supplied-strategy workflow. |

Backtest runners, validators, optimisation engines, workflow executors and risk pipelines are deterministic services,
not agents. They execute approved inputs and return canonical evidence without making research-design or quality
decisions.

## Historical Lineage Index

The former linear tracker remains available at commit `577c774`:

```bash
git show 577c774:plans/mcp_trading_research_tools_plan.md
```

| Legacy tasks | Resulting capability | Current position |
| --- | --- | --- |
| 1-32 | Initial MCP, Data, Knowledge, method, strategy and backtest foundations | Historical foundation; current contracts supersede several early forms. |
| 33A-33AB | Postgres-first knowledge ingestion and target-bound methodology evidence | Implemented bounded methodology subsystem. |
| 33AC | Composite methodology architecture | Mapped to KNOW-1; deferred. |
| 34-38 | Supervisor, Quant Methods and Hypothesis orchestration | Mapped to ORCH and AGENT workstreams. |
| 39A-G | ML engineering, training, evaluation and registry | Mapped to ML-1 through ML-6. |
| 39H-I | Runtime prediction and strategy integration | Implemented at `577c774`; controlled qualification remains QUAL-ML-RUNTIME. |
| 39J-40 | Prediction monitoring and ML Agent | Mapped to ML-7 and AGENT-ML. |
| 41-48 | Attribution, Evaluation, robustness, recommendation and synthesis | Mapped to REV, ROB and REC workstreams. |
| 49-50 | Experiment runner and acceleration | Mapped to RUNNER-1 and PERF-1. |
| 53-54 and TRR-1 through TRR-12 | Documentation and `trader_research` bounded-context refactor | Implemented and requalified. |
| 56A-D | Knowledge-independent implementation admission | Controlled accepted baseline. |
| 57A-H | Specifications, backtests, optimisation, review and tracking projection | Controlled accepted baseline. |
| 57I-S | Frozen Postgres/MCP qualification and acceptance | Controlled accepted at `verification-57i-freeze-v6`. |
| 58-59 | Walk-forward optimisation and review | Mapped to WFO workstream. |
| 60 | Calendar-aware quality | Mapped to DATA-1. |

Legacy IDs remain valid references in commits, Postgres verification records and historical discussions. New work uses
capability IDs from this roadmap.

## Completion Policy

Before marking an active capability complete:

1. Verify every hard dependency and input artifact contract.
2. Implement through the owning package boundary.
3. Add direct behavior tests before MCP, agent or Postgres integration tests.
4. Update product state, architecture, agent ownership, MCP catalog, contracts and operations only where behavior
   actually changed.
5. Record the strongest qualification level without promoting focused or integration evidence to `controlled`.
6. Review registered tools, artifact ownership, Postgres projections and package boundaries.
7. Record the commit/tag and canonical acceptance refs.
