# Research Capability Roadmap

This is the canonical active roadmap for Trader's research product. It translates the target in
[Agentic Research Orchestration Redesign](agentic_orchestration_redesign.md) and the accepted per-agent records in
[Agent Designs](agent_designs.md) into capability frontiers, dependencies, delivery status, and acceptance evidence.

Read [Research Product State](../docs/research_agents/product_state.md) first for what works today. Current package
boundaries, agent allowlists, MCP registration, tool contracts, workflows, and operations remain authoritative only for
implemented behavior.

Last reviewed: 2026-09-01.

## Roadmap Rules

- Architecture is named by stable responsibility, never by a delivery checkpoint or sequence number.
- The historical `ORCH-*` and `AGENT-*` identifiers are roadmap work-item labels only; completed identifiers are
  immutable lineage, and the product never names components after delivery checkpoints.
- Active agentic work uses responsibility names rather than checkpoint codes.
- A capability frontier records an outcome, its hard dependencies, current status, and acceptance evidence. It is not
  a presumed chronological slice.
- Workstreams may proceed concurrently when their hard dependencies are satisfied.
- Deterministic capability-plane work may advance without extending the frozen deterministic agent control plane.
- Implementation, qualification, and availability are reported independently.
- A capability is complete only when implementation, active documentation, tests, and declared evidence agree.
- Git history, freeze tags, and canonical Postgres acceptance records retain detailed delivery history. This roadmap
  does not duplicate implementation journals or verification transcripts.

## Status Vocabulary

| Field | Values |
| --- | --- |
| Work status | `ready`, `in_progress`, `blocked`, `deferred`, `superseded`, `complete` |
| Implementation | `absent`, `partial`, `implemented` |
| Qualification | `none`, `focused`, `integration`, `controlled` |
| Availability | `unregistered`, `registered`, `gated`, `operator_only`, `deferred` |

## Capability Dependency Graph

```text
DATA ────────────────────────────────────────────┐
SUPPLIED IMPLEMENTATION + SPECIFICATIONS ────────┼──> EXPERIMENT EXECUTION ──> REVIEW
KNOWLEDGE ── optional provenance ────────────────┘              │
                                                               ├──> ROBUSTNESS ──> WFO CORE
KNOWLEDGE ──> STRUCTURAL INGESTION ──> DOSSIER ──> IMPLEMENTATION BRIEF
                                                        │
                                                        └──> STRATEGY ENGINEERING
                                                                  │
                                                                  └──> IMPLEMENTATION + SPECIFICATIONS

ML FEATURES + TRAINING ──> MODEL VERSION ──> ML DEPLOYMENT ──> EXPERIMENT EXECUTION
                                                                            │
                                                                            └──> WFO ML EXTENSION

DESIGN + EVALUATION CHARTER ──> FRAMEWORK SPIKE ──> AGENT RUNTIME FOUNDATION
ROLE-SCOPED MCP ───────────────────────────────────────────────┘

AGENT RUNTIME FOUNDATION + CAPABILITY PLANE
  -> RESEARCH COORDINATOR
  -> DATA + STRATEGY ENGINEERING
  -> EXPERIMENT DESIGN + EXECUTION
  -> ROBUSTNESS + WALK-FORWARD + INDEPENDENT EVALUATION
  -> MLFLOW-BACKED COMPLEX SIGNALS
  -> GROUNDED RECOMMENDATION + OPERATOR PAPER-CANDIDATE REVIEW
  -> CONTROLLED AGENTIC QUALIFICATION
```

Orchestration is a cross-cutting capability. The first agentic vertical slice does not require every future specialist
tool family, but it does require real model decisions, role-scoped MCP, canonical evidence, safe code execution,
coordinator review of every specialist return, human authority, and behavioral evaluation.

Knowledge remains optional for an externally supplied implementation, but a claim of research-backed implementation
must traverse structural ingestion, a validated research dossier, and an accepted implementation brief before Strategy
Engineering authors code.

## Accepted Baseline

The baseline is the capability plane available for reuse on fitness, not a compatibility promise for `trader_agents`.

| ID | Capability | Implementation | Qualification | Availability | Evidence |
| --- | --- | --- | --- | --- | --- |
| BASE-KNOW | Knowledge ingestion and bounded methodology extraction through 33AB | implemented | integration | registered | Canonical Postgres source/evidence lineage and controlled regressions. |
| BASE-IMPL | Knowledge-independent implementation admission through 56A-D | implemented | controlled | registered | Accepted in `verification-57i-freeze-v6`. |
| BASE-EXP | Strategy, risk-stack and backtest specifications through 57A-C | implemented | controlled | registered; execution gated | Accepted in `verification-57i-freeze-v6`. |
| BASE-OPT | Provider-neutral optimisation and independent review through 57D-H | implemented | controlled for built-in engines | registered; execution gated | Built-in grid/random accepted in `verification-57i-freeze-v6`; optional providers remain separate. |
| BASE-DATA | Data discovery, manifests, quality, and bounded loading evidence | implemented | controlled | registered; loading gated | Realistic Data evidence graphs in the controlled baseline. |
| BASE-ARCH | `trader_research` bounded-context cutover through TRR-12 | implemented | controlled | operational | Requalified at the v6 freeze. |
| BASE-ML-RUNTIME | Runtime prediction and model-backed strategies through 39H-I | implemented | integration | registered; model loading gated | Commit `577c774`; focused, local MLflow, and isolated Postgres evidence, outside the v6 acceptance record. |

The deterministic orchestration freeze remains valid historical evidence:

- Tag: `verification-orchestration-v1-freeze`
- Revision: `b1f49bd2e8f71bedc4bd66724df756a5935f3eca`
- Profile: `controlled_orchestration_v1`
- Authority: `verification_control.orchestration_acceptance_records`
- Scope: caller-built Data and Experiment Design tasks, explicit approvals, and the fixed
  `supplied_implementation_to_evidence` workflow
- Exclusion: model planning, model-selected delegation/tools, free-form brief interpretation, dynamic replanning, ML,
  general robustness, walk-forward analysis, paper trading, and live trading

## Active Work Graph

### Research-backed implementation

The current 33AB subsystem is a bounded evidence baseline, not an implementation-ready multi-textbook research system.
The target design is canonical in
[Research-Backed Implementation Architecture](agentic_orchestration_redesign.md#research-backed-implementation-architecture)
and the current/target evidence boundary is recorded in
[Semantic Methodology Extraction](../docs/research_agents/semantic_extraction.md#planned-agentic-knowledge-to-implementation-path).

| Capability frontier | Status | Hard dependencies | Current deliverable | Acceptance evidence |
| --- | --- | --- | --- | --- |
| Knowledge-to-implementation design | in_progress | BASE-KNOW and current-tool/lineage audit | Approve the retrieval/understanding/citation distinction, Knowledge Research and Quantitative Methods boundaries, research-dossier and implementation-brief responsibilities, source/engineering decision split, fail-closed gaps, and downstream admission path. | Reviewed design covers distributed, multi-source, conflicting, and missing-detail cases without weakening exact claim provenance. |
| Textbook corpus and architecture benchmark | ready | BASE-KNOW; may proceed with design | Curate licensed/approved fixtures covering a local method, a book-scale composite framework, remote equations/state/algorithm stages, tables/figures, multiple editions, source conflict, a deliberately missing detail, and embedded prompt injection. Record the 33AB baseline. | Corpus, expert obligations/claims, expected conflicts/blockers, evaluation metrics, and baseline retrieval/dossier results are versioned and reviewed. |
| Structure-preserving source representation and retrieval | blocked | Accepted knowledge design and benchmark | Compare current page-text extraction with a layout-aware candidate; preserve typed hierarchy and provenance; add source maps and the simplest measured structural/iterative retrieval affordances. | Parsing/retrieval ablations meet reviewed claim-recall, provenance, cost, latency, and deterministic export thresholds on real textbook fixtures. |
| Multi-source research dossier | blocked | Structure-preserving retrieval, Agent runtime foundation, MCP inventory | Knowledge Research Agent iteratively satisfies evidence obligations, expands structural context, records exact cross-source claim spans, conflicts, gaps, and an immutable readiness verdict. | Dossier evaluation proves citation entailment, coverage, conflict retention, unsupported-fact control, bounded loops, recovery, and prompt-injection resistance. |
| Implementation brief and source-backed authoring | blocked | Passed dossier, Quantitative Methods and Strategy Engineering agent surfaces, BASE-IMPL | Validated brief with typed mathematics/algorithm/state/tests and separated source-backed versus engineering decisions; isolated code authoring and normal admission. | Accepted briefs yield faithful admitted candidates; ambiguous or missing material detail blocks before code; source fidelity never substitutes for experimental evidence. |
| Controlled research-backed implementation qualification | blocked | Accepted end-to-end knowledge-backed surface | Freeze sources, parsers, embeddings/indexes, agent programs, model profiles, tool catalog, evaluation corpus, code, configuration, and environment; run repeated real-model qualification. | Reviewed thresholds pass for claim recall, citations, coverage, conflict/gap handling, implementation fidelity, safety, recovery, cost, and latency. |

### Orchestration

The target is a clean replacement of `trader_agents`. No source, state, graph, checkpoint, prompt, task, catalog,
workflow, or import compatibility is required. The detailed design and behavioral scenarios are canonical in
[Agentic Research Orchestration Redesign](agentic_orchestration_redesign.md).

| Capability frontier | Status | Hard dependencies | Current deliverable | Acceptance evidence |
| --- | --- | --- | --- | --- |
| Design and evaluation charter | complete | Current-state, dependency, and lineage audit | The approved temporary [First Agentic Implementation Slice plan](agent_designs/first_agentic_slice_implementation_plan.md), complete Coordinator/Data/Strategy records, accepted shared patterns, representative scenarios, deterministic invariants, and layered qualification contract define the slice. Other specialist records continue later; ML is parked. | Every first-slice agent has an accepted complete record, slice-wide patterns preserve those boundaries, representative scenarios are labelled, and deferred decisions cannot leak into the slice. |
| MCP capability and trust-boundary inventory | complete | Accepted slice charter | The canonical first-slice inventory in `docs/research_agents/tool_contracts.md` records every support, session, canonical-read, Data, catalogue, Coding Workspace, and admission operation. Candidate writes and cleanup use source-free replay records; provider-backed Data loading uses prepared and terminal canonical operation evidence and fails closed when post-interruption state is ambiguous. | Every operation records role, side effect, approval, idempotency/recovery, public output/errors, disposition, and one or more cases in `first-agentic-slice-evaluation-v1`. |
| Framework and observability spike | complete | Approved first-slice charter and representative scenario fixtures | The real-model comparison selected LangGraph 1.2.2 plus the 3.1.x Postgres checkpointer over PydanticAI 2.37.0 for control-runtime fit. Both used strict schemas, dynamic narrowed tool choices, real MCP, parallel work, evidence-led revision, PostgreSQL resume, interrupts, and queryable MLflow traces across two different briefs; the disposable code was removed. | Different briefs changed agenda digests, Data tool choice, evidence gaps, and coordinator action. Four recorded trace IDs resolved; LangGraph resumed natively after a new connection, while PydanticAI required custom checkpoint/control glue. |
| Agent runtime foundation | in_progress | Accepted framework spike | Clean `trader_agents` cutover is implemented with model profiles, agent-program identity, MCP adapters, role-aware dynamic tools, context policy, budgets, delegation/evidence-return/coordinator-decision contracts, branch lineage, loop guards, bounded source-free coordinator and specialist Postgres state, interrupts, trace correlation, runtime composition, and CLI. Focused tests prove specialist resume through a fresh PostgreSQL connection without repeating an accepted read. Provider backfill now requires a costed matching dry-run plan, runtime-bound lineage, and a canonical prepared/terminal operation journal that suppresses provider replay. Full coordinator recovery, security, MLflow, and operational qualification remain. | Contract, policy, persistence, security, and fresh-process tests prove model/tool loops without direct platform access or replayed mutations. |
| Coordinator evidence-review loop | in_progress | Agent runtime foundation | The implemented Coordinator rejoins every specialist return, independently reads canonical refs, records append-only decision receipts, and can revise, revisit, fork, ask, conclude, or fail closed. Agenda policy now admits disjoint Data and Strategy catalogue fan-out, enforces specialist-owned hard joins, derives mutation locks from trusted scope, and preserves unfinished delegation identity across a soft join. Broader behavioral and production recovery evidence remains. | Poor/promising/stable/unstable scenarios produce evidence-consistent decisions; equivalent loops, exhausted budgets, contaminated evaluation, and out-of-authority actions stop before mutation. |
| First agentic implementation slice | in_progress | Accepted first-slice charter, focused MCP inventory, accepted framework spike, Agent runtime foundation, BASE-DATA, BASE-IMPL | Research Coordinator, Data Research Agent, and Strategy Engineering Agent loops are implemented over role-scoped Data, implementation-catalogue, Coding Workspace, admission, session, and canonical-read capabilities. Multi-asset Data readiness, exact reuse, isolated authoring/admission, parallel join, evidence verification, bounded repair, interrupt, runtime, and CLI paths have focused tests. Source-free specialist checkpoints, replay-safe candidate and Data mutations, and deterministic immutable-package registration close the current local recovery/trust gaps; complete end-to-end qualification remains open. | Real-model natural-language tasks produce materially different agendas; multi-asset Data discovery/backfill/revalidation, implementation comparison, reuse/adapt/author choice, isolated code revision after failed admission, canonical handoff, restart, interrupt, prompt-injection resistance, bounded loops, and denied scope paths work end to end across repeated runs. |
| Prospective experiment loop | blocked | Coordinator evidence-review loop, First agentic implementation slice, BASE-EXP, BASE-OPT | Experiment Design Agent plus coordinator-invoked deterministic MCP execution/job services for prospective protocols, approvals, baseline/comparison execution, bounded search, successor protocols, and branch lineage. | All trials remain visible; in-scope tuning, out-of-scope tuning, new asset scope, early stop, and result-driven redesign preserve approval, multiplicity, and sealed evidence. |
| Robustness, walk-forward, and independent evaluation | blocked | Prospective experiment loop, ROB-2, REV-2, WFO-2 | Robustness & Walk-Forward Agent plus context-isolated Evaluation Agent over immutable variants, folds, stitching, attribution, and critique. | Stable, unstable, incomplete, and contradictory returns route correctly; negative findings and dissent survive coordinator synthesis. |
| Complex-signal agent lifecycle | parked | Agent runtime foundation, ML-1 through ML-7 | Intentionally deferred until the first non-ML agentic implementation slice is qualified. | Future reactivation requires an explicit roadmap decision; Trader and MLflow lineage, promotion authority, leakage, parity, robustness, and WFO evidence remain mandatory. |
| Recommendation and paper-candidate review | blocked | Independent Evaluation, coordinator evidence-review loop | Grounded coordinator synthesis and an operator-approved candidate record handed to a separate deterministic paper-trading preparation workflow. | Conclusions cite canonical evidence and dissent; research agents cannot deploy, start sessions, submit orders, clear halts, or mutate brokers. |
| Controlled agentic qualification | blocked | Accepted end-to-end target surface | Freeze code, agent programs, tool catalog, model profiles, evaluation datasets, configuration, and environment; run repeated real-model qualification. | Reviewed thresholds pass for brief interpretation, evidence review, routing, replanning, loop termination, scientific quality, grounding, independence, human authority, security, recovery, scale, cost, and latency. |

### Current design decisions

- The Research Coordinator is the only default user-facing agent and reviews every specialist return.
- Specialists return structured findings and canonical artifact refs; their recommended next steps are advisory.
- The coordinator can assess evidence for routing but cannot replace the independent Evaluation verdict or overwrite a
  specialist artifact.
- Returning to earlier work creates a new immutable attempt or branch; completed evidence is never rewritten.
- Hyperparameters may be explored only inside a prospective search space and budget. Changes outside it require a
  successor protocol and approval.
- A new asset pair is a new research branch with fresh Data evidence and an expanded multiplicity record unless the
  operator brief forbids exploration, in which case the coordinator interrupts or stops.
- Walk-forward or sealed evidence may motivate a successor hypothesis but cannot be reused as untouched confirmation
  after tuning.
- Repeated materially equivalent delegations without new evidence, exhausted limits, and decisions outside coordinator
  authority fail closed.
- Exact immutable source elements and claim spans are citeable evidence. Source maps and model-generated
  section/chapter summaries are versioned navigation artifacts only.
- Knowledge Research owns iterative source investigation and a cross-source research dossier. Quantitative Methods owns
  the implementation brief; Strategy Engineering authors code only from an accepted brief for knowledge-backed work.
- A research dossier must distinguish corroboration, complementary evidence, conflict, edition differences, and gaps.
  Sources do not vote by count, and material missing detail blocks rather than being supplied from model memory.
- Source-backed method decisions and Trader engineering decisions are recorded separately. Provenance fidelity does not
  imply trading efficacy, which still requires prospective experiments, robustness, walk-forward analysis, and
  independent Evaluation.
- LangChain/LangGraph is the recommended runtime, subject to the framework spike. DSPy is an offline measurable-program
  optimization layer. MLflow is the planned model plus agent trace/evaluation surface. MCP is the capability boundary.
- Research agents may recommend paper-trade review but never mutate a live or paper broker runtime.

### Charter review progress

The canonical working records are in [Agent Designs](agent_designs.md). Acceptance below records design-review
agreement only; it does not claim implementation or qualification.

| Decision area | Review state | Recorded position |
| --- | --- | --- |
| Standard agent architecture record | accepted | Every agent is specified by mission, exclusive decisions, entry/context/trust/model/tool boundaries, control loop, state, evidence return, termination, evaluation, concurrency, and handoff rules. |
| Research Coordinator authority | accepted | Broad evidence-constrained routing authority; no specialist-evidence override, self-approval, scope expansion, code/model admission, or trading authority. |
| Research Coordinator architecture | accepted | The canonical [Research Coordinator design](agent_designs/research_coordinator.md) defines a model-backed supervisor, structured delegations/decisions, bounded context, read-only evidence verification, single-writer session state, durable public decision evidence, and fail-closed termination. |
| Parallel coordination | accepted | Independent specialist invocations and deterministic jobs may run concurrently; policy computes the ready set; every return rejoins the coordinator; conflicting mutations, approvals, coordinator transitions, and evidence-dependent stages remain serialized. |
| Data Research Agent architecture | accepted | The complete [Data Research design](agent_designs/data_research.md) records multi-asset scope, dynamic role-scoped MCP, readiness/backfill authority, model/tool loop, durable state, evidence return, termination, evaluation, concurrency, and handoff boundaries for the first slice. |
| Knowledge Research Agent architecture | in_review | Existing iterative multi-source research, exact-evidence, dossier, and fail-closed decisions are consolidated in the [Knowledge Research design](agent_designs/knowledge_research.md). Model-selected MCP registration and ingestion inside a session-approved source envelope are accepted; the remaining standard record is pending. |
| Quantitative Methods Agent architecture | in_review | The [Quantitative Methods design](agent_designs/quantitative_methods.md) accepts one pre-code, outcome-blind responsibility and assigns behaviorally material Trader integration decisions to the brief while leaving non-semantic software design to Strategy Engineering. The remaining standard record is pending. |
| Strategy Engineering Agent architecture | accepted | The complete [Strategy Engineering design](agent_designs/strategy_engineering.md) records typed build contracts, mandatory MCP comparison, exact-version trust/re-admission rules, isolated Coding Workspace, outcome isolation, admission-repair, durable state, evidence return, termination, evaluation, concurrency, and handoff boundaries for the first slice. |
| Experiment Design Agent architecture | in_review | The [Experiment Design design](agent_designs/experiment_design.md) owns the prospective experiment charter, claims, protected-evidence roles, stage gates, budgets, and authority envelope. Detailed robustness/WFO design belongs to the specialist; research-question and hypothesis latitude remain under review. |
| Experiment execution boundary | accepted | Main-protocol execution has no separate LLM identity. The Research Coordinator invokes specialized deterministic MCP protocol execution/job capabilities; code owns compilation, scheduling, retries, reconciliation, persistence, and resource enforcement. RWFO invokes its own plan-pinned execution surface. |
| Robustness & Walk-Forward Agent architecture | in_review | The [Robustness & Walk-Forward design](agent_designs/robustness_walk_forward.md) owns staged multi-agent plan synthesis and direct plan-pinned specialist execution. A validated plan may proceed inside the approved envelope; material or out-of-envelope decisions interrupt. The remaining standard record is pending. |
| Specialist architecture records | in_progress | Coordinator, Data Research, and Strategy Engineering are complete for the first slice; later specialist records remain under review or parked. |
| Shared agent design-pattern review | accepted for first slice | Supervisor/specialist capabilities, custom loops, deterministic policy, single-writer coordination, specialist reconciliation, isolated coding, joins, recovery, and context isolation are recorded in [Agent Designs](agent_designs.md). Later slices must repeat the review for their added boundaries. |

### Gating decision register

| Decision | Current position | Resolve in | Blocks |
| --- | --- | --- | --- |
| Primary agent runtime | LangChain/LangGraph recommended; PydanticAI is the comparison, not a parallel production stack. | Framework and observability spike | Agent runtime foundation. |
| First supported model profiles | Provider-neutral profile contract agreed; concrete providers/models not selected. | Charter for requirements, spike for exercised profiles | Runtime implementation and evaluation thresholds. |
| MCP tool disposition | Existing catalog is evidence, not a target promise. | MCP capability inventory | Role-aware agent tools and specialist slices. |
| Textbook parser and canonical source structure | Current `pypdf` page text is the baseline; Docling is the leading layout-aware candidate, conditional on real-corpus stability, provenance, quality, licence, and cost evidence. | Textbook corpus and architecture benchmark | Structural source representation and retrieval. |
| Hierarchical retrieval complexity | Begin with typed document hierarchy plus agent-controlled existing hybrid search; add recursive summaries or a claim/concept graph only for measured gain. | Knowledge benchmark and ablations | Multi-source dossier implementation and operating cost. |
| Dossier, method-card, and brief relationship | Dossier owns the research session and cross-source claims; brief owns the coding handoff; whether composite work also publishes one or several method cards remains open. | Knowledge design review | Artifact schemas, validation, and source-backed authoring. |
| Source precedence and conflicts | Source suitability and declared edition/authority rules replace source-count voting; material unresolved conflict branches a variant or blocks. Exact precedence policy remains open. | Knowledge design and expert corpus review | Dossier validation and coordinator routing. |
| Long-running operation model | Synchronous bounded calls versus MCP jobs remains open. | MCP inventory and framework spike | Backtest, optimisation, WFO, and training recovery design. |
| Strategy coding sandbox | Ephemeral resource-bounded workspace accepted: pinned read-only repository, separate candidate writes, no general network/secrets, MCP-only commands, and policy-gated pinned dependencies. Concrete container, mirror, limits, and schemas are spike-owned. | Framework and observability spike | Strategy Engineering implementation. |
| Approval envelope | Human authority boundaries are agreed; environment-level pre-approval profiles and cost thresholds remain open. | Design charter | Mutation middleware and operator interrupts. |
| Evidence-routing criteria | Labels are brief/protocol-relative; concrete poor/promising/WFO-readiness fields remain open. | Design/evaluation charter | Coordinator program and scenario labels. |
| Loop material-change policy | Immutable lineage and fail-closed repetition are agreed; initial revision/fork limits remain measurement-driven. | Charter plus framework measurements | Coordinator dispatch guards and controlled qualification. |
| Agent-program storage | Git/Trader/MLflow authority split needs exact artifact identities and promotion flow. | Framework spike | Program loading, trace correlation, and release freeze. |
| Behavioral promotion thresholds | Evaluation dimensions and scenario families are agreed; numeric quality/cost/latency thresholds await baseline runs. | Framework spike and expert review | Production promotion and controlled agentic qualification. |
| Recommendation role | Coordinator synthesis is the initial target; a separate agent requires measured independence benefit. | Robustness/Evaluation vertical slice | Final recommendation composition only. |

### Deterministic capability-plane work

These capabilities are independently useful and supply target agent tools. Their IDs are capability lineage, not
architecture names.

| ID | Capability | Status | Hard dependencies | Enables |
| --- | --- | --- | --- | --- |
| ML-1 | MLflow runtime and mutation policy | ready | BASE-OPT | Dependency-ready but not selected while ML delivery is parked. |
| ML-2 | Point-in-time feature-set engineering | ready | BASE-DATA, BASE-IMPL | Dependency-ready but not selected while ML delivery is parked. |
| ML-3 | Training datasets and chronological split plans | blocked | ML-2 | Future training admission and model-aware WFO. |
| ML-4 | Training pipeline admission, fitting and run reconciliation | blocked | ML-1, ML-3 | Future predictive evaluation. |
| ML-5 | Predictive evaluation and comparison | blocked | ML-4 | Future immutable model versions. |
| ML-6 | Immutable model versions and promotion evidence | blocked | ML-5 | Future complete model-to-strategy chain. |
| ML-7 | Prediction monitoring and drift | ready | BASE-ML-RUNTIME | Dependency-ready but not selected while ML delivery is parked. |
| QUAL-ML-RUNTIME | Controlled qualification of runtime prediction | ready | BASE-ML-RUNTIME | Dependency-ready but not selected while ML delivery is parked. |
| ROB-1 | General immutable attack and variant contracts | ready | BASE-EXP, BASE-OPT | General robustness and WFO. |
| ROB-2 | Cost, window, concentration, perturbation and regime execution/judgment | blocked | ROB-1 | Robustness agent, WFO audit, and Evaluation. |
| REV-1 | General return attribution | ready | BASE-EXP | Broader Evaluation. |
| REV-2 | Broader skeptical Evaluation | blocked | REV-1, ROB-2 | Independent agent verdict and recommendation constraints. |
| REV-3 | Evaluation and Adversarial specialist graphs under the frozen policy shell | superseded | ORCH-1, REV-2, ROB-2 | Replaced by the clean agent runtime. |
| REC-1 | Recommendation and synthesis contracts | blocked | REV-2, ROB-2 | Grounded recommendation artifacts and paper-candidate review. |
| WFO-1 | Strategy walk-forward core | blocked | BASE-OPT, ROB-1 | Strategy WFO and ML extension. |
| WFO-2 | Stitched OOS Evaluation and independent audit | blocked | WFO-1, ROB-2 | Audited strategy WFO. |
| WFO-ML | Model-training walk-forward extension | blocked | WFO-1, ML-4, ML-6 | Future audited model-aware WFO. |
| DATA-1 | Calendar-aware market-data quality | ready | BASE-DATA | Better equity data evidence. |
| KNOW-1 | Composite methodology representation | deferred | BASE-KNOW | Better book-scale method evidence. |
| PERF-1 | Compiled-kernel conformance and acceleration | deferred | None | Runtime optimization when profiling justifies it. |

`KNOW-1` remains the deferred lineage of the old deterministic composite-card proposal. The active research-backed
implementation frontiers do not assume that proposal is the right artifact model; the design/benchmark decides which
existing evidence contracts are retained by fitness.

### Frozen deterministic orchestration lineage

These rows exist only to locate the implemented and qualified surface. They do not define the target architecture.

| ID | Capability | Status | Hard dependencies | Current position |
| --- | --- | --- | --- | --- |
| ORCH-0 | Product-state and roadmap cutover | complete | None | Historical foundation. |
| ORCH-GOV | Decision authority and domain ownership redesign | complete | ORCH-0, BASE-ARCH | Current artifact-authority metadata remains reusable on fitness. |
| ORCH-1 | Capability and workflow contracts | complete | ORCH-GOV | Frozen objective/protocol/workflow declaration surface. |
| ORCH-2 | Operational checkpoint and handoff model | complete | ORCH-1 | Frozen deterministic resume shell. |
| ORCH-3 | Deterministic implementation-to-evidence workflow | complete | ORCH-1, ORCH-2, BASE-DATA, BASE-EXP, BASE-OPT | Frozen fixed compiler/executor. |
| ORCH-4 | Bounded Research Coordinator planning policy | complete | ORCH-3 | Frozen model-free coordinator policy. |
| AGENT-1 | Specialist graph contract and common policy shell | complete | ORCH-1 | Frozen deterministic shell; not the target agent contract. |
| AGENT-DATA | Integrate Data Agent as a resumable specialist | complete | ORCH-2, AGENT-1 | Frozen deterministic Data route. |
| AGENT-DESIGN | Experiment protocol proposal and specialist graph | complete | AGENT-1, BASE-IMPL, BASE-DATA, BASE-EXP | Frozen deterministic Design route. |
| ORCH-5 | Multi-specialist composition | complete | ORCH-4, AGENT-1, AGENT-DATA | Frozen caller-built composition. |
| ORCH-6 | Controlled orchestration qualification | complete | ORCH-3, ORCH-4, ORCH-5, AGENT-DESIGN | Accepted only for `controlled_orchestration_v1`. |
| AGENT-QUANT | Quant Methods specialist under the frozen policy shell | superseded | AGENT-1 | Replaced by the model-backed target. |
| AGENT-ML | ML specialist under the frozen policy shell | superseded | AGENT-1, ML-6, ML-7 | Replaced by the model-backed target. |
| AGENT-HYP | Hypothesis graph under the frozen control model | superseded | ORCH-1 | No initial standalone target agent. |
| RUNNER-1 | High-level deterministic experiment runner | superseded | ORCH-3, REV-2, ROB-2 | Replaced by coordinator-led dynamic research. |

The workflow executor owns no research claim and is not an agent. The implementation lineage is `e3f7d85` for
declaration/authority contracts, `6cbc886` for checkpoint responsibility, and `28c1d33` for fixed MCP execution.

#### Implemented Research Composition

The frozen composition accepted explicit `ResearchCompositionRequest` and `SpecialistTask` values, selected registered
routes, stored `AcceptedSpecialistResult` receipts, and returned canonical input URIs without replaying accepted steps.
It used `SpecialistDecision`, `SpecialistActionCatalog`, `SpecialistActionOutcome`, `SpecialistResult`, and
`SpecialistRouteCatalog`. It did not infer tasks from prose or perform model-selected routing.

#### Implemented Data Specialist Cutover

The frozen Data route used `DataSpecialistRequest` and the registered actions `validate_market_data_scope`,
`ensure_market_data_available`, and `capture_market_data_evidence`. It returned canonical manifest/quality refs and
proved fresh-saver resumption without repeating accepted actions. The former graph was removed without compatibility
aliases; the cutover was completed without compatibility aliases.

#### Implemented Experiment Design Specialist

The frozen Design route created one immutable protocol proposal over caller-supplied fields and canonical Data refs,
then paused for explicit operator decisions. It could not interpret a free-form brief, revise after results, or approve
its own assumptions.

#### Controlled Orchestration Qualification Plan

The accepted freeze passed `ORCHESTRATION_RUNTIME`, `ORCHESTRATION_CORE`, `ORCHESTRATION_E2E`,
`ORCHESTRATION_RECOVERY`, `ORCHESTRATION_POLICY`, `ORCHESTRATION_SCALE`, and `ORCHESTRATION_ACCEPTANCE`. Exact terminal
replay, policy isolation, real Postgres/MCP execution, and controlled scale apply only to the frozen deterministic
surface.

## Current Ready Queue

The selected delivery focus is the first Coordinator–Data–Strategy agentic slice. Work proceeds in this order:

1. Preserve the accepted Research Coordinator, Data Research, Strategy Engineering, and shared first-slice pattern
   records as implementation constraints.
2. Preserve the reviewed operation inventory and `first-agentic-slice-evaluation-v1` fixture as build constraints.
3. Finish production qualification of the implemented LangGraph runtime foundation, especially fresh-process
   PostgreSQL recovery, idempotency, trace correlation, security, and runtime composition.
4. Qualify the implemented Data Research, Strategy Engineering, and Coordinator loops against real MCP and Coding
   Workspace boundaries, including failed-admission repair and denied-scope cases.
5. Qualify the production slice across the frozen 12-scenario dataset with repeated real-model runs before extending into Experiment
   Design and coordinator-invoked deterministic experiment execution.

Knowledge-backed authoring, RWFO, and Evaluation design may continue without expanding the first implementation slice.
All ML agent and ML capability work is parked. Independent non-ML deterministic frontiers remain available only when
they directly unblock the selected slice.

This is a choice of parallel frontiers inside the selected slice, not an instruction to reactivate parked work or
execute every dependency-ready capability.

## Target Agent Capability Map

| Agent | Target decisions | Required capability plane | Decision outputs |
| --- | --- | --- | --- |
| Research Coordinator | Interpret briefs, review every specialist return against canonical evidence, create/revise the agenda, advance/revise/revisit/fork/execute/ask/conclude/stop, enforce budgets, reconcile findings, and synthesize cited conclusions. | Agent runtime, read-only artifacts/comparisons, Research Session MCP, branch/loop/budget state, specialist delegation, and approved-main-protocol execution/job tools. | Evidence-review decisions, agenda/branch revisions, delegations, execution invocations, approval requests, fail-closed stops, synthesis, and optional candidate proposal. |
| Data Research Agent | Choose discovery, ingestion, quality, and remediation actions; judge fitness for the requested research. | Data MCP, BASE-DATA, DATA-1. | Dataset/quality refs, acquisition requests, fitness findings, and blockers. |
| Knowledge Research Agent | Decompose evidence obligations; inspect approved source structure and quality; iteratively retrieve/expand exact evidence; reconcile multi-source support, conflicts, and gaps; judge dossier readiness. | Knowledge MCP, BASE-KNOW, typed source hierarchy/maps, bounded evidence resources, dossier validation. | Research dossiers, exact cross-source claim refs, suitability findings, conflicts, gaps, and blocked/readiness verdicts. |
| Quantitative Methods Agent | Translate a passed dossier into an exact source-faithful quantitative specification before code or outcomes exist. | Validated dossiers, method contracts, formal/reference checks, Trader interface constraints, and implementation-brief validation. | Accepted or blocked implementation briefs, separated source/engineering decisions, formal checks, caveats, and evidence-gap requests. |
| Strategy Engineering Agent | Reuse, adapt, or author strategy/risk code from supplied requirements or an accepted implementation brief; diagnose failures and submit candidates for independent admission. | Accepted briefs where knowledge-backed, isolated Coding Workspace MCP, and BASE-IMPL. | Candidate packages, validation refs, limitations, and revisions. |
| Experiment Design Agent | Design the prospective experiment charter: hypothesis, baseline/selection protocol, evidence partitions, protected-stage envelopes, criteria, budgets, costs, material assumptions, and successor protocols. | BASE-EXP, BASE-OPT, Data and implementation evidence. | Protocol proposals, evidence-stage/authority envelopes, and approval requests. |
| Robustness & Walk-Forward Agent | Synthesize relevant agent evidence into a staged attack/WFO plan; after validation and approval, operate specialist tools, recover bounded jobs, and inspect sensitivity and stitched out-of-sample behavior. | Experiment Design charter plus canonical Data, method, strategy, execution, ML, and prior-review refs; ROB-1, ROB-2, WFO-1, WFO-2. | Immutable robustness/WFO plans, execution evidence, sensitivity findings, dissent, blockers, and successor requests. |
| ML Signal Research Agent (parked) | Future choice of point-in-time features, training/evaluation design, model family, tuning, registry, and drift investigation. | Parked ML-1 through ML-7, MLflow, and model-backed execution. | Future feature, training, model-version, predictive-evaluation, parity, prediction, and drift refs. |
| Evaluation Agent | Independently judge leakage, selection bias, costs, robustness, completeness, and alternative explanations. | REV-1, REV-2, and read-only canonical evidence. | Evaluation verdict, cited dissent, missing-evidence requests, and recommendation constraints. |

Hypothesis formation initially belongs to Experiment Design with Strategy Engineering, Quantitative Methods, and
Knowledge Research support.
Recommendation synthesis initially belongs to the coordinator and cannot override Evaluation. Validators, accounting,
backtest/optimisation engines, risk pipelines, persistence, and policy enforcement are deterministic services rather
than agents.

## Historical Lineage Index

Detailed obsolete plans have been removed from the active `plans/` directory. Git remains the historical authority.

| Legacy work | Resulting capability | Current position |
| --- | --- | --- |
| 1-32 | Initial MCP, Data, Knowledge, strategy, and backtest foundations | Historical foundation; current contracts supersede early forms. |
| 33A-33AB | Postgres-first knowledge ingestion and methodology evidence | Implemented bounded methodology subsystem. |
| 33AC | Composite methodology architecture | Mapped to `KNOW-1`; deferred. |
| 34-48 | Deterministic supervisor/specialists, ML, review, robustness, and recommendation concepts | Useful domain lineage; old agent-control work is superseded by the redesign. |
| 39H-I | Runtime prediction and strategy integration | Implemented at `577c774`; further `QUAL-ML-RUNTIME` work is parked. |
| 53-54 and TRR-1 through TRR-12 | Documentation and `trader_research` bounded-context refactor | Implemented and requalified. |
| 56A-D | Knowledge-independent implementation admission | Controlled accepted baseline. |
| 57A-H | Specifications, backtests, optimisation, review, and tracking projection | Controlled accepted baseline. |
| 57I-S | Frozen Postgres/MCP qualification and acceptance | Controlled at `verification-57i-freeze-v6`. |
| 58-59 | Walk-forward optimisation and review | Mapped to `WFO-1`, `WFO-2`, and `WFO-ML`. |
| 60 | Calendar-aware Data quality | Mapped to `DATA-1`. |

The final deprecated linear tracker is available with:

```bash
git show 577c774:plans/mcp_trading_research_tools_plan.md
```

## Completion Policy

Before marking an active frontier complete:

1. Verify every hard dependency and input artifact contract.
2. Implement through the owning package and MCP boundary without compatibility layers unless explicitly approved.
3. Test deterministic behavior directly, then agent trajectories, persistence, human interrupts, security, and real
   integration in proportion to the changed surface.
4. Update product state, architecture, agent boundaries, MCP catalog, contracts, workflows, operations, and this roadmap
   only where behavior actually changed.
5. Record model, agent-program, tool-catalog, evaluation-dataset, configuration, code, and environment identities for
   any agentic qualification claim.
6. Report behavioral quality across repeated runs; do not promote one successful trajectory to controlled evidence.
7. Preserve canonical negative evidence, dissent, branch lineage, multiple-testing records, and operator decisions.
8. Confirm research agents remain outside paper/live broker mutation and that final promotion authority is human.
