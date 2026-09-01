# Research Agent Tool Contracts

This document defines the active contract for research-agent tools. The current direction is:

```text
deterministic trader_research services
  -> MCP tools in trader_mcp
  -> LangGraph agent identities in trader_agents
```

MCP is the tool boundary. LangGraph is the agent identity and orchestration layer. Tools produce structured artifacts
under the bounded-context authority declared in [agents.md](agents.md). The MCP `agent_owner` envelope field identifies
the intended tool allowlist/stewardship role; it does not establish canonical artifact ownership or authenticated
caller identity.

Use [mcp_tools.md](mcp_tools.md) for the current registered MCP catalog. This file is the detailed contract appendix for
request fields, envelope shapes, artifact payloads, and validation behavior.

## Functional Status Boundary

Only tools listed as registered in [mcp_tools.md](mcp_tools.md) and returned by `mcp_get_config` are callable. The
implementation/specification cutover is complete: strategy/risk candidates, candidate stacks, loose baseline/portfolio
backtest requests, filesystem run identities, and `evaluation_generate_performance_report` are not registered. Current
execution begins with content-addressed implementation versions and immutable specifications. Provider-neutral
parameter optimisation, explicit tracking projection, sealed-holdout Evaluation, and independent Adversarial audit are
registered. ML deployment/runtime strategy integration is registered; ML feature/training/evaluation/registry and drift
tools plus broader robustness remain planned.

Canonical loaders recompute content-addressed IDs and validation lineage at use time. Optimisation startup rechecks the
pinned base specification, implementation hashes, dataset/quality snapshots, objective source, and provider profile;
payload or configuration drift blocks before a trial executes. Optimisation result reads, tracking projection,
holdout Evaluation, variant execution, and Adversarial audit also reload the sealed plan and recompute the complete
trial ledger, objective values, deterministic selection, and selected child refs before consuming a run.

Knowledge-base and bounded methodology contracts remain implemented and maintained at the 33AB baseline. Composite
methodology expansion is deferred under 33AC.

### MLflow Contract Invariants

Tasks 39H-I implement the runtime/deployment subset; 39A-G/J remain planned. All current and future ML requests and
artifacts obey these rules:

- MLflow tracking and registry locations come from approved server configuration, not request payloads.
- MLflow experiment/run/model refs are reconciled into Trader Postgres artifacts with source, dataset, feature,
  environment, signature, and digest evidence.
- Data Agent manifests own market-data scope. Feature and training tools reject loose hidden scope and inconsistent
  dataset refs.
- Training uses explicit chronological split plans with target horizons, purge/embargo, and point-in-time leakage
  evidence. Random splitting is not the default time-series contract.
- Registered-model aliases are mutable selectors. Every training evaluation, backtest, deployment manifest, trading
  session, prediction, and drift report records an immutable resolved model version.
- Model-version tags and aliases represent lifecycle state; deprecated MLflow model stages are not used.
- Supplied trainer code is an immutable validated artifact. MCP does not execute prompt text, arbitrary notebook state,
  or an unvalidated pickle.
- Runtime inference uses a dependency-neutral core contract and an optional MLflow adapter. It does not call MCP or
  perform per-prediction MLflow tracking writes.
- Model evaluation is ML-owned predictive evidence. Strategy profitability remains Evaluation-owned backtest evidence.
- MLflow writes, training, alias assignment, and runtime deployment have separate policy gates. The ML Agent cannot
  mutate live trading or broker state.

### Deferred Walk-Forward Contract Invariants

Tasks 58-59 add full walk-forward optimisation after the reproducible backtest, ML deployment, and robustness
prerequisites. Chronological validation folds in 39C/39F remain earlier ML correctness contracts.

- `walk_forward_optimization_plan` is immutable and records implementation/deployment refs, base backtest spec, fold
  boundaries, purge/embargo, candidate search space, objective, constraints, costs, seeds, budgets, and stop/resume
  policy before execution.
- Each fold records in-sample/selection and untouched out-of-sample boundaries separately. Selected parameters or model
  version are locked before creating the out-of-sample child specification.
- Every evaluated/rejected candidate, score, exception, seed, selected ref, child specification, backtest, and MLflow
  run/model ref remains visible. Results cannot retain only the winner.
- Out-of-sample results cannot alter the same fold's selection. Procedure-level tuning against aggregate results must be
  disclosed and may require nested walk-forward evidence.
- `walk_forward_evaluation_report` contains stitched out-of-sample evidence only; in-sample/selection returns are not
  reported as walk-forward performance.
- `walk_forward_robustness_report` is independently Adversarial-owned and cannot mutate the optimisation run, model
  alias, deployment, or promotion state.
- The optimisation runner declares the maximum side effect it may perform. An ML-enabled run requires the backtest,
  MLflow-write, and training gates in addition to its general execution gate.

## Control Plane And Execution Plane

Research tooling has two separate configuration planes.

The MCP server is the control plane. It owns only:

- process startup and stdio transport
- server identity, registered tool names, descriptions, and static metadata
- artifact root and server-local policy flags
- capability gates such as `TRADER_MCP_ALLOW_DATA_LOADING`

The tool/runtime layer is the execution plane. It owns only:

- typed tool requests and deterministic service contracts
- injected dependencies such as event stores, catalog providers, runners, and policies
- trader runtime YAML used to build execution dependencies
- runtime dotenv values used by that YAML, such as Postgres and Alpaca credentials

These planes must remain one-way and lazy:

- The MCP server must be able to start, list tools, and answer `mcp_health` / `mcp_get_config` without a valid trader
  YAML, broker credentials, database connection, or backtest runtime.
- A broken execution-plane config must fail inside the affected tool call as a structured envelope. It must not prevent
  MCP server startup or tool registration.
- Execution services in `trader_research` must not read `local.env`, inspect MCP transport details, depend on MCP client
  identity, or branch on which process called them.
- MCP adapters may translate JSON-native tool inputs into typed requests and inject dependencies, but deterministic
  services must know only their request objects, dependency interfaces, and explicit runtime policy.
- Runtime `.env` files are for execution-plane YAML expansion only. They are loaded lazily before building the trader
  config for a tool, never as a prerequisite for MCP server startup.
- Duplicating values across env files is acceptable when those values serve different planes. Avoid "DRY" env loading
  that couples MCP process startup to execution runtime secrets, broker settings, database settings, or script defaults.

## Envelope

Every MCP tool returns a stable envelope:

```json
{
  "ok": true,
  "command": "data_get_inventory",
  "agent_owner": "Data Agent",
  "side_effect": "read_only",
  "schema_version": "1",
  "generated_at": "2026-05-26T12:00:00+00:00",
  "data": {},
  "artifacts": {},
  "warnings": [],
  "errors": []
}
```

Fields:

- `ok`: command success.
- `command`: stable MCP tool identifier.
- `agent_owner`: intended agent allowlist/stewardship label for this tool. It is transport metadata, not artifact
  authority or authenticated caller identity.
- `side_effect`: declared side-effect class.
- `schema_version`: envelope schema version.
- `generated_at`: UTC timestamp.
- `data`: machine-readable result.
- `artifacts`: generated or consumed artifact references.
- `warnings`: non-fatal issues.
- `errors`: structured fatal errors when `ok=false`.

Canonical MCP research artifact refs use `research://postgres/{artifact_type}/{artifact_id}`. New implementation,
specification, backtest, optimisation, Evaluation, and Adversarial services require the structured store and have no
filesystem authority or fallback. Canonical `research_artifacts` rows use required `domain_owner` and `producer_tool`
columns plus nullable `requested_by` and `actor`. Direct calls leave unavailable requester/actor provenance null;
orchestration values require both fields, the resume shell retains them in checkpoint state, and the workflow executor
propagates the workflow ID and `workflow_executor` actor into orchestrated calls.

`SpecialistHandoff` is a separate governance contract. It requires non-empty `domain_owner`, `producer_tool`,
`requested_by` and `actor`, validates domain authority against the artifact type, and carries either a canonical
artifact reference/payload together with source request, warnings, blockers and provenance refs. It has no
`agent_owner` field and cannot transfer authority to the coordinator. The reusable specialist graph accepts only the
canonical-URI form as an output because payload-only handoffs cannot safely satisfy or resume a requested artifact
slot.

## Orchestration Contracts

The declaration contracts are transport-neutral. They define immutable JSON-safe values used before and after
deterministic tool calls:

| Contract | Purpose | Fail-closed checks |
| --- | --- | --- |
| `ResearchObjective` | Operator outcome, success criteria, constraints and supplied refs. | Requires stable identity plus explicit requester and actor. |
| `ExperimentDesignRequest` | Complete structured strategy/risk, Data, cost, runtime, robustness, evaluation and approval-routing choices. | Rejects missing or unknown fields, implicit costs, unbounded runs and invalid existing protocol shapes before any tool call. |
| `ExperimentProtocolProposal` | Immutable Experiments-owned proposal evidence over exact canonical inputs. | Pins task/objective/design identity, payload-hashed refs and one requested approval per material assumption; it can never carry an approved lifecycle. |
| `ExperimentProtocol` | Fair test design over supplied implementation and Data requirements. | Approved means every material assumption has an explicit approved decision; optimisation requires selection plus sealed holdout. |
| `CapabilityDefinition` | Versioned declarative action metadata. | Restricts side effects to research-safe classes and declares exact artifact slots, policy gates and configuration keys. |
| `Prerequisite` | Required artifact, capability, policy or approval condition. | Resolution evidence and blockers must agree with status. |
| `ArtifactSlot` | Typed input/output requirement or bounded resolved ref set. | Artifact type, domain owner, cardinality, refs and status must agree. |
| `WorkflowPlan` | Capability DAG selected from a bounded template. | Rejects unknown steps, bindings, configuration, prerequisites, approvals, cycles and false readiness. |
| `WorkflowStepResult` | Public result from one executor attempt. | Carries only canonical refs, bounded public data, issues, identity, idempotency and retry classification. |
| `Approval` | Operator decision over one material assumption. | Requested records cannot contain decisions; approved/rejected records require decision actor and rationale. |

These contracts do not load artifacts, call services, write Postgres, invoke MCP or hold LangGraph checkpoint state.
Existing MCP `ToolEnvelope` remains the transport result. The workflow executor adapts a validated envelope into a
`WorkflowStepResult`; it does not persist arbitrary raw payloads or hidden model reasoning.

### Model-Backed Session Evidence

The replacement slice uses two canonical public artifact contracts. The model runtime is implemented, while these
MCP contracts remain deterministic evidence boundaries rather than model execution operations:

| Contract | Purpose | Fail-closed checks |
| --- | --- | --- |
| `ResearchSession` | Freeze the operator-approved objective, success definition, approval and scope envelopes, one implementation specification or exact ref, Python quality guide, model/program/tool-catalog identities, and hard budget. | Rejects incomplete identities, duplicate programs, invalid JSON boundaries, invalid budgets, and missing or competing implementation inputs. Exact replay is idempotent; changed content under the same ID is a conflict. |
| `AgentDecisionReceipt` | Preserve one content-addressed public coordinator decision at an accepted branch boundary. | Requires the owning session, an admitted program and pinned model, exact next sequence, non-decreasing cumulative usage within budget, resolvable canonical evidence, and no append after a terminal receipt. |

`research_create_agent_session` and `research_record_agent_decision` are canonical local mutations. Their corresponding
get operations resolve and revalidate exact records. `research_read_artifact` is a read-only, type-pinned,
domain-owner-checked dereference with a caller-selected payload byte bound capped at 256,000 bytes. These tools do not
authorize a requested side effect, dispatch work, expose raw SQL, or turn prose into authority.

Session and receipt projections live in `research_agent_sessions` and `research_agent_decision_receipts` alongside the
canonical `research_artifacts` rows. Receipts retain public summaries, blockers, next actions, evidence refs, branch and
attempt identity, program/model pins, and cumulative budget use. Prompts, hidden reasoning, credentials, raw messages,
and complete tool transcripts are deliberately excluded.

### First-Slice Capability And Trust-Boundary Inventory

This is the reviewed operational inventory for the Research Coordinator, Data Research, and Strategy Engineering
slice. `Session` below means that the runtime must expose the operation through the admitted role catalogue and apply
the session's scope, side-effect, mutation, and budget policy before the MCP call. MCP registration and an
`agent_owner` label alone do not authenticate that caller or grant approval.

| Operation | Role, side effect, and approval | Idempotency and recovery | Public result, fail-closed errors, and qualification fixture |
| --- | --- | --- | --- |
| `mcp_health` | All roles; read-only; session catalogue only. | Safe to repeat after restart. | Bounded server/tool health; transport/schema failure; every MCP scenario. |
| `mcp_get_config` | All roles; read-only; session catalogue only. | Safe to repeat; configuration identity must be rechecked on resume. | Capability flags and tool metadata; malformed or drifted catalogue blocks; `crash_and_lost_response`. |
| `research_create_agent_session` | Coordinator; canonical local mutation; operator-approved payload required. | Same ID/content is an exact replay; conflicting content fails. | Session ref and pinned authority/budget identities; validation/store conflict; every end-to-end scenario. |
| `research_get_agent_session` | Coordinator; read-only; exact session ID/ref. | Safe to repeat and required after restart. | Revalidated session and ref; missing/drifted record; `crash_and_lost_response`. |
| `research_record_agent_decision` | Coordinator; canonical local mutation; admitted program/model and remaining budget required. | Content-addressed replay is safe; sequence must append exactly, counters cannot decrease, and terminal branches cannot append. | Public decision receipt and ref; evidence, sequence, identity, budget, or terminal conflict; `low_information_loop`, `crash_and_lost_response`. |
| `research_get_agent_decision` | Coordinator; read-only; exact receipt ID/ref. | Safe to repeat and required when reconciling a lost response. | Revalidated public receipt; missing or invalid record; `crash_and_lost_response`. |
| `research_read_artifact` | Coordinator and state-narrowed specialist readers; read-only; exact expected type/ref. | Safe to repeat; owner, type, hash, and byte bound are revalidated. | Bounded payload plus governance metadata; type/owner/size/ref failure; all evidence-review scenarios. |
| `data_discover_symbols` | Data Research; read-only; approved provider/source discovery envelope. | Safe to repeat against the same catalogue identity. | Bounded symbol/coverage candidates; policy, provider, configuration, or pagination failure; `out_of_envelope_acquisition`. |
| `data_get_inventory` | Data Research; read-only; exact composite scope. | Safe to repeat; post-mutation reads must use the unchanged scope. | Dataset-manifest payload; runtime/config/scope failure; `exact_reuse`, `unfit_requested_scope`. |
| `data_summarize_quality` | Data Research; read-only; exact composite scope. | Safe to repeat; quality generation is rechecked after loading. | Quality obligations, gaps, and completeness; runtime/config/scope failure; `exact_reuse`, `unfit_requested_scope`. |
| `data_ensure_loaded` | Data Research; local mutation only for an approved acquisition envelope and enabled loading gate. | Inspect mode is replay-safe. Sample loading requires an accepted transition identity and post-load revalidation; lost-response mutation qualification remains mandatory. | Load/plan evidence plus refreshed Data payloads; gate/scope/provider/cost/runtime failure; `bounded_backfill_and_adaptation`, `out_of_envelope_acquisition`, `crash_and_lost_response`. |
| `data_create_research_snapshot` | Data Research; canonical local mutation; exact requester/actor and store required. | Content-derived matching snapshot records replay exactly; drift conflicts. | Manifest and quality refs for one scope; authority/store/scope mismatch; `exact_reuse`, `bounded_backfill_and_adaptation`. |
| `research_list_strategy_templates` | Strategy Engineering; read-only metadata tier. | Safe to repeat against the pinned code revision/tool catalogue. | Maintained strategy summaries; never direct-reuse evidence; `exact_reuse`, `new_authorship_and_repair`. |
| `research_list_risk_manager_templates` | Strategy Engineering; read-only metadata tier. | Safe to repeat against the pinned code revision/tool catalogue. | Maintained risk summaries; never direct-reuse evidence; risk-build variants of `exact_reuse`. |
| `research_search_implementations` | Strategy Engineering; read-only canonical/catalogue query; store required. | Stable request and result refs produce a reproducible catalogue ID. | Ranked source-free rows, trust tier, and admission refs; store/query failure; `exact_reuse`, `new_authorship_and_repair`. |
| `research_get_implementation` | Strategy Engineering; read-only exact-version resolution; source inclusion is separately narrowed. | Safe to repeat; exact source/admission hashes are revalidated. | One version, trust tier, source when permitted, and matching admission ref; missing/drifted version; `exact_reuse`, `bounded_backfill_and_adaptation`. |
| `research_compare_implementation` | Strategy Engineering; read-only field comparison over one exact build contract/version. | Content-derived comparison ID makes exact replay stable. | Match/difference/unknown rows and direct-reuse eligibility, never semantic equivalence or efficacy; invalid ref/contract; `exact_reuse`, `bounded_backfill_and_adaptation`. |
| `coding_create_workspace` | Strategy Engineering; local mutation; workspace gate, pinned repository/image, candidate attempt, and build contract required. | Exact attempt/contract/revision reopens the workspace; conflicting manifest fails. | Workspace identity and public isolation policy; disabled policy/path/identity failure; `new_authorship_and_repair`, `crash_and_lost_response`. |
| `coding_get_workspace` | Strategy Engineering; read-only exact workspace. | Safe to repeat while the workspace is active. | Status, bounded candidate file list, and policy; missing/destroyed/invalid workspace; all authorship scenarios. |
| `coding_search_repository` | Strategy Engineering; read-only pinned-revision search within approved roots. | Safe to repeat; revision and bounded matches are returned. | Paths, lines, excerpts, and revision; denied root/query/size/encoding failure; `malicious_content`, `new_authorship_and_repair`. |
| `coding_read_repository_file` | Strategy Engineering; read-only approved text file. | Safe to repeat; returns exact content hash and revision. | Bounded content and hash; traversal/suffix/size/encoding failure; `malicious_content`, `new_authorship_and_repair`. |
| `coding_write_candidate_file` | Strategy Engineering; local workspace mutation; active exact attempt and file/total byte budgets required. The trusted runtime supplies a deterministic `operation_id`; direct callers may omit it and receive a content-derived identity. | A source-free prepared/accepted operation receipt binds operation, request, content, path, and result hashes. Exact replay returns the accepted result; reuse of an operation identity with different content fails closed. | Candidate path, hash, bytes, workspace use, and `idempotent_replay`; operation conflict plus traversal/suffix/size/inactive-workspace failure; `new_authorship_and_repair`, `crash_and_lost_response`. |
| `coding_read_candidate_file` | Strategy Engineering; read-only active workspace file. | Safe to repeat and hash-checked before package/admission. | Bounded content and hash; missing/traversal/size/inactive-workspace failure; `malicious_content`, `new_authorship_and_repair`. |
| `coding_resolve_dependencies` | Strategy Engineering; read-only policy validation; no installation or network authority. | Safe to repeat against the pinned container policy. | Approved preinstalled pins/image; denied or unpinned dependency; `irreparable_admission`, `malicious_content`. |
| `coding_run_check` | Strategy Engineering; isolated local execution; active workspace, allowlisted check, pinned container, and resource budget required. | Repeatable only for the same workspace snapshot/check identity; every attempt remains public lineage. | Exit/timeout/bounded output evidence; missing OCI runtime, non-zero, timeout, or policy denial; `new_authorship_and_repair`, `irreparable_admission`. |
| `coding_package_candidate` | Strategy Engineering; read-only inert packaging; exact active workspace/source required. | Content-addressed package ID is stable for identical files. | Exact source, hashes, file manifest, and package ID; syntax/path/size failure; all adaptation/authorship scenarios. |
| `coding_destroy_workspace` | Strategy Engineering runtime cleanup; irreversible local mutation after package acceptance or terminal failure. | A source-free `destroying` tombstone is written before exact deletion and advanced to `destroyed`; exact retries return the prior success with `idempotent_replay`. A destroyed attempt cannot be reopened. | Destroyed identity, non-recoverable status, and replay flag; missing/path/OS failure; `crash_and_lost_response`, `irreparable_admission`. |
| `research_register_strategy_implementation` | Strategy Engineering caller, Experiments authority; canonical local mutation; accepted package/build lineage and mutation budget required. | Content-addressed exact replay; changed source creates a new version. | Strategy implementation ref; schema/source/store conflict; adaptation/authorship scenarios. |
| `research_validate_strategy_implementation` | Independent deterministic admission called by Strategy Engineering; canonical local mutation; exact version required. | Exact implementation/source/fixture validation replays to the same report identity. | Passed/failed admission report and actionable findings; source/runtime/contract failure; `exact_reuse`, `new_authorship_and_repair`, `irreparable_admission`. |
| `research_register_risk_manager_implementation` | Strategy Engineering caller, Experiments authority; canonical local mutation; accepted package/build lineage and mutation budget required. | Content-addressed exact replay; changed source creates a new version. | Risk implementation ref; schema/source/store conflict; risk-build variants. |
| `research_validate_risk_manager_implementation` | Independent deterministic admission called by Strategy Engineering; canonical local mutation; exact version required. | Exact implementation/source/fixture validation replays to the same report identity. | Passed/failed admission report and actionable findings; source/runtime/contract failure; risk-build variants. |

The versioned fixture `tests/fixtures/agentic_slice_scenarios.json` is the qualification source for the named cases in
the final column. The inventory intentionally exposes judgment-sized operations: deterministic services still own
mutation and admission, while the models retain the meaningful choices about investigation, comparison, authorship,
revision, and evidence sufficiency.

### Model-Backed Coordination And Specialist Contracts

`CoordinatorAgenda` is the strict model-proposed task DAG. `AgendaTaskProposal` fixes task identity, specialist role,
objective, dependencies, bounded input, mutation key, and resource estimates; construction rejects duplicate tasks and
cycles. A deterministic scheduler selects only dependency-ready tasks, reserves budget before dispatch, and prevents
conflicting mutation keys from running concurrently.

`SpecialistDelegation` fixes session, task, branch, attempt, program, model, tool-catalogue, scope, approval, input,
context refs, and per-invocation limits. `DataAgentTurn` and `StrategyAgentTurn` contain exactly one proposed MCP call or
one terminal conclusion. Policy validates role, phase, tool schema, scope, requester/actor identity, mutation lifecycle,
loading/coding approvals, candidate package/admission lineage, loops, and remaining budget before dispatch.

`SpecialistReturn` contains status, findings, issues, exact canonical evidence refs, bounded usage, lineage, and a
content digest. Every return rejoins the Coordinator. `CoordinatorDecision` then selects `advance`, `revise`,
`revisit`, `fork`, `ask_operator`, `conclude`, or `stop`, with action-specific fields and cited evidence. Code verifies
those refs through `research_read_artifact` and appends an `AgentDecisionReceipt` before applying the decision.
Unknown fields, contradictory action payloads, unverified evidence, exhausted budget, duplicate low-information work,
and out-of-authority mutations fail closed.

### Frozen Research Coordination Decision Contract (Removed)

`CoordinationDecision` is the complete public output of one Research Coordinator policy pass. Its action is one of
`execute_registered_specialist_task`, `execute_registered_workflow`, `request_prerequisite`, `request_approval`,
`report_terminal_state` or `block`. Specialist execution pins task ID, authority, task digest and route version.
Workflow execution pins objective ID, protocol ID, registered template ID/version and deterministic plan ID. Other
actions carry only typed `Prerequisite` values, canonical outcome identity or bounded `ResearchIssue` blockers. Fields
for these actions are mutually exclusive.

The decision schema deliberately has no tool name, tool arguments, symbols, windows, costs, search dimensions or
protocol payload. Unknown fields are rejected during parsing. Template identity is resolved only through the code-owned
`WorkflowTemplateCatalog`; an execution decision transported across a boundary must recompile from the exact objective,
protocol and canonical inputs to the same plan ID before the executor may consume it. Coordination decisions and graph
state are operational values, not new canonical artifacts or hidden planner transcripts.

### Frozen Specialist Task And Result Contracts (Removed)

The shared specialist graph boundary adds no MCP tool and does not change `ToolEnvelope`. Its public values are:

| Contract | Purpose | Fail-closed checks |
| --- | --- | --- |
| `SpecialistTask` | Address one objective and bounded specialist input to a registered decision authority. | Requires requested output slots within that authority, canonical input refs, explicit requester/actor, permitted side effects, satisfied policy gates, bounded JSON input and no pre-resolved output. |
| `SpecialistDecision` | Select one registered action, request a prerequisite, complete or block. | Rejects unknown fields, tool names/arguments, mismatched task/authority, undeclared canonical input bindings and undeclared output-slot bindings. |
| `SpecialistActionOutcome` | Return declared canonical handoffs and bounded issues from a registered handler. | Exact action identity, output declarations, status/issues, producer, owner, requester, actor, URI and cardinality must agree. |
| `SpecialistResult` | Return terminal handoffs, task-slot bindings, prerequisites, blockers or errors. | Every handoff binds exactly once to a requested compatible slot; terminal status and issues cannot contradict each other. |

`SpecialistActionCatalog` contains code-owned `CapabilityDefinition` and handler pairs for exactly one
`DecisionAuthority`. A handler is the only component allowed to interpret `specialist_input`; it must normalize that
boundary into a role-specific typed request before calling MCP or another injected adapter. Policy output cannot add a
handler, tool name, argument body, side-effect class or authority through graph state. The shell persists no raw
handler response. Callers may inject a LangGraph checkpointer; the shell retains the first task digest, accepted action
summaries and their digests, canonical handoffs, slot bindings, counters and structured issues. Exact terminal resume
does not repeat accepted work, while task drift and conflicting replay fail closed. Catalog construction rejects
non-idempotent actions and missing declared configuration dependencies; configuration values and secrets remain
injected into handlers, never graph state.

The production Data specialist adds `DataSpecialistRequest`, which strictly normalizes one `DataRequirement`, provider
and instrument/bar context, discovery source, and optional `sample` loading intent. Its task factory creates exact
manifest and quality slots and separates local-persistence permission from sample-loading approval. The action catalog
registers `validate_market_data_scope`, `ensure_market_data_available`, and `capture_market_data_evidence`; the policy
cannot provide tool names or argument bodies. Snapshot handoffs are accepted only after both returned URIs resolve in
the injected canonical store with matching Data ownership, producer, requester, actor, captured status, request scope
and dataset identity. Checkpoints contain the refs and payload hashes, not the resolved payloads or MCP envelope.

The production Experiment Design specialist adds `ExperimentDesignRequest` and a task factory that accepts only an
approved objective, complete design, exact canonical input refs, requester/actor and explicit local-mutation
permission. Its one action calls `research_create_experiment_protocol_proposal`. The service resolves and hashes every
declared ref, validates implementation kind/status, Data requirement/manifest/quality agreement and optional
optimisation validation, then persists only a proposed record. Exact replay returns the same record; conflicting
content fails without overwrite. The handler reloads the proposal and returns only a canonical digest-pinned handoff.

`apply_experiment_protocol_approvals` is a pure operator-boundary helper. It requires one terminal decision for every
requested approval and preserves approval ID, subject, assumption, requester and requested approver. All approvals
produce the matching approved protocol; any rejection produces a blocked protocol. It performs no persistence, and a
change to any design field requires a new proposal identity.

`SpecialistRouteCatalog` is a separate code-owned boundary over complete specialist graph runners. Public route
metadata contains only authority, immutable route version and supported output artifact types; those types must belong
to that authority. Graph builders, MCP clients, stores, checkpointers and runtime configuration remain injected code.
Unknown or unavailable authorities, unsupported outputs and multiple matching versions fail before graph execution.

### Research Composition Contracts

`ResearchCompositionRequest` fixes one approved objective, stable composition identity, requester/actor and an ordered
bounded set of complete caller-built `SpecialistTask` values. Every task must carry the exact objective, composition ID
as requester and composition actor. The runner never derives a task, symbols, date windows, side-effect permission or
tool arguments from objective prose.

`AcceptedSpecialistResult` is the checkpoint-safe receipt created only after a completed result is validated against the
original task and selected route. It contains task/authority/route/result digests, canonical artifact refs and exact
task-slot URI bindings. Composition resolves every handoff from the canonical store and rechecks artifact type,
authority, producer, requester, actor, status and payload digest before creating that receipt. An approved protocol must
use the accepted Data manifest and quality refs and, when a proposal was accepted, match its protocol ID, objective,
design digest and canonical inputs. A different dataset or design cannot silently replace completed specialist work.

Composition state contains only request/objective/task/proposal/protocol digests, proposal ref, accepted receipts, the
latest bounded result summary, Coordinator decision, child workflow/outcome identity, transition counters and
structured issues. It excludes
complete tasks, protocols, artifacts, raw MCP responses, tool arguments, prompts, credentials and model reasoning.
Composition, specialist and workflow checkpoints use separate thread IDs. Exact terminal replay is a no-op; reused IDs
with changed request or protocol content, ambiguous routes, invalid results, canonical drift or exhausted transition
budgets fail closed. This is a Python library contract and adds no MCP tool.

### Operational Resume Contract

The resume shell uses `WorkflowStepResult` as the only resume input to a checkpointed step. It validates the
plan ID, pending step, attempt, producer command, side-effect class and required output artifact cardinality. It stores
only result identity/status/retry, canonical artifact refs and bounded issues. Arbitrary `public_data` remains an
ephemeral transport projection and is not checkpointed.

The shell emits an interrupt containing only workflow/plan/step/capability identity, producer tool, side effect,
attempt and a configuration digest. It does not accept an arbitrary callable or MCP payload. The operational
idempotency key is retained with a content digest: replaying identical content is a no-op, while reusing the key for
different content terminates the workflow. The operator-visible state excludes plan and result digests.

Postgres checkpoint rows are not `ToolEnvelope` artifacts, canonical `ResearchArtifactRecord` values or evidence that
a tool ran successfully. The workflow executor creates `WorkflowStepResult` only after validating the actual MCP
envelope and its canonical refs.

### Deterministic Execution Contract

The fixed-template compiler accepts an approved `ResearchObjective`, an approved `ExperimentProtocol` and a configured
`ResearchArtifactStore`. It supports only the versioned `supplied_implementation_to_evidence` template. Every supplied
implementation, Data manifest/quality report and optimisation objective validation is resolved by canonical URI and
pinned with a payload SHA-256 digest before the plan is created.

Each `WorkflowStep.configuration` contains one closed `ToolInvocation`: registered tool name, invocation mode, literal
arguments and artifact-slot bindings. It cannot contain a callable, arbitrary MCP payload, filesystem path, database
handle or provider instance. The executor resolves only those bindings, appends `requested_by={workflow_id}` and
`actor=workflow_executor`, and calls `McpToolClient`.

The executor accepts a result only when `command`, `agent_owner` and `side_effect` match the compiled capability and
every returned ref resolves with the declared artifact authority. It hashes produced payloads before checkpointing
their refs. Pinned input drift, unavailable refs, policy blockers and invalid cardinality fail closed. Transport retries
are capped at three attempts. `WorkflowExecutionInterrupted` is a deliberate operator/test pause that preserves the
checkpoint; it is not a terminal outcome.

On re-entry, the executor reloads and fully revalidates any already persisted objective/protocol/plan registration and
terminal outcome before reusing it. Matching records suppress duplicate persistence calls; content, authority,
producer, requester, actor or status drift raises `WorkflowExecutionError`. Accepted workflow steps remain governed by
their independent checkpoint digests.

The execution boundary deliberately transforms and stores different representations at different stages:

| Value | Produced by | Contents | Persistence authority |
| --- | --- | --- | --- |
| `ToolInvocation` | Fixed-template compiler | Closed tool name, invocation mode, literal arguments and artifact-slot bindings. | Embedded in the canonical `WorkflowPlan`; never an arbitrary callable or request body. |
| `ToolEnvelope` | MCP adapter | Transport success/error state, command, allowlist owner, side effect, bounded data, issues and artifact refs. | Ephemeral transport value; not checkpointed as-is. |
| `ExperimentProtocolProposal` | Experiment Design service before approval | Proposed protocol, requested approvals, task/objective/design digests and digest-pinned canonical inputs. | Canonical Experiments-owned artifact, retained unchanged after approval. |
| `WorkflowStepResult` | Workflow executor after envelope/ref validation | Attempt identity, status, retry class, canonical refs and bounded issues. | Bounded summary in the workflow checkpointer; not a canonical research claim. |
| `WorkflowOutcome` | Workflow executor after terminal checkpoint state | Terminal status, produced/review refs, blockers, errors and permitted next actions. | Canonical Orchestration-domain artifact written through MCP. |

The immutable governance payload identity and the write provenance are related but distinct. Objective/protocol payloads
preserve the declared requester and actor; compiled plan/outcome payloads use the protocol requester and
`research_coordinator`. Executor MCP calls, step results and the resulting `ResearchArtifactRecord` provenance use
`requested_by={workflow_id}` and `actor=workflow_executor`. This records mechanical execution without claiming that the
executor made the research-design decision.

| MCP tool | Required input | Canonical output |
| --- | --- | --- |
| `data_create_research_snapshot` | One exact Data scope plus `requested_by` and `actor`. | Matching Data-owned `dataset_manifest` and `data_quality_report` records. |
| `research_create_experiment_protocol_proposal` | Approved objective, complete design request, exact task/requester identity and registered Experiment Design actor. | Immutable Experiments-owned `experiment_protocol_proposal` ref with requested approvals. |
| `research_register_experiment_workflow` | Approved objective, approved matching protocol, ready matching plan, requester and actor. | Orchestration objective/plan refs plus Experiments-owned protocol ref. |
| `research_record_workflow_outcome` | Terminal `WorkflowOutcome`, requester and actor; its ready plan and matching objective/protocol must resolve, every produced/review ref must resolve under its declared authority and pinned hash, and review refs must be a subset of produced refs. | Orchestration-owned `workflow_outcome` ref. |

## Side Effects

| Class | Meaning | Allowed examples |
| --- | --- | --- |
| `read_only` | Reads config, event-store data, local artifacts, or broker/operator snapshots without writing. | Inventory, data quality summary, result lookup. |
| `local_mutating` | Writes local artifacts or bounded research records; never submits broker orders. | Dataset manifest, quality report, sample load, backtest artifact, robustness report. |
| `external_research_mutating` | Mutates an approved external research service without broker or live-runtime mutation. | Explicit tracking projection now; later ML training/registry writes. |
| `broker_read` | Reads broker state through operator-owned surfaces. | Future read-only operator context tools. |
| `broker_mutating` | Mutates broker state. | Not allowed for research-agent MCP tools. |

External writes require a generic default-off gate plus a purpose-specific gate. Training execution and alias
promotion will require additional independent gates even though both use the external research mutation class.

No research-agent tool may start `TraderService`, submit orders, clear halt state, reconcile broker state, run raw SQL,
or bypass core platform validation.

## Initial Data Agent Tools

| Tool | Side Effect | Primary artifact |
| --- | --- | --- |
| `data_get_inventory` | `read_only` | `dataset_manifest.json` payload or reference |
| `data_summarize_quality` | `read_only` | `data_quality_report.json` |
| `data_create_research_snapshot` | `local_mutating` | canonical matching dataset-manifest and quality-report refs |
| `data_ensure_loaded` | `local_mutating` | load/backfill evidence plus dataset manifest update |

These tools are implemented first because the Data Agent owns the ingredients that later research agents consume.

## Agent Tool Inventory

| Tool | Owning agent | Primary artifact |
| --- | --- | --- |
| `knowledge_register_source` | Quantitative Methods Agent | `knowledge_source_manifest.json` or `knowledge://postgres/knowledge_source_manifest/...` |
| `knowledge_ingest_documents` | Quantitative Methods Agent | `knowledge_ingestion_report.json`, schema-v2 evidence units stored in Postgres `knowledge_chunks`, `knowledge_embedding_manifest.json` or `knowledge://postgres/...` refs |
| `knowledge_get_ingestion_status` | Quantitative Methods Agent | source and ingestion status summary |
| `knowledge_list_sources` | Quantitative Methods Agent | source manifest listing |
| `knowledge_search_methods` | Quantitative Methods Agent | approved method-card search result |
| `knowledge_list_method_card_sets` | Quantitative Methods Agent | stable method-card set summaries |
| `knowledge_get_method_card_set` | Quantitative Methods Agent | method-card set revision history |
| `knowledge_retrieve_evidence` | Quantitative Methods Agent | `evidence_retrieval_report.json` with lexical/vector/combined rank diagnostics |
| `knowledge_get_evidence_chunks` | Quantitative Methods Agent | `evidence_chunk_dereference_report.json` with bounded stored chunk text |
| `knowledge_discover_methodology_candidates` | Quantitative Methods Agent | `research://postgres/methodology_candidate/...` refs |
| `knowledge_assemble_methodology_evidence` | Quantitative Methods Agent | `research://postgres/methodology_evidence_packet/...` refs |
| `knowledge_extract_methodology_fields` | Quantitative Methods Agent | `methodology_field_extraction_report` and updated `methodology_candidate` refs |
| `knowledge_validate_methodology_candidate` | Quantitative Methods Agent | `methodology_candidate_validation_report` with readiness summary |
| `knowledge_create_method_card_draft` | Quantitative Methods Agent | canonical evidence-backed `method_card_draft` payload |
| `knowledge_publish_method_card` | Quantitative Methods Agent | approved `method_card.json` |
| `knowledge_update_method_card_status` | Quantitative Methods Agent | retired `method_card.json` status update |
| `knowledge_validate_citations` | Quantitative Methods Agent | `citation_validation_report.json` |
| `math_list_method_contracts` | Quantitative Methods Agent | method contract catalog for indicators, transforms, statistical tests, diagnostics, and multiple-testing procedures |
| `math_validate_method_contract` | Quantitative Methods Agent | method contract validation report |
| `math_register_method_implementation` | Quantitative Methods Agent | `method_implementation_manifest.json` |
| `math_run_indicator_fixtures` | Quantitative Methods Agent | `indicator_validation_report.json` |
| `math_run_signal_fixtures` | Quantitative Methods Agent | `signal_implementation_validation_report.json` |
| `math_generate_python_method` | Quantitative Methods Agent | quarantined generated Python source plus registration and fixture-validation results |
| `math_run_signal_diagnostics` | Quantitative Methods Agent | `signal_diagnostic_report.json` |
| `math_run_multiple_testing_report` | Quantitative Methods Agent | `multiple_testing_report.json` |
| `math_generate_cpp_kernel` | Quantitative Methods Agent | draft `cxx_kernel_manifest.json` from an approved template |
| `math_compile_kernel` | Quantitative Methods Agent | local compiled-kernel build evidence |
| `math_package_method_artifact` | Quantitative Methods Agent | source-backed `method_package_manifest.json` for validated Python indicator/signal implementations |
| `math_run_cpp_conformance` | Quantitative Methods Agent | deferred compiled-kernel conformance/equivalence report |
| `ml_get_runtime`, `ml_health`, `ml_list_training_experiments` | ML Agent | planned configured MLflow training runtime/health metadata |
| `ml_create_feature_set`, `ml_validate_feature_set` | ML Agent | planned `ml_feature_set_spec` and validation report |
| `ml_create_training_dataset`, `ml_create_time_series_split_plan` | ML Agent | planned point-in-time dataset and chronological split artifacts |
| `ml_register_training_pipeline`, `ml_validate_training_pipeline`, `ml_create_training_spec`, `ml_run_training` | ML Agent | planned training pipeline/spec and MLflow fitting evidence |
| `ml_get_training_run`, `ml_reconcile_mlflow_run` | ML Agent | planned reconciled `mlflow_run_ref` |
| `ml_evaluate_model`, `ml_compare_model_versions` | ML Agent | planned time-series model evaluation/comparison reports |
| `ml_register_model_version`, `ml_get_model_version`, `ml_list_model_versions`, `ml_resolve_model_alias`, `ml_assign_model_alias` | ML Agent | planned immutable model-version and promotion artifacts |
| `ml_create_deployment_manifest`, `ml_validate_deployment` | ML Agent | registered version-pinned deployment evidence and parity validation |
| `ml_summarize_predictions`, `ml_compute_drift_report` | ML Agent | planned prediction and drift artifacts |
| `hypothesis_create_card` | Hypothesis Agent | `hypothesis_card.json` |
| `research_create_plan` | Quant Research Supervisor Agent | experiment plan |
| `research_list_strategy_templates`, `research_list_risk_manager_templates` | Strategy Engineering Agent | maintained discovery metadata |
| `research_search_implementations`, `research_get_implementation`, `research_compare_implementation` | Strategy Engineering Agent | bounded catalogue results, exact-version evidence, and field-level compatibility evidence |
| `coding_create_workspace`, `coding_get_workspace`, `coding_destroy_workspace` | Strategy Engineering Agent | exact disposable-workspace lifecycle receipts |
| `coding_search_repository`, `coding_read_repository_file` | Strategy Engineering Agent | bounded read-only repository evidence from the pinned revision |
| `coding_write_candidate_file`, `coding_read_candidate_file`, `coding_resolve_dependencies`, `coding_run_check`, `coding_package_candidate` | Strategy Engineering Agent | bounded candidate files, dependency verdicts, isolated check receipts, and inert candidate packages |
| `research_register_strategy_implementation`, `research_validate_strategy_implementation` | Strategy Engineering Agent | strategy implementation version and independent validation report |
| `research_register_risk_manager_implementation`, `research_validate_risk_manager_implementation` | Strategy Engineering Agent | risk implementation version and independent validation report |
| `research_register_optimization_objective`, `research_validate_optimization_objective` | Quantitative Methods Agent | objective implementation version and validation report |
| `research_create_strategy_specification`, `research_validate_strategy_specification` | Quant Research Supervisor Agent | immutable strategy spec and validation |
| `research_create_risk_stack_specification`, `research_validate_risk_stack_specification` | Quant Research Supervisor Agent | immutable ordered risk spec and validation |
| `research_create_backtest_specification`, `research_validate_backtest_specification` | Quant Research Supervisor Agent | Data Agent-scoped canonical backtest spec and validation |
| `research_run_backtest_specification`, `research_get_backtest_results`, `research_compare_backtest_results` | Quant Research Supervisor Agent | canonical DB run and comparison refs |
| `research_get_optimizer_runtime`, `research_create_parameter_optimization_plan`, `research_run_parameter_optimization`, `research_get_parameter_optimization_results` | Quant Research Supervisor Agent | engine health and canonical plan/run/trial ledger |
| `research_run_parameter_optimization_variants` | Quant Research Supervisor Agent | Adversarial-requested immutable child runs |
| `research_project_experiment_tracking` | Quant Research Supervisor Agent | non-authoritative tracking projection report |
| `research_create_experiment_protocol_proposal` | Experiment Design Agent | immutable proposed protocol and requested approvals |
| `research_register_experiment_workflow` | Quant Research Supervisor Agent | approved objective/protocol and ready plan refs |
| `research_record_workflow_outcome` | Quant Research Supervisor Agent | terminal workflow outcome ref |
| `research_create_walk_forward_plan`, `research_run_walk_forward_optimization`, `research_get_walk_forward_results` | Quant Research Supervisor Agent | deferred walk-forward plan/run/result artifacts |
| `evaluation_generate_parameter_optimization_report` | Evaluation Agent | sealed untouched-holdout Evaluation report |
| `evaluation_generate_walk_forward_report` | Evaluation Agent | deferred stitched out-of-sample walk-forward Evaluation report |
| `evaluation_generate_report` | Evaluation Agent | later skeptical critique report |
| `adversarial_create_parameter_optimization_audit_plan`, `adversarial_generate_parameter_optimization_audit` | Adversarial Agent | immutable attack plan and robustness report |
| `adversarial_run_robustness` | Adversarial Agent | planned broader `robustness_report.json` |
| `adversarial_audit_walk_forward` | Adversarial Agent | deferred walk-forward robustness report |
| `research_analyze_return_attribution` | Quant Research Supervisor Agent | attribution report |
| `research_generate_recommendation` | Quant Research Supervisor Agent | recommendation report |

## Canonical Implementation, Specification, And Optimisation Contracts

Implementation registration accepts `name`, `version`, complete `source_code`, `factory_name`, optional `class_name`, a
bounded parameter schema, dependency declarations, authoring origin, capabilities, resource/runtime requirements,
optional generic provenance refs, and metadata. IDs are content-addressed over normalized identity and source hash.
Validation accepts exactly one implementation ID, URI, or inline payload and writes an
`implementation_validation_report` after import/call safety checks, kind-specific interface construction, parameter
validation, and a deterministic fixture. Strategy/risk/objective implementation records all have Experiments-domain
authority; current tool allowlists route strategy/risk admission through the Supervisor identity and objective
admission through Quantitative Methods. Method cards and packages are not eligibility requirements. Dependency declarations
are descriptive lock/provenance data; they never expand the executable import allowlist. Validation blocks broad
`trader` imports, restricted Trader database/broker/runtime submodules, filesystem/network/database/subprocess/tool
imports, unsafe dynamic builtins, dangerous mutation calls, and dunder-based introspection. Objective modules receive a
separate closed builtin environment and may import only `math`; modules such as `typing` and `statistics` are excluded
because their module globals expose ambient interpreter modules. These are bounded admission and deterministic-fixture controls, not a claim
that arbitrary Python is an operating-system security sandbox.

`research_create_strategy_specification` consumes one passed strategy implementation validation and explicit
parameters, sizing, portfolio mode, runtime context, assumptions, tunable-field declarations, optional provenance, and
optional typed prediction bindings required by that implementation.
Symbols, dates, timeframe, source, and live/broker/raw-SQL permissions are forbidden. The validation tool resolves the
exact source hash again. Risk-stack creation similarly consumes an ordered non-empty array of passed risk implementation
validations with explicit parameters and tunable fields, then revalidates order and every source hash. Strategy tunable
paths use `/strategy/parameters/{name}` or `/strategy/sizing/{name}`; ordered risk paths use
`/risk/{index}/parameters/{name}`. Protocol construction rejects paths that do not identify an explicitly configured
value, use the wrong manager index, or are selected by an optimisation dimension without first being declared tunable.

`research_create_backtest_specification` consumes a passed strategy-spec validation, optional passed risk-stack
validation, exactly one complete Data Agent manifest, matching complete quality report, costs/assumptions, initial
cash/positions, benchmark, deterministic seed, run/logging limits, and optional immutable parent/selection/variant
lineage. It embeds and hashes the normalized Data/quality payloads. The validator re-resolves all upstream validations
and fails on hash or scope drift. Loose scope and filesystem refs are not accepted.

`research_run_backtest_specification` accepts only a passed backtest-spec validation ref and requires
`TRADER_MCP_ALLOW_BACKTESTS=true`. It chooses no-risk or ordered-risk execution from the specification and writes one
canonical `backtest_run` containing summary metrics, complete result, curves, trades, positions, symbol metrics,
exposure, risk decisions/breaches/measures, warnings, blockers, and full implementation/specification/dataset lineage.
Execution is idempotent by deterministic run ID: a complete persisted run is returned only after record identity,
domain authority, producer operation, status, specification, source hashes, dataset hashes, result identity, sidecar completeness, and provenance
revalidate. Drift blocks the call; valid persisted evidence is not overwritten or replayed.
`research_get_backtest_results` accepts exactly one run ID or DB URI. Comparison accepts 2-50 canonical run refs plus a
numeric ranking metric/order. No new execution service reads or returns a durable filesystem path.

### Runtime Prediction And Deployment Contracts

`ml_create_deployment_manifest` accepts passed immutable `ml_model_version_ref` and
`ml_feature_set_validation_report` refs, one configured adapter profile, a typed raw-output contract, inference scope,
bounded failure/latency policy, credential-free environment digest, deterministic parity fixture, and backtest/paper
eligibility. It writes canonical `ml_deployment_manifest` evidence to Trader Postgres. Strategy thresholds, mapping,
sizing, allocation, symbols, broker controls, credentials, mutable aliases, and live eligibility are rejected or absent.

`ml_validate_deployment` accepts exactly one persisted deployment ID, URI, or matching inline payload. It rechecks
model/feature snapshots, content-derived IDs, adapter version/configuration, and availability, then loads the pinned
model and compares normalized parity output hashes. Model loading requires `TRADER_MCP_ALLOW_ML_RUNTIME=true`. A passed
report remains subject to the same drift checks whenever a strategy specification or run resolves it.

A strategy implementation declares named `prediction_requirements` in its closed `runtime_requirements`: accepted raw
semantics, horizons, scalar/structured shapes, inference scopes, consumer kind, and required status. Its strategy
specification binds each name to one passed deployment validation, selected output names, and a maintained versioned
mapper with explicit parameters. The normalized deployment, output, and mapper snapshots contribute to the strategy
specification and backtest-run identities. The deployment remains ML-domain evidence; the Experiments-domain binding
contains the trading interpretation.

At run composition, the resolver revalidates all evidence and constructs `FeatureProvider`, `Predictor`, and mapper
objects once. `per_symbol` decisions use independent symbol callbacks. `universe_snapshot` decisions require an exact,
synchronized configured universe and execute once per complete timestamp; stale, missing, duplicate, or misaligned
members fail closed. Bounded `prediction_events` record model/deployment/feature hashes and raw outputs before mapped
`signal_events`; created orders carry those refs in `decision_evidence` and still pass through normal risk processing.

An optimisation plan consumes a passed selection-region backtest-spec validation, a sealed chronological holdout Data
Agent manifest and matching quality report, one passed `optimization_objective` validation, direction, typed finite
search dimensions, constraints, seed, trial budget, and bounded sequential resource limits. Every dimension path must be
explicitly declared tunable by the owning strategy/risk spec. Costs, datasets, implementations, provider settings,
holdout/fold boundaries, and undeclared fields are rejected.

The objective receives only this closed object:

```json
{
  "schema_version": "1.0",
  "status": "passed",
  "metrics": {},
  "counts": {},
  "costs": {},
  "exposure": {},
  "risk": {},
  "quality": {},
  "constraints": {},
  "lineage": {}
}
```

Unknown top-level fields, non-scalar metrics/costs, invalid counts, unsupported runtime imports/calls, and unavailable
objective metrics block. An engine receives only search dimensions, seed, prior canonical trial outcomes, direction,
and budget. A run pins engine profile/version/configuration digest/capabilities, seed, and executor kind. It never changes
engine in place. Each canonical trial stores the suggestion, retry attempts, exceptions, child specs/runs, closed
observation, constraints, objective result, diagnostics, warnings, and blockers. Selection is deterministic and remains
exploratory. Trial budgets are limited to 1-1,000, execution remains sequential, and retry attempts are limited to
1-3. Warning, blocker, and exception evidence is count/size bounded before persistence. A declared
`per_trial_timeout_seconds` requires a deadline-capable executor; otherwise the trial blocks before child execution.
The Postgres MCP adapter enforces that deadline by spawning a fresh child process, recreating its Postgres connections
after spawn, and terminating overdue work. Merely observing elapsed time after an executor returns does not satisfy the
contract.

Canonical run consumption is fail-closed rather than a projection lookup. The loader verifies the run ID against the
resolved engine profile and executor, reloads the plan and all upstream validations, requires contiguous trial
sequence/IDs and declared parameters, reevaluates every passed observation with the pinned objective, recomputes counts
and tie-breaking, and compares the selected parameters/value/child refs. A modified run, plan, trial, implementation,
validation, strategy parameter, cost assumption, dataset/quality snapshot, or selection lineage is therefore rejected
by every downstream consumer.

`builtin_grid` and `builtin_random` are always available without Optuna or MLflow. `optuna_tpe` is lazy and requires its
dedicated configured non-public schema/role plus both external-write and Optuna-write gates. Provider loss blocks or
leaves a run partial; `research_get_parameter_optimization_results` reads canonical Trader evidence without the provider.

`research_project_experiment_tracking` accepts only a supported canonical run ref and configured profile. It derives
all metrics/tags, calls the sink at most once per canonical digest/profile, and writes an idempotent
`experiment_tracking_projection_report` with `authoritative=false`. It accepts no arbitrary metrics, tags, URI, or
credentials. The generic external-write and experiment-tracking-write gates are both required.

Evaluation accepts an optimisation run and a matching sealed-holdout `backtest_run`. It verifies completed selection,
holdout dataset hash, selected strategy specification, selection lineage, and required risk telemetry before writing its
own report. Adversarial plan creation freezes a baseline digest and declared attacks. The Supervisor executes immutable
requested optimisation variants; cost/window stresses use immutable child backtest specs. Adversarial judgment consumes
those refs, cannot rewrite the baseline/selection, and blocks missing required evidence or observed instability.

## Method Package Artifacts

`math_package_method_artifact` packages a validated Python implementation for optional implementation producers. It is
local-mutating and writes `method_package_manifest.json`; it does not register an executable strategy.

Request fields:

- `implementation_id` or `implementation_manifest`: a `method_implementation_manifest` whose `status` is `validated`.
- `validation_report_id` or `validation_report`: a passed `indicator_validation_report` or
  `signal_implementation_validation_report` matching the implementation.
- Optional `cxx_kernel_id` or `cxx_kernel_manifest`: compiled C++ metadata for the same Python implementation.

Success data contains `method_package_manifest` with:

- package ID, method ID, runtime contract, implementation ID, entrypoint, class name, source path/hash/provenance, and
  constructor kwargs.
- method contract snapshot, approved method-card refs, validation report ref, validation summary, safety profile, and
  dependency allowlist.
- optional accepted `cxx_kernel_refs`, warnings, blockers, `status="validated"`, and schema version.

Python validation is the gate. Packaging fails closed when the implementation is not validated, source hashes do not
match, approved method-card refs are missing, runtime contracts are unsupported, or the validation report is missing,
failed, blocked, mismatched, or the wrong report type. C++ refs are optimization metadata only: missing, generated,
uncompiled, mismatched, or otherwise invalid C++ refs produce warnings and are excluded without blocking a valid Python
package.

## Maintained Implementation Template Catalog

`research_list_strategy_templates` and `research_list_risk_manager_templates` are read-only discovery tools over the maintained implementation catalog exposed by `trader_research.experiments`. Each row exposes a stable template ID, implementation kind, runtime contract, real `trader_standard` entrypoint, typed parameter metadata, required runtime context, and concise behavior metadata. Strategy rows also declare portfolio mode. Maintained entries are never direct-reuse evidence.

The implementation catalogue search accepts a bounded query, implementation kinds, capabilities, runtime contract,
portfolio mode, and optional visibility of unadmitted canonical versions. It returns metadata without source. Exact
resolution accepts an implementation ID or canonical URI and returns admission evidence; source requires an explicit
bounded request. Comparison accepts one exact implementation plus typed build-contract fields and returns match,
difference, and unknown rows. It does not make the Strategy Engineering reuse/adapt/author decision or claim efficacy.

The Coding Workspace contract separates a pinned read-only repository snapshot from candidate writes. Workspace
identity is derived from the attempt and build-contract identities. Repository and candidate paths are normalized and
bounded by suffix and size policy. Dependency resolution is an allowlist verdict and performs no installation.
Candidate checks accept only the registered compile, Ruff, and pytest identities and run through a pinned,
networkless, read-only, resource-bounded container with the workspace mounted read-only; an unavailable runtime fails
closed without host execution. Packaging returns inert source, file hashes, revision, and check evidence. It does not
import, admit, execute in Trader, backtest, deploy, or trade the candidate. The entire surface remains unavailable
unless the Coding Workspace policy gate and exact runtime configuration are enabled.

Catalog rows are informational producer metadata. They are not implementation versions, executable specifications, validation evidence, or permission to run code. They do not contain method-card requirements, candidate validation requirements, source generators, dataset scope, filesystem paths, or mutable provider identity. To execute a maintained implementation, a producer submits its source through the same content-addressed implementation registration and validation contract used by handwritten and externally produced code.

The candidate-era Python packages, domain models, filesystem bundle readers, and performance-report service have been deleted. Their MCP names and artifact types are unsupported. No compatibility alias, filesystem fallback, migration reader, or automatic translation from candidate IDs exists.

Compatibility aliases may be kept while the older Math Coder naming is retired:

| Alias | Canonical tool |
| --- | --- |
| `math_list_indicator_contracts` | `math_list_method_contracts` filtered to indicator and transform families |
| `math_validate_indicator_contract` | `math_validate_method_contract` filtered to indicator and transform families |

The `math_*` namespace is a tool namespace, not a claim that the agent is limited to coding indicators. The owning
identity is Quantitative Methods Agent.

Knowledge-base rules:

- Hybrid retrieval combines lexical and vector indexes; those indexes are retrieval infrastructure, not authority.
- Runtime MCP knowledge storage uses Postgres by default. PostgreSQL full-text search handles lexical retrieval and
  pgvector handles dense retrieval; tests may inject a JSON compatibility store.
- The authority is the approved source registry plus approved method cards.
- Evidence retrieval should return citeable schema-v2 evidence units with source IDs, locators, source approval status,
  local label metadata, neighbor refs, and lexical/vector rank metadata rather than opaque context blobs.
- Evidence dereferencing is explicit: agents call `knowledge_get_evidence_chunks` with retrieved `chunk_id` values to
  receive real stored evidence-unit text, source metadata, locators, text hashes, `hash_verified`, text length metadata,
  and `text_truncated`. The request field remains `chunk_ids`; the values are evidence-unit IDs after schema v2.
- Legacy broad chunk manifests are not translated. A knowledge base created before schema-v2 evidence units must be
  reset and reingested so old chunk refs do not silently contaminate methodology artifacts.
- `knowledge_ingest_documents(force=true)` performs source-scoped replacement without first deserializing existing
  evidence rows. This allows an operator to regenerate incompatible evidence-unit versions without adding legacy
  translation or compatibility reads.
- Ingestion builds and validates the complete embedding generation before replacing active evidence. The Postgres store
  publishes replacement evidence units, vectors, the embedding manifest, and the success report in one transaction;
  provider or publication failure leaves the prior active generation visible.
- Ingestion does not imply approval; `method_card_draft.json` is not executable.
- Sophisticated statistical-test and multiple-testing contracts must cite approved method cards and pass
  `knowledge_validate_citations`. Seeded cards and persisted approved cards in the configured `KnowledgeStore` are both
  visible to citation and math validation.
- Knowledge tools must not expose arbitrary filesystem access, execute code from documents, or reproduce large source
  passages in artifacts.

Methodology schema:

The conceptual semantic-extraction design and execution graph are defined in
[semantic_extraction.md](semantic_extraction.md). This appendix defines transport and artifact contracts.

- `methodology_candidate` is a Quantitative Methods artifact for source-backed candidate structure before approval or
  execution. It is not a method card, implementation, strategy, or risk manager.
- `methodology_evidence_packet` is a Quantitative Methods artifact that records family-role evidence assembled from
  candidate evidence units before field extraction. It stores role IDs, found/missing roles, accepted role
  evidence-unit refs, rejected or weak role refs, source/chunk/text hashes, readiness goal, and diagnostics. Each role
  ref records `target_binding`, `accepted_target_binding`, binding terms, competing method labels, and the reason it was
  accepted or rejected. It is not a method card or approval.
- Method cards use the `method_card_draft` and `method_card` artifact types and always carry nullable methodology fields,
  field-level evidence, candidate lineage, and validation lineage. There is no second shallow or rich card format.
- Methodology fields are grouped into common core groups: `identity`, `scope`, `data_requirements`, `method_specification`,
  `signal_decision_logic`, `portfolio_execution`, `risk_validation`, and `implementation_notes`.
- Domain extension blocks are nullable and closed: `technical_indicators`, `statistical_arbitrage`,
  `options_derivatives`, `fundamental_valuation`, `sentiment_alternative_data`, `portfolio_construction`,
  `risk_models`, and `execution_methods`.
- Each populated field uses the same shape: `value`, `evidence_refs`, optional `confidence`, optional `quality`,
  `warnings`, and `blockers`. Populated values require at least one field-level evidence ref. Null fields do not require
  evidence.
- Unsupported core groups, extension blocks, or field names fail closed at schema construction.
- Source suitability matters. Internal notes can support operator-local context, but textbook or primary-source claims
  for high-risk families need real textbook, paper, documentation, or comparable curated sources. The validator blocks
  textbook/primary-source claims backed only by internal notes.
- Method-card fields are descriptive evidence, not executable code. They can provide provenance, defaults, and template
  eligibility only where a maintained service explicitly supports the method family.

Methodology candidate tool contracts:

- `knowledge_discover_methodology_candidates` request: optional `query`, optional `source_ids`, optional
  `method_families`, `top_k=25`, `neighbor_radius=1`, `max_candidates=10`, and `approved_only=true`. At least one of
  `query`, `source_ids`, or `method_families` is required.
- Discovery combines retrieval, direct source evidence-unit scans, neighboring evidence units, local method-label
  evidence, deterministic method-identity grouping, and de-duplication. Source-level method families are scope hints,
  not automatic candidate labels. Candidate records carry `method_identity` with canonical/source name, aliases,
  abbreviations, identity evidence-unit refs, query alignment, and competing method labels. Success writes
  `methodology_candidate` records and returns `research://postgres/...` refs. It does not create method cards,
  implementations, strategies, or approvals.
- `knowledge_assemble_methodology_evidence` request: exactly one of `methodology_candidate_id`,
  `methodology_candidate_uri`, or inline `methodology_candidate`; optional `readiness_goal`, `neighbor_radius`, and
  `max_chunks_per_role`.
- Evidence assembly selects a family-level evidence profile, searches candidate/source evidence units for role-specific
  evidence, and writes `methodology_evidence_packet`. Role profiles are target-agnostic: they define evidence
  categories such as definition, input data, formula, parameters, signal logic, risk controls, limitations, and
  validation requirements, but they do not enumerate known method names. A role item counts only when the evidence unit
  contains role terms and is bound to the target method by direct label, alias label, same sentence, same paragraph, or
  accepted nearby context. Generic family nouns do not satisfy specialized implementation roles by themselves; for
  example, calling something an indicator is not formula or algorithm evidence. Competing labels, missing role terms,
  and weak context are retained under `rejected_chunks` and diagnostics, not counted as readiness evidence. Missing
  required accepted roles produce packet blockers.
- `knowledge_extract_methodology_fields` request: exactly one candidate input or evidence-packet input
  (`methodology_candidate_id`, `methodology_candidate_uri`, inline `methodology_candidate`, `evidence_packet_id`,
  `evidence_packet_uri`, or inline `evidence_packet`); optional `max_chars_per_chunk`.
- Extraction dereferences candidate evidence units and, when a packet is supplied, populates only fields supported by
  accepted target-bound role evidence. Evidence units are non-exclusive; packet refs carry accepted and rejected exact
  claim spans within each unit. Rejected or weak spans never populate fields, even when the surrounding unit also
  contains accepted target evidence. Field-level source/chunk/claim-span refs identify every contributing
  span, including offsets, selected text/hash, role, target binding, and extraction version. Field-specific semantic
  filters prevent generic role evidence from populating specialized fields, and bounded multi-span synthesis retains all
  contributing refs. Unrelated extension blocks remain absent/null. Success writes the updated
  `methodology_candidate` plus `methodology_field_extraction_report`.
- `knowledge_validate_methodology_candidate` request: exactly one candidate input or extraction-report ref
  (`methodology_candidate_id`, `methodology_candidate_uri`, inline `methodology_candidate`, `extraction_report_id`, or
  `extraction_report_uri`).
- Validation checks source/chunk existence, chunk-source consistency, locator matches, closed field groups and names,
  field-level refs, quote limits, family minimums, high-risk family evidence counts, internal-note-only textbook or
  primary-source claims, source-backed method identity, required identity evidence-unit refs, packet role consistency
  against accepted target-bound role refs, stale packet source/locator/text hashes, and fields that cite rejected or
  competing-method evidence. Packet lineage is required for passed semantic validation; packet-less extraction can
  populate fields but cannot validate into a canonical method-card draft. It writes
  `methodology_candidate_validation_report` with status `passed` or `blocked` and readiness summaries for descriptive,
  implementation, signal, strategy-template, or risk-manager use where the family profile defines them.
- Methodology field refs must include exact `claim_span` provenance. Validation re-slices stored evidence-unit text at
  the supplied offsets, recomputes the span hash, checks role and target binding, and verifies specialized field semantics.
  Another method appearing elsewhere in the same evidence unit is not a blocker.
- `knowledge_create_method_card_draft` request: exactly one of `methodology_candidate_validation_id`,
  `methodology_candidate_validation_uri`, or inline `methodology_candidate_validation_report`; optional `method_id`,
  `title`, `family`, and `version`.
- Canonical method-card draft materialization requires a packet-backed passed validation report with `valid=true`, empty
  blockers, implementation readiness, and a loadable matching `methodology_candidate` whose lineage points to the same
  evidence packet as the validation report. Optional `method_id`, `title`, or `family` overrides fail closed unless the
  candidate identity, aliases, abbreviations, and validated families support them. The service revalidates source/chunk
  evidence, derives compact summary fields from evidence-backed methodology fields, and fails closed if assumptions, inputs, outputs,
  or failure modes cannot be populated.
  Success writes the complete `method_card_draft` with nullable field groups, field-level evidence refs, candidate
  lineage, validation refs, source hashes, and chunk hashes. Search derives a compact `MethodCardSummary`; summaries
  have no writable parser or persistence API.
- `knowledge_publish_method_card` preserves the complete payload. Approved cards remain visible to method-card search,
  citation validation, evidence-required method contracts, implementation registration, and method packaging through
  derived summaries or the narrow approved-card read port.
- Approved cards may be retained as optional provenance by an external implementation producer. The resulting
  source receives no special eligibility: it must pass the same content-addressed implementation registration,
  validation, and specification contracts as handwritten or maintained source. Numeric behavior is never inferred from
  prose at execution time.
- These tools are DB-first `local_mutating` tools. MCP requires a configured research artifact store and fails closed
  with `research_artifact_store_unavailable` when canonical DB persistence is unavailable.

`knowledge_get_evidence_chunks` contract:

- Request: `chunk_ids: list[str]` required, maximum 25; optional `source_id`; `include_text: bool = true`;
  `max_chars_per_chunk: int = 4000`, bounded to 1-20000.
- Success data: `evidence_chunk_dereference_report`, top-level `chunks`, `chunk_count`, and `missing_chunk_ids`.
- Each returned item is a schema-v2 evidence unit and includes `chunk_id`, `evidence_unit_id`, `source_id`, source
  title/type/status, `approved_source`, `locator`, `topics`, `method_families`, `text_hash`, `hash_verified`,
  `text_char_count`, `text_word_count`, `text_truncated`, and `text` when requested.
- Missing chunk IDs or source mismatches fail closed with `code="chunk_dereference_error"` and structured
  `missing_chunk_ids` / `source_mismatch_chunk_ids`; no embedding vectors are returned.

`knowledge_create_method_card_draft` contract:

- Request: `method_id`, `title`, `family`, non-empty `assumptions`, `inputs`, `outputs`, `failure_modes`, and
  `evidence_refs`; optional `version`.
- Evidence refs must include at least one source or chunk reference and pass citation validation with
  `require_approved_method_card=false`.
- Success data contains a legacy/projection `method_card_draft`; draft cards are persisted but excluded from default
  approved method search and are not sufficient for canonical rich-methodology readiness.

`knowledge_publish_method_card` contract:

- Request: `draft_method_card_id`, `approved_method_card_id`, `approved_by`, `approval_note`, and `approve=true`.
- Publishing preserves the draft and creates a separate approved `method_card` with approval provenance.
- Publishing preserves `method_card_set_id` lineage, writes a new immutable card revision, supersedes any prior current
  approved card in the same set, and updates the set's current approved pointer.
- Re-publishing the same approved card is idempotent only when the persisted content matches; conflicting content fails
  closed.

Method-card set contracts:

- Method-card rows carry `method_card_set_id`, `revision_number`, and optional `supersedes_method_card_id`.
- Rows or payloads missing `method_card_set_id` or `revision_number` are invalid. The platform does not synthesize
  legacy set IDs or silently backfill old Postgres method-card data; operators should reset/recreate method-card rows or
  run an explicit reviewed migration when old data must be kept.
- A method-card set is the stable aggregate identity for a methodology card; `method_card_id` remains the immutable
  draft or approved revision ID used for exact citations.
- Draft creation derives a set ID from method ID, family, normalized title, and source fingerprint, unless the caller
  supplies an explicit set ID to create an intentional revision.
- Set summaries expose current approved and draft pointers, status counts, source fingerprint, card IDs, and latest
  revision number.
- The set-listing tool is read-only and supports method ID, family, status, retired visibility, and limit filters.
- The set-detail tool is read-only and returns one set plus revision history when requested.
- Postgres exposes pgAdmin-friendly active-card, revision-history, and set-summary views. Active views filter out
  `rejected` and `superseded` card rows; canonical storage preserves those rows for audit.

`knowledge_update_method_card_status` contract:

- Request: `method_card_id`, `status`, `updated_by`, `note`, and optional `superseded_by_method_card_id`.
- `status` is limited to `rejected` or `superseded`; the tool cannot approve cards or bypass
  `knowledge_publish_method_card`.
- `superseded_by_method_card_id` is required when `status="superseded"`.
- The target must be a persisted method card. Seeded cards are not retired by this tool.
- Success updates the stored method-card payload through the configured knowledge store, preserves lifecycle audit
  metadata, repairs method-card set current pointers, and hides the retired card from normal method-card search and
  approved-card checks.

`math_register_method_implementation` contract:

- Request: `method_id`, non-empty `method_card_ids`, optional `method_contract`, optional `entrypoint`, optional
  `source_path`, optional `class_name`, optional `constructor_kwargs`, optional `implementation_kind`
  (`maintained` or `generated`), optional `dependency_allowlist`, and optional `expected_source_hash`.
- Runtime contract: the method contract declares the Trader runtime class. Current supported values are
  `trader.indicators.Indicator` and `trader.signals.Signal`. The entrypoint must resolve to a subclass of the declared
  runtime contract; this reuses Trader package contracts instead of creating a parallel implementation schema.
- Source provenance contract: the implementation source file must have a module-level docstring with `Source reference`
  and `Implements` sections. The docstring must name the registry method, at least one approved method-card reference,
  implementation class, Trader runtime contract, implemented formula/algorithm/action rule, input ordering, warmup
  behavior, output ordering for series methods, and no-lookahead boundary. For generated quarantined implementations,
  the docstring must name the exact method-card IDs passed to the tool.
- Validation: method ID must exist in `math_registry`; approved method-card refs must match the method; source hash must
  match when supplied; provenance docstring checks must pass; imports and calls must pass the static safety allowlist;
  generated implementations must resolve from their artifact source path.
- Success data contains `method_implementation_manifest` with method ID, language, implementation kind, entrypoint,
  class name, source path, source hash, constructor kwargs, approved method-card refs, method contract,
  source provenance, `runtime_contract`, dependency allowlist, safety profile, and `status="registered"`.

`math_run_indicator_fixtures` contract:

- Request: either `implementation_id` for a persisted manifest or `implementation_manifest` inline; optional `fixtures`.
- The manifest must have `runtime_contract="trader.indicators.Indicator"`; signal manifests fail closed with
  `code="invalid_runtime_contract"`.
- Fixture inputs use ascending close values. The service builds latest-first `Bar` sequences, calls
  `Indicator.compute_series(bars)`, expands warmup nulls, compares expected values, and runs prefix checks for
  no-lookahead behavior.
- Before fixtures run, the service revalidates the manifest, approved method cards, source hash, entrypoint, and static
  safety checks.
- Success data contains an updated `method_implementation_manifest` with `status="validated"` and an
  `indicator_validation_report` with validation ID, implementation ID, method ID, entrypoint, source hash,
  fixture results, warnings, and blockers. Fixture mismatches return `ok=false` and leave the manifest blocked.

`math_run_signal_fixtures` contract:

- Request: either `implementation_id` for a persisted manifest or `implementation_manifest` inline; optional `fixtures`.
- The manifest must have `runtime_contract="trader.signals.Signal"`; indicator manifests fail closed with
  `code="invalid_runtime_contract"`.
- Fixture inputs use ascending close values. The service builds latest-first `Bar` sequences and calls
  `Signal.compute(bars) -> float`.
- Fixture payloads use `expected` for the scalar output and may use `expected_prefix` for no-lookahead/warmup checks.
  An `expected_prefix` value of `null` means the prefix should raise warmup `ValueError`; a numeric value must match the
  scalar output for that prefix.
- Before fixtures run, the service revalidates the manifest, approved method cards, source hash, entrypoint, static
  safety checks, runtime subclass, and provenance docstring.
- Success data contains an updated `method_implementation_manifest` with `status="validated"` and a
  `signal_implementation_validation_report` with validation ID, implementation ID, method ID, entrypoint, source hash,
  scalar fixture results, prefix results, warnings, and blockers. Fixture mismatches return `ok=false` and leave the
  manifest blocked.

`math_run_signal_diagnostics` contract:

- Request: `signal_observations`, `forward_return_labels`, `candidate_family_manifest`, `method_contracts`, optional
  `quantile_count`, and optional `data_quality_report`.
- `signal_observations` rows must include `candidate_id`, `signal_name`, `symbol`, `ts`, and finite numeric `value`.
  Optional `session`, `regime`, and `metadata` are explanatory context; raw indicator values are not the primary tested
  unit.
- `forward_return_labels` rows must include `symbol`, `ts`, positive integer `horizon`, and finite numeric
  `forward_return`. The service joins labels to observations by `symbol` and `ts`, then computes per-horizon results.
- `candidate_family_manifest` must include `candidate_family_id`, unique candidate IDs, and the tested grid. Candidate
  IDs referenced by observations or p-value rows must be declared before inference.
- Evidence: every horizon requires a `rank_ic` method contract with approved method-card evidence. If a candidate
  declares an implementation manifest or implementation ID, that manifest must be validated and must use
  `runtime_contract="trader.signals.Signal"`. Candidates without executable implementation evidence may run as
  observational diagnostics with warnings.
- Success data contains `signal_diagnostic_report` and an artifact reference. The report includes candidate count,
  tested grid, input counts, implementation refs, IC/rank IC, rank-IC p-values where sample size permits, hit rate,
  action-conditioned returns, coverage, turnover proxy, quantile buckets for continuous signals, monotonicity score,
  and symbol/session/regime breakdowns. Discrete `-1/0/+1` action signals skip quantile monotonicity and report an
  explanatory warning.
- Validation failures such as duplicate observation keys, missing labels for all observations, non-finite values,
  unknown candidates, missing rank-IC evidence, or invalid implementation manifests return `ok=false` with blockers
  embedded in the persisted report.

`math_run_multiple_testing_report` contract:

- Request: `candidate_family_manifest`, `metric_matrix`, `method_contract`, and optional `alpha`.
- `candidate_family_manifest` must include `candidate_family_id`, unique candidate IDs, candidate count implied by the
  declared IDs, and tested grid metadata.
- `metric_matrix` must contain exactly one p-value row per declared candidate. Rows must include `candidate_id` and
  finite `p_value` or `raw_p_value` in `[0, 1]`; optional `metric_name`, `metric_value`, and `horizon` are preserved in
  report rows.
- `method_contract.method_id` must be `benjamini_hochberg`, with approved method-card evidence. The first implemented
  multiple-testing method is Benjamini-Hochberg; Bonferroni, Holm, White Reality Check, Hansen SPA, Deflated Sharpe
  Ratio, and PBO remain follow-on methods.
- Success data contains `multiple_testing_report` and an artifact reference. The report includes raw p-values,
  adjusted p-values, rejection flags, accepted/rejected candidate IDs, correction method, alpha, candidate count,
  tested grid, warnings, and blockers.
- Validation failures such as missing candidate family metadata, duplicate candidate IDs, unknown metric candidates,
  duplicate metric rows, invalid p-values, missing candidate p-values, or missing method-card evidence return
  `ok=false` with blockers embedded in the persisted report.

`math_generate_python_method` contract:

- Request: `method_id`, non-empty `method_card_ids`, `method_contract`, and optional `fixtures`.
- MCP calls the configured provider-neutral LLM client and requires JSON with `class_name` and `source_code`.
- The generation prompt requires `source_code` to start with the same module-level provenance docstring enforced by
  `math_register_method_implementation`.
- Generated code is written only under `artifacts/research/method_implementations/quarantine/`; it is never written to
  `src/` or imported as a maintained package.
- Static safety checks reject filesystem access, network/process/SQL/broker imports, dynamic imports, `eval`, `exec`,
  `open`, global/nonlocal mutation, and dependencies outside the allowlist.
- Passing generated drafts immediately run through `math_register_method_implementation` and
  the fixture runner selected by `runtime_contract`: `math_run_indicator_fixtures` for Indicator methods and
  `math_run_signal_fixtures` for Signal methods. Success data reports the generated source path, registration result,
  fixture-validation result, and `status="validated"`; failures remain quarantined with `status="blocked"`.

`math_generate_cpp_kernel` contract:

- Request: either `implementation_id` for a persisted Python method implementation manifest or
  `implementation_manifest` inline; optional `template_id`.
- The Python manifest must have `status="validated"`, `runtime_contract="trader.indicators.Indicator"`, approved
  method-card refs, and an unchanged source hash. Signal manifests, unvalidated manifests, missing evidence, and
  unsupported methods fail closed.
- The first supported template is `sma_scalar_series_v1` for `method_id="sma"`. The tool renders only maintained
  templates under `trader_standard`; it does not accept arbitrary C++ source from callers or LLMs.
- Generated source is scanned for disallowed includes and unsafe call patterns, then written under the caller's
  artifact root with a `cxx_kernel_manifest`.
- Success data contains `cxx_kernel_manifest` with Python implementation provenance, method-card refs, method contract,
  template ID/hash, generated source path/hash, ABI metadata, warmup/NaN/alignment/dtype/no-lookahead policy, and safety
  policy. Unsupported or unsafe inputs return `ok=false` with blockers.

`math_compile_kernel` contract:

- Request: either `kernel_id` for a persisted C++ kernel manifest or `kernel_manifest` inline; optional `compiler` and
  `timeout_seconds`.
- Compilation verifies the generated source hash and safety scan before invoking a compiler. The compile command uses
  fixed safe flags, runs in an isolated artifact build directory, and captures stdout/stderr to a build log.
- Success data contains an updated `cxx_kernel_manifest` with compiler path/version, flags, command, build directory,
  binary path/hash/size, build log path, `status="compiled"`, and a compile-only benchmark summary.
- Missing compilers, tampered sources, disallowed source content, timeouts, or compiler failures return `ok=false` with
  an updated `status="compile_failed"` manifest and blockers. Contract-first C++ conformance/equivalence is deferred
  behind the method-package -> strategy -> backtest -> performance-report toolchain.

## LangGraph Use

Each LangGraph agent has its own identity, state schema, role policy, tool allowlist, and required output artifact.
Agents call MCP tools through an MCP client wrapper. They must not call platform internals directly when an MCP tool
exists.

Minimal allowlists:

| Agent | Allowed initial tools |
| --- | --- |
| Data Agent | `data_get_inventory`, `data_summarize_quality`, `data_create_research_snapshot`, `data_ensure_loaded`, read-only health/config |
| Strategy Engineering Agent | Implementation discovery/comparison, bounded Coding Workspace, and strategy/risk admission tools |
| Quant Research Supervisor Agent | Specialist artifact reads, supervisor handoff tools, specification/backtest/optimisation `research_*` tools |
| Quantitative Methods Agent | `knowledge_*` retrieval/ingestion/citation tools, `math_list_method_contracts`, `math_validate_method_contract`, fixture, diagnostic, multiple-testing, method-packaging, and optional kernel tools |
| ML Agent | Registered `ml_create_deployment_manifest` and `ml_validate_deployment`; remaining 39A-G/J lifecycle tools are planned. |
| Hypothesis Agent | Ingredient artifact reads, `hypothesis_create_card` |
| Evaluation Agent | Canonical backtest reads, `evaluation_generate_parameter_optimization_report`, later broader reports |
| Adversarial Agent | Canonical plan/run reads and registered parameter-optimisation audit tools |

LangGraph state may store artifact references, status, public messages, and structured decisions. It must not persist
hidden reasoning or raw LLM scratchpads as product records.
