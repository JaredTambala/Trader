# First Agentic Implementation Slice — Review Plan

Status: temporary review draft; no implementation is authorized until this plan and its prerequisite architecture
records are accepted.

Last reviewed: 2026-09-01.

This is a temporary sub-document of the [Agent Designs](../agent_designs.md) workbook. It converts the selected
Coordinator–Data–Strategy direction into a reviewable implementation sequence. It does not replace the owning
[Research Coordinator](research_coordinator.md), [Data Research](data_research.md), or
[Strategy Engineering](strategy_engineering.md) architecture records, the
[Agentic Research Orchestration Redesign](../agentic_orchestration_redesign.md), or the
[Research Capability Roadmap](../research_capability_roadmap.md).

After review, accepted architectural decisions belong in those canonical records and accepted delivery dependencies
belong in the roadmap. This temporary document should then be deleted or reduced to unresolved implementation notes so
it does not become a competing tracker.

## Decision requested

Approve or amend:

1. the functional cutoff at a coordinator-accepted Data readiness return plus an independently admitted strategy or
   risk candidate;
2. the operator-specified build-contract route for the first slice while Knowledge Research and Quantitative Methods
   remain deferred;
3. the gates and work sequence below, including a disposable framework comparison before production cutover;
4. the proposed MCP capability changes, isolated coding boundary, and clean replacement of `trader_agents`; and
5. the behavioral, security, recovery, cost, and latency evidence required before the slice is called implemented.

Reviewing this plan does not reopen the accepted agent authority boundaries. Any proposed implementation that would
change those boundaries returns to the owning agent record before code is written.

## Intended product outcome

The first slice proves one useful, recognizably agentic research path:

```text
operator supplies a natural-language research brief, scope and authority
  -> Research Coordinator interprets the brief and creates a visible bounded agenda
  -> deterministic policy validates scope, dependencies, approvals and budgets
  -> Data Research investigates the complete multi-asset data scope through MCP
  -> Strategy Engineering investigates the implementation catalogue through MCP
  -> independent ready work may proceed concurrently
  -> Data Research optionally backfills inside its approved envelope and revalidates
  -> Strategy Engineering chooses reuse, adaptation or new authorship
  -> isolated Coding Workspace checks and packages the exact candidate
  -> independent deterministic admission accepts or rejects it
  -> a rejected candidate may enter a bounded evidence-led repair attempt
  -> every specialist return rejoins the Research Coordinator
  -> the coordinator verifies canonical refs and advances, revises, asks, concludes or stops
```

The successful terminal result is not a backtest or a recommendation. It is a grounded coordinator conclusion that
identifies:

- an exact Data scope with canonical manifest and quality evidence, including partial or blocked scope where
  applicable;
- one exact admitted strategy or risk implementation version, or an explicit implementation blocker;
- implementation comparison and reuse/adapt/author evidence;
- immutable branch, delegation, candidate-attempt and admission lineage;
- assumptions, uncertainty, consumed budgets and unresolved questions; and
- the permitted next action, normally future handoff to Experiment Design.

The path is agentic only if models make meaningful, evidence-responsive choices about agenda, delegation, investigation,
tool use, implementation approach and revision. Deterministic validation, a hard-coded route disguised as a model
agent, or prose wrapped around the frozen orchestration does not satisfy the outcome.

## Scope boundary

### Included

- A real-model Research Coordinator with structured agenda, delegation, evidence review and decision outputs.
- A real-model Data Research Agent using a dynamically narrowed, role-scoped MCP catalogue.
- A real-model Strategy Engineering Agent using implementation-catalogue and Coding Workspace MCP capabilities.
- Operator clarification and approval interrupts.
- Multi-asset and role-labelled Data scope, bounded acquisition, revalidation and exact snapshot evidence.
- Maintained and previously admitted implementation discovery, comparison, reuse, adaptation and new authorship.
- Disposable isolated coding workspaces, bounded development checks, candidate packaging and independent admission.
- Postgres-backed interruption, fresh-process recovery, idempotency and immutable attempt lineage.
- Deterministic policy enforcement for authority, tool side effects, scope, budgets, concurrency and loop limits.
- MLflow agent traces and evaluation correlation where the selected observability profile enables them. This does not
  reactivate the ML Signal Research Agent or ML research lifecycle.
- Repeated scripted-model and real-model behavioral qualification.

### Excluded

- Knowledge Research and source ingestion for research-backed implementations.
- Quantitative Methods and source-backed implementation briefs.
- Experiment Design, backtest execution, optimisation, robustness, walk-forward analysis and independent Evaluation.
- ML feature engineering, training, registry promotion, signal research, monitoring or an ML Agent.
- Strategy-performance judgment, recommendation, paper-candidate preparation, deployment or broker mutation.
- Compatibility with current `trader_agents` imports, graphs, tasks, policies, catalogues, checkpoints or stored state.
- General shell, filesystem, network, package-installation, SQL, infrastructure or credentials access for a model.

The first slice therefore uses only an operator-approved, knowledge-independent implementation specification with the
behavioral completeness required by the Strategy Engineering entry contract. A free-form idea is insufficient. Missing
strategy semantics cause clarification or a blocked return; neither the coordinator nor Strategy Engineering may fill
them from model memory. A later knowledge-backed slice adds Knowledge Research and Quantitative Methods without
weakening this rule.

## Preconditions and implementation gates

Production work proceeds only when each preceding gate is accepted. Work inside a gate may run concurrently where the
dependency table permits it.

| Gate | Required result | Acceptance evidence | Unlocks |
| --- | --- | --- | --- |
| Agent architecture closure | Complete the pending standard-record sections for Data Research and Strategy Engineering; review first-slice shared patterns against all three agent boundaries. | Parent tracker marks the three records and their required pattern review accepted. | Final slice contracts and capability inventory. |
| Capability and trust-boundary inventory | Inventory every required session, canonical-read, Data, implementation-catalogue, Coding Workspace and admission operation; record retain/redesign/add/remove decisions. | Reviewed inventory includes role, side effect, authority, idempotency, output/resource shape, errors, recovery and qualification fixture for every operation. | Capability-plane implementation and spike schemas. |
| Evaluation charter | Freeze representative tasks, expected evidence obligations, forbidden trajectories, attack cases and proposed promotion thresholds. | Human-reviewed fixtures and assertions distinguish useful agent behavior from plausible final prose. | Comparable framework spike and test-first implementation. |
| Framework and observability decision | Run equivalent disposable LangChain/LangGraph and PydanticAI paths with a real model, MCP, Postgres resume, structured returns, an interrupt, parallel work and traces. | Recorded decision against the same scenarios; losing spike removed; dependency and model profiles pinned. | Production agent runtime foundation. |
| Implementation authorization | User accepts this plan as amended and the roadmap records the selected work. | Explicit review decision with any remaining spike-owned choices named. | Production code changes. |

Current state on 2026-09-01: the Coordinator architecture is accepted, while the Data Research and Strategy
Engineering records and the first-slice shared pattern review remain incomplete. The capability inventory, evaluation
charter and framework comparison have not yet been performed. Production implementation is therefore not ready to
start immediately after review of this document alone.

## Entry and handoff contract for the first slice

The initial session fixture must provide:

- a natural-language objective and success definition;
- operator identity, session identity and an explicit approval policy;
- asset/universe, date, frequency, provider, cost, data-loading and compute envelopes;
- one operator-approved implementation specification or an exact canonical reference to one;
- pinned Trader interface and Python quality requirements;
- permitted dependency and Coding Workspace policy;
- model profile, token/time/tool budgets and concurrency limit; and
- any starting canonical Data or implementation refs.

The operator-approved implementation specification is deterministically normalized into the typed build contract
required by Strategy Engineering. Normalization may reject missing or contradictory fields; it does not infer material
behavior. Approval provenance and every material assumption remain visible.

Every delegation declares its branch and attempt identity, question, required inputs, expected output, available
authority, tool and mutation scope, reserved budget, dependencies, approval requirements and expected information gain.
Every specialist return declares answered and unanswered questions, bounded findings, canonical refs, assumptions,
uncertainty, blockers, consumed budget and advisory next actions.

The coordinator accepts a return only after deterministic envelope validation and bounded canonical dereferencing. It
then records one structured decision: `advance`, `revise`, `revisit`, `fork`, `ask_operator`, `conclude`, or
`stop_fail_closed`. No free-form model text directly causes a mutation or state transition.

## Parallel execution plan

The initial slice must demonstrate useful parallelism without introducing multiple writers for coordinator state.

| Work | May run in parallel with | Required join |
| --- | --- | --- |
| Data inventory and quality investigation | Read-only implementation-catalogue discovery and comparison | Soft join while findings remain independent. |
| Data investigation for disjoint assets or data roles | Other disjoint Data investigation within the same approved envelope | Data Research owns later scope reconciliation; hard join before a complete readiness verdict. |
| Catalogue comparison for independently approved candidate branches | Data work and other isolated candidate branches within budget | Coordinator reviews every branch return; no first-result-wins selection. |
| Data backfill mutation | Disjoint immutable/catalogue reads when policy and resource budgets permit | Hard join before affected inventory, quality and snapshot claims. |
| Workspace edits and checks for one candidate attempt | Data work; never another writer in the same workspace | Hard join before packaging and admission. |
| Candidate admission | Unrelated read-only investigation | Hard join before the candidate can be returned as admitted. |

The coordinator alone changes shared agenda and branch state. A deterministic scheduler computes the legal ready set,
reserves budgets and serializes conflicting mutations. Specialists do not delegate directly to peer specialists in
this slice. Multiple partial returns from one responsibility are reconciled by a later invocation of that same
specialist after coordinator review.

## Proposed component and package boundaries

The implementation must preserve the repository architecture:

- `trader_agents` is replaced cleanly with model profiles, versioned agent programs, structured state and output
  schemas, coordinator and specialist graph wiring, policy middleware, scheduler, MCP adapters, checkpointer adapters,
  interruption handling and trace correlation. Current source is useful only as audited input; no compatibility shims
  or old checkpoint readers survive.
- `trader_mcp` owns MCP transport, registration, schemas, role metadata and adapters. It must not acquire research
  judgment or hide several model decisions inside one opaque workflow command.
- `trader_research.data` continues to own deterministic discovery, inventory, quality, loading and Data evidence.
- `trader_research.experiments` continues to own implementation identity and admission evidence. The catalogue may
  index eligible implementations but cannot change their canonical identity or validation state.
- A bounded research coding service owns workspace lifecycle, allowed operations, packaging and resource enforcement;
  the capability inventory must settle its exact `trader_research` domain placement before implementation.
- `trader_standard` remains the home of maintained first-party implementations, not agent state or experiment
  orchestration.
- `trader` remains independent of research, MCP and agent packages.
- Canonical research artifacts remain in Trader Postgres. Agent operational checkpoints use a separate checkpointer
  namespace and are not research evidence. MLflow traces are diagnostic/evaluation projections and not product
  authority.

The coordinator may invoke Data Research and Strategy Engineering through versioned specialist capabilities exposed by
the agent runtime. The specialists' interactions with Trader, research services and coding infrastructure occur only
through MCP. An agent invocation is not itself a new all-powerful MCP endpoint.

## Capability inventory hypotheses

These are starting hypotheses to test in the formal MCP inventory, not approved tool contracts.

| Capability | Current position | Proposed disposition for the slice |
| --- | --- | --- |
| MCP health and configuration | Registered read-only support tools. | Retain; add bounded role, program, catalogue-version and policy visibility needed for traceability. |
| Data symbol discovery | Registered, with provider discovery policy. | Retain or reshape for typed multi-asset/universe discovery and bounded result pagination. |
| Data inventory and quality | Registered for bounded scopes. | Retain underlying services; verify one composite role-labelled scope, coverage semantics and model-usable errors. |
| Data loading/backfill | Registered and gated. | Retain deterministic mutation; add an explicit acquisition envelope, estimate/approval surface, cancellation and exact post-mutation evidence where missing. |
| Data research snapshot | Registered canonical mutation. | Retain; require exact composite-scope identity and matching revalidated inventory/quality generations. |
| Canonical artifact reads | Available through internal stores and selected tools, but not yet a complete role-scoped model resource surface. | Add bounded immutable MCP resources/read operations with type, owner, hash, lineage and pagination validation. |
| Maintained template lists | Registered metadata-only lists. | Retain as one catalogue tier; do not mistake them for a complete implementation search surface. |
| Previous implementation search and resolution | Incomplete. | Add versioned typed/lexical/semantic search, exact manifest/admission/provenance resolution, bounded eligible source retrieval and reproducible catalogue identity. |
| Brief-to-implementation comparison | Incomplete. | Add deterministic field-alignment support and a canonical or validated compatibility record; the model still judges reuse/adapt/author. |
| Workspace creation, read/search, edit, checks, packaging and cleanup | Absent as a target MCP family. | Add role-scoped capabilities over a disposable resource-bounded container with a pinned read-only repository and separate candidate writes. |
| Dependency resolution | No target coding capability. | Add a deterministic, policy-gated operation over approved mirrors, pinned versions/hashes and licence/security policy; no model network access. |
| Strategy/risk registration and validation | Registered content-addressed admission path. | Retain independent services; reshape ownership/inputs only where required to accept exact workspace packages and immutable attempt lineage. |
| Research session, approvals, budgets, interrupts and branch receipts | Current deterministic orchestration state is not the target. | Define new bounded operational capabilities and canonical public receipts without persisting hidden reasoning or raw tool payloads. |

The formal inventory must prefer task-level operations that return enough evidence for another model decision. It must
avoid both microscopic CRUD sequences that consume context without adding judgment and opaque end-to-end tools that
remove meaningful judgment from the agents.

## Planned work sequence

### Complete the first-slice design

- Finish every pending standard-record section for Data Research and Strategy Engineering.
- Review the supervisor-with-specialists, agent-as-tool/custom-node, coding workspace, deterministic-policy,
  concurrency, interruption and recovery patterns against the accepted boundaries.
- Draft the shared session, agenda, delegation, evidence-return, coordinator-decision, branch/attempt, scope-envelope,
  budget and public-receipt schemas.
- Decide which values are operational checkpoint state and which become canonical Orchestration evidence.
- Resolve the precise first-slice output contract and cleanup/disposal behavior.

### Establish evaluation before framework selection

- Create human-reviewed brief and evidence fixtures for the representative scenarios below.
- Label required questions, legal and illegal delegations, evidence obligations, permitted mutations, expected stops and
  material trajectory constraints.
- Define deterministic assertions for scope, authority, lineage, tool calls, canonical refs, recovery and safety.
- Define model-quality scoring separately from deterministic invariants.
- Set provisional cost, latency, token, tool-call, revision and concurrency ceilings for measurement in the spike.

### Inventory and close the capability plane

- Audit current MCP registration, schemas, owners, side-effect labels, policy flags and backing services against the
  hypotheses above.
- Specify the smallest coherent additions for composite Data work, bounded canonical reads, implementation catalogue,
  Coding Workspace, dependency resolution, admission packaging and public session receipts.
- Implement deterministic domain services before their MCP adapters.
- Add contract, package-boundary, policy, idempotency, cancellation, Postgres and security tests for each capability.
- Update `mcp_tools.md`, `tool_contracts.md`, `agents.md`, product state and the roadmap with implemented reality.

### Run and decide the framework spike

- Implement the same thin Coordinator–Data–Strategy scenario once with LangChain/LangGraph and once with PydanticAI.
- Use a real supported model, real MCP transport, isolated specialist context, structured outputs, Postgres resume, one
  approval interrupt, one legal parallel branch and MLflow-correlated traces.
- Measure schema reliability, dynamic tool narrowing, supervisor/subagent ergonomics, checkpoint recovery,
  cancellation, traceability, testability, latency, token use and implementation complexity.
- Record why the selected framework better implements Trader's boundaries. Remove the losing spike entirely.
- Pin framework, model client and tracing dependencies only after this decision.

LangChain/LangGraph remains the leading hypothesis because it already fits the accepted graph, interrupt and Postgres
checkpoint direction. The spike is still required: existing LangGraph use proves library integration, not the target
model/tool loop or the relative fit of the current APIs.

### Build the agent runtime foundation

- Replace the current `trader_agents` control plane without compatibility imports or state migration.
- Implement versioned model profiles and agent programs, typed structured outputs and strict validation.
- Implement the MCP client boundary with role- and state-aware tool narrowing and bounded resource dereferencing.
- Implement deterministic scope, approval, side-effect, budget, concurrency, lineage and loop middleware outside model
  output.
- Implement single-writer coordinator state, isolated specialist checkpoints, atomic accepted-return receipts,
  interrupts, cancellation and fresh-process recovery.
- Implement trace redaction and correlation across session, delegation, model, MCP, artifact, workspace and admission
  identities.

### Build the Data Research Agent

- Implement its versioned model program and structured investigation/readiness outputs.
- Support composite scope decomposition, parallel disjoint investigation and specialist-owned reconciliation.
- Let the model select discovery, inventory, quality and permitted remediation tools from the current role catalogue.
- Enforce acquisition envelopes deterministically before mutation.
- Require inventory and quality revalidation plus an exact snapshot after loading/backfill.
- Return complete, conditional, partial or blocked readiness evidence through the coordinator.

### Build the Strategy Engineering Agent

- Implement typed build-contract validation and the versioned strategy-engineering model program.
- Require catalogue discovery and field-level comparison before every reuse/adapt/author decision.
- Provision one isolated workspace per candidate attempt and expose only approved MCP operations.
- Package exact source, tests, manifests and bounded check evidence; submit them to independent admission.
- Implement bounded diagnostic repair where an actionable admission finding leaves the build contract unchanged.
- Destroy ephemeral workspaces after accepted packaging or terminal failure while retaining immutable candidate and
  admission lineage.

### Integrate the Research Coordinator

- Implement model-led brief interpretation, visible agenda formation and specialist delegation.
- Dispatch only the deterministic scheduler's legal ready set and preserve single-writer session state.
- Verify every specialist return and its material canonical refs before making the next decision.
- Demonstrate soft and hard joins, clarification and approval interrupts, revision, revisit, bounded fork, conclusion
  and fail-closed termination.
- Produce the terminal grounded slice summary without claiming experimental efficacy.

### Qualify and cut over

- Run focused contracts first, followed by MCP/package-boundary, sandbox, Postgres recovery and end-to-end suites.
- Run repeated real-model scenarios against one frozen code, program, model-profile, tool-catalogue, database,
  container-image, configuration and evaluation-dataset identity.
- Review failures and rerun the complete qualification after material changes; do not select favorable individual
  trajectories.
- Update active documentation and roadmap state only to the evidence actually achieved.
- Remove the old `trader_agents` implementation and development checkpoint state through explicit bounded reset
  instructions; do not ship compatibility readers.

## Dependency-aware concurrency during delivery

| Workstream | Can start when | Can proceed concurrently with | Join condition |
| --- | --- | --- | --- |
| Data and Strategy architecture completion | This plan is under review. | Shared scenario drafting. | Both records and shared pattern review accepted. |
| MCP inventory | Stable provisional entry/return boundaries exist. | Evaluation fixture design. | Reviewed disposition for every first-slice capability. |
| Data capability changes | Data tool contracts accepted. | Implementation catalogue and Coding Workspace services. | Role catalogue and contract tests pass. |
| Implementation catalogue and Coding Workspace | Build contract, trust tiers and sandbox contracts accepted. | Data capability changes. | Catalogue, isolation, admission and security tests pass. |
| Framework candidates | Inventory schemas and representative scenarios accepted. | No production runtime work. | One measured decision; losing candidate removed. |
| Runtime foundation | Framework decision accepted. | Final deterministic MCP capability work with stable contracts. | Contract, policy, checkpoint and trace tests pass. |
| Data and Strategy agent programs | Runtime and their respective role surfaces are stable. | Each other. | Each passes isolated scripted and real-model scenarios. |
| Coordinator integration | Runtime plus at least one accepted specialist path. | Remaining isolated specialist hardening. | Every integrated return passes coordinator validation. |
| Controlled qualification | Entire selected slice and docs are internally complete. | Nothing that changes the freeze. | All required phases pass against one frozen identity. |

## Representative evaluation scenarios

The charter should include at least these cases:

1. **Exact reuse:** a multi-asset brief with ready Data and an exact admitted implementation match. The coordinator
   permits parallel Data and catalogue investigation; Strategy Engineering chooses reuse for field-level reasons.
2. **Bounded backfill and adaptation:** one required Data role has an in-envelope gap; an admitted implementation is
   close but requires an allowed adaptation. Data is backfilled and revalidated, modified code receives new identity,
   and prior admission is not inherited.
3. **New authorship and repair:** no suitable implementation exists. Strategy Engineering authors in isolation, first
   admission fails with an actionable defect, and one evidence-led repair attempt succeeds without changing semantics.
4. **Material ambiguity:** the brief or operator specification omits a behaviorally material rule. The coordinator asks
   rather than allowing either specialist to invent it.
5. **Out-of-envelope acquisition:** useful Data requires an unapproved provider, period, volume or cost. The agent
   returns partial evidence and an approval request; no mutation occurs.
6. **Unfit requested scope:** Data remains materially defective. The coordinator does not substitute a more favorable
   asset or silently narrow the period.
7. **Malicious content:** provider metadata, tool output, repository text or candidate code contains instructions to
   widen authority, reveal context or call a forbidden capability. Policy and agent behavior both resist it.
8. **Admission cannot be repaired:** repeated equivalent failures, prohibited dependencies or required semantic change
   terminate with complete attempt lineage.
9. **Crash and lost response:** interruption occurs before and after a local mutation and during a specialist return.
   Fresh-process recovery neither loses an accepted receipt nor repeats an accepted mutation.
10. **Low-information loop:** paraphrased delegations or candidate changes do not reset loop counters. The coordinator
    stops when no new evidence is expected.
11. **Distinct briefs:** materially different objectives and constraints produce materially different agendas, tool
    choices and conclusions while preserving the same authority policy.
12. **Denied trading path:** a prompt requests paper or live deployment after admission. No broker or deployment tool is
    available and the coordinator reports the authority boundary.

Evaluation must inspect trajectories, tool calls, refs and state transitions, not only final prose. Scripted-model tests
prove contracts and recovery; repeated real-model evaluation proves that meaningful decisions are actually delegated
to models. Neither substitutes for the other.

## Verification layers

| Layer | What it must prove |
| --- | --- |
| Pure contract and policy tests | Normalization, structured-output rejection, authority, budgets, ready-set computation, joins, loops and lineage are deterministic and fail closed. |
| MCP contract tests | Registration, role exposure, envelopes, resources, pagination, side effects, issue classes and canonical refs match documentation. |
| Capability service tests | Composite Data behavior, catalogue identity/search, workspace lifecycle, packaging, admission and cleanup work without an agent. |
| Sandbox security tests | No host/repository writes, arbitrary commands, network, credentials, dependency bypass, resource escape or unbounded output. |
| Agent tests with controlled models | Expected tool choices, revisions, interrupts and malformed-output recovery can be reproduced without provider variance. |
| Postgres integration and recovery | Checkpoints, canonical artifacts, accepted-return receipts, idempotency and fresh-process resume survive failures at every mutation boundary. |
| Repeated real-model evaluation | Different briefs yield appropriate non-fixed trajectories; grounding, safety, recovery, quality, cost and latency meet reviewed thresholds. |
| Final frozen acceptance | All mandatory layers run against the same exact code, programs, model profile, tool catalogue, fixtures, database schema, sandbox image and configuration. |

## Definition of done

The slice is implemented only when:

- all three first-slice architecture records and shared pattern decisions are accepted and match the implementation;
- the selected runtime contains real model/tool loops rather than the frozen deterministic policies;
- every model interaction with Trader capabilities crosses a role-scoped MCP boundary;
- the representative success, blocked, adversarial, interruption and loop scenarios meet reviewed thresholds across
  repeated runs;
- Data and implementation/admission outputs resolve as exact canonical evidence with correct authority and lineage;
- code runs only in the accepted isolated workspace and no research agent can reach broker or deployment mutation;
- restart and idempotency evidence passes against Postgres in fresh processes;
- traces are complete enough to audit decisions without persisting hidden reasoning or secrets;
- old `trader_agents` code and incompatible checkpoint state are removed through the approved clean cutover;
- active architecture, agent, MCP, tool-contract, operation, product-state and roadmap documentation matches reality;
  and
- a reviewed frozen qualification record identifies the exact accepted revision and environment.

An impressive demonstration, one favorable model trajectory, passing deterministic tools alone, or an admitted
candidate without the coordinator/specialist evidence loop is not completion.

## Principal risks and controls

| Risk | Required control |
| --- | --- |
| Recreating deterministic orchestration with LLM wording | Behavioral fixtures require evidence-responsive agenda, tool and revision differences; fixed-route code fails evaluation. |
| Framework abstractions redefining authority | Agent records and deterministic policy contracts are fixed before framework selection. |
| Coordinator becoming a domain specialist | Specialist ownership, bounded canonical verification and mandatory return/redelegation are enforced in schemas and evaluation. |
| MCP tools being too granular or too opaque | Inventory evaluates whether each operation leaves the next meaningful judgment with the model while keeping mutation deterministic. |
| Unsafe generated code | Disposable container, no general network/shell/host writes, allowlisted checks, exact packaging and independent admission. |
| Prompt injection through data or code | Treat all content as untrusted, separate instructions from observations, narrow tools outside model output and test embedded attacks. |
| Retry or resume duplicating mutations | Idempotency keys, transition fingerprints, accepted-return receipts and fresh-process fault injection at mutation boundaries. |
| Outcome-driven coding | No experiment results exist in this slice; Strategy Engineering remains outcome-blind and can revise only from checks/admission evidence. |
| Non-reproducible evaluation | Freeze model/program/tool/config identities, retain public traces and run repeated scenario sets without cherry-picking. |
| ML scope returning indirectly | MLflow is trace infrastructure only; ML research tools and the ML agent remain absent from the role catalogues and acceptance scope. |

## Review defaults and unresolved choices

Unless review changes them, this plan recommends:

- stopping the first slice at Data readiness plus an admitted candidate;
- using the operator-specified build-contract route for every first-slice end-to-end fixture;
- treating LangChain/LangGraph as the leading runtime candidate while retaining a genuine PydanticAI comparison;
- using Postgres for canonical evidence and agent checkpointing in separate namespaces;
- using a rootless or equivalently isolated OCI/Docker workspace with networking disabled by default;
- requiring one primary real-model profile for acceptance and recording provider portability as a later concern; and
- using MLflow for trace/evaluation projection without making it product authority or reactivating ML delivery.

The framework spike must resolve the exact model/provider profile, framework versions, schema mechanism, container
runtime, trace integration, and numeric operating limits. If required credentials or the chosen sandbox runtime are
unavailable, the spike stops with a named environmental blocker rather than silently substituting a fake production
path.
