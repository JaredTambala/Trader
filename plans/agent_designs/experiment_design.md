# Experiment Design Agent Design

Design status: architecture review in progress; this document does not authorize implementation.

Last reviewed: 2026-10-09 (complete architecture proposal; human acceptance pending).

This document is the canonical build-lifecycle architecture record for the Experiment Design Agent. Review status and
shared principles are maintained in the parent [Agent Designs](../agent_designs.md) workbook. System-level direction
remains in [Agentic Research Orchestration Redesign](../agentic_orchestration_redesign.md). Work assignment and delivery
progress are maintained in Notion's
[Trader Work Items](https://app.notion.com/p/31131085ffc54c329f25445843e9ac52).

## Established design constraints

The system-level review and frozen deterministic baseline establish these starting constraints:

- The agent designs a prospective, falsifiable, reproducible experiment over canonical candidate and Data evidence
  before execution results exist.
- It owns the prospective experiment charter: claims and falsification criteria, baselines, comparisons, metrics,
  evidence partitions, costs, constraints, parameter-search spaces, multiple-testing controls, protected-stage
  envelopes, execution bounds, stage gates, and stop rules.
- Material assumptions are explicit and carry requested approvals. The agent cannot approve its own proposal or treat a
  code-owned default as operator consent.
- A protocol proposal is immutable. Approval preserves its exact design identity; changing a material field creates a
  different proposal.
- The agent does not execute experiments, inspect sealed evidence while designing the protocol, select a winner after
  the fact, or issue the final strategy-quality verdict.
- Result-driven redesign creates a separately identified successor protocol and preserves predecessor evidence,
  branch lineage, expanded multiplicity, and any contaminated holdout status.
- Hypothesis formation initially remains inside Experiment Design rather than creating a separate Hypothesis Agent,
  unless evaluation later proves that context-isolated divergent ideation materially improves research quality.

## Proposed mission

Turn a Coordinator-delegated research question into a falsifiable hypothesis brief before candidate construction when
one is needed, then turn an accepted brief, admitted candidates, and qualified Data evidence into the smallest fair,
prospective experiment protocol. Record material assumptions, comparisons, selection opportunities, resource bounds,
and approval requests before the affected work. The brief and protocol are separate immutable artifacts with separate
readiness gates; neither proposal is its own approval.

The mission ends at an immutable proposed brief or protocol and structured approval requests or blockers. It does not
approve, execute, repair, or evaluate an experiment.

## Protocol authority

The agent may decide:

- the formal null, alternative, and decision claims that operationalize the delegated question;
- suitable baselines, controls, candidate comparisons, primary and secondary metrics, and acceptance/falsification
  criteria;
- chronological partitions, warmup, selection/validation/holdout roles, leakage controls, and permitted reuse;
- cost, execution, risk, portfolio, seed, and reproducibility assumptions requiring explicit treatment;
- prospective parameter spaces, optimisation objectives, budgets, stopping rules, and multiple-testing controls;
- the robustness and walk-forward evidence obligations, protected inputs, stage gates, and authority envelope needed
  for the eventual claim; and
- whether the available candidate and Data evidence is sufficient to propose a fair experiment or must return a
  blocker.

It may use read-only artifact and comparison resources plus role-scoped proposal, power/sample, cost-estimation, and
protocol-validation MCP capabilities. Deterministic services resolve canonical refs, validate schemas and lineage,
calculate checks, persist immutable proposals, and apply explicit operator decisions.

## Robustness and walk-forward charter boundary

Experiment Design specifies what robustness and longitudinal evidence the research claim requires, but it does not
design the specialist attack and walk-forward plan. Its immutable protocol defines:

- the claims and decision criteria that later evidence must address;
- development, robustness, walk-forward, and final protected evidence roles, including what remains sealed;
- the evidence and contamination state the later specialist may inspect at each stage;
- stage-entry and exit gates, overall compute/cost ceilings, multiplicity obligations, and minimum required evidence;
- prohibited scope changes and the envelope within which a child robustness/WFO plan may operate; and
- which material child-plan decisions require operator approval.

The Research Coordinator invokes the Robustness & Walk-Forward Agent when a stage gate is satisfied. That specialist
uses the protocol together with canonical outputs from relevant agents to design the detailed attacks, fold geometry,
tuning/retraining policy, stitching, specialist budgets, and sensitivity criteria. It returns an immutable child plan
through the coordinator for validation and any required approval before protected execution.

The child plan may be created before baseline evidence, after explicitly declared development evidence, or after prior
robustness/WFO findings. Its evidence-access manifest determines whether it is prospective, staged-prospective, or an
exploratory successor. Experiment Design does not pretend that a later plan was fixed at session start; the system
preserves exactly which evidence was visible when each plan was authored.

If the proposed child plan exceeds the protocol's claim, protected partitions, scope, or authority envelope,
Experiment Design must create a successor protocol. If it remains inside the envelope, the original protocol remains
immutable and the approved child plan supplies the specialist detail.

## Proposed research-question and hypothesis boundary

The operator owns the research purpose and every material expansion of it. The Research Coordinator interprets the
operator brief, pins the authorized research question, branch, scope, budgets, and permitted specialist work, and
decides whether an early hypothesis or a later protocol delegation is ready. Experiment Design may formulate the
testable claim inside that envelope: mechanism, falsifier, null and alternative, outcome-to-decision rules, baselines,
and comparisons. It may say that a question cannot yet be tested. It cannot silently change the objective, universe,
timeframe, candidate family, method, risk intent, outcome target, evidence partition, or resource ceiling.

The early phase produces a proposed revision of the existing Experiments-owned `HypothesisBrief` (`hypothesis_card`).
An operator-authored accepted brief may instead be supplied unchanged. Only the human operator accepts a brief;
`proposed` is not consent for material scope or assumptions. The Coordinator gives Data, Strategy Engineering, and
later Evaluation the accepted, digest-pinned brief handoff. Experiment Design does not directly delegate to those
specialists or rewrite their evidence. A changed material claim creates a successor brief and research branch;
changing wording without a semantic change must not reset multiplicity or contamination history.

The later phase receives that exact accepted brief plus admitted implementation and Data evidence. It formalizes the
experiment without treating a plausible strategy or a promising observed result as proof. If the admitted candidate
cannot test the brief, it returns a mismatch or a Coordinator-facing successor suggestion, not a convenient new claim.
Any new universe, method, candidate family, target, or purpose is a proposed branch for operator review. The
Coordinator can request the new branch only after its own authority checks; the original brief and protocol remain
unchanged. A result-informed successor must name the predecessor, exposed results, contamination state, and expanded
selection opportunity. Exposed evidence cannot become untouched confirmation for that successor.

Examples of the boundary:

| Delegated question or finding | Permitted Experiment Design action | Required boundary |
| --- | --- | --- |
| “Does this momentum idea have evidence within the approved scope?” | Propose a falsifiable mechanism, null, alternative, and decision rules. | Ask for missing timeframe or outcome meaning before a material guess. |
| Candidate admission uses a different Data scope from the accepted brief. | Return a canonical mismatch and a possible revision request. | Do not stretch the brief or silently choose new data. |
| Development results suggest a more favorable window or parameter. | Propose a labelled exploratory successor with full trial and exposure lineage. | Do not edit the approved protocol or call exposed evidence confirmatory. |

## Proposed exclusive decisions and hard boundaries

Experiment Design exclusively chooses the scientific test design inside delegated authority: precise falsifiable
claims, baselines, comparisons, primary/secondary metrics, partition roles, leakage controls, precommitted search and
multiple-testing treatment, stage gates, and a robustness/WFO obligation envelope. It judges whether canonical inputs
are sufficient for a fair proposal. A deterministic validator independently checks exact refs, consistency, limits,
and permissions; the agent cannot validate or approve itself.

The Coordinator owns research agenda, branch selection, specialist dispatch, and main-protocol execution requests.
Data owns dataset fitness; Strategy Engineering owns implementation; Robustness/WFO owns detailed attacks and fold
design; Evaluation owns the independent quality verdict. Human operators own material approval. No research agent
gets broker mutation, trading controls, direct SQL, unrestricted shell, or sealed-evidence access through this role.

## Proposed entry and readiness contracts

Both entry modes require session, delegation, branch/attempt, requester, actor, program/profile/catalogue, approval
policy, budget, and exact authorized question/scope identities. The Coordinator must supply a bounded task with
declared output slots and canonical refs; an unstructured user message alone is not authority.

- **Hypothesis-brief mode:** receives the operator objective and permitted question/scope envelope, existing brief
  revision if any, relevant outcome-blind method or Data availability refs, and the approval policy. Missing
  mechanism, falsifier, or material scope returns clarification. It may propose but cannot accept a brief. A
  prior accepted brief is not rewritten to make downstream work easier.
- **Protocol mode:** requires an accepted, digest-pinned `HypothesisBriefHandoff`, approved objective, admitted exact
  implementation/risk refs, qualified manifest and quality refs, coherent provider/data scope, current branch/trial
  ledger, partition/contamination state, budget and approval policy. It may propose an immutable protocol only when
  the evidence supports the brief and every execution-affecting assumption is explicit. Missing or incompatible
  artifacts return typed prerequisites; a draft brief or unadmitted candidate is not ready.
- **Successor-protocol mode:** adds the predecessor protocol/approval, exact visible-result refs, exposure manifest,
  selection history, contamination status, and a Coordinator-authorized redesign question. It cannot use a predecessor
  identity for changed design or relabel exposed holdout as fresh.

Readiness is checked by code against canonical refs and policy before model invocation and again before persistence.
Existing `ExperimentDesignRequest`/`ExperimentProtocolProposal` and `HypothesisBrief` are baseline contracts, not a
claim that the current deterministic service already implements this model-backed entry path. Any additional
stage-envelope fields require separately reviewed, typed contract work before they are executable.

## Proposed context and trust boundary

The role sees the delegated question, accepted brief where applicable, public branch/attempt state, canonical
candidate/Data/method refs, bounded summaries with cited source identities, budget, approval policy, and explicit
visibility labels for development, robustness, and protected evidence. Protocol design sees no sealed holdout values,
private Evaluation deliberation, specialist hidden reasoning, credentials, raw data corpus, or unrestricted transcript.
For a result-informed successor, code builds a new context containing only the declared exposed results and their
contamination labels; it never smuggles them into a nominally prospective invocation.

Operator prose, source text, implementation comments, provider metadata, tool responses, and prior model summaries
are untrusted data. They cannot expand scope or demand a tool call. Canonical refs are dereferenced through
role-scoped readers and checked for owner, type, requester, revision, digest, status, and visibility. Prompt injection
or a forged approval inside an artifact fails at policy, not by asking the model to be careful.

## Proposed model program and capability surface

Use a versioned Experiment Design program with distinct brief and protocol task schemas under one identity. Each
strict structured output is one of: a bounded read/tool proposal, a complete artifact proposal with cited inputs and
explicit assumptions, a typed clarification/prerequisite/approval request, or a blocker. The output pins program,
profile, schema, catalogue, delegation, branch, and attempt identities. Model text cannot declare approval, alter
trusted identities, or select a capability absent from the role catalogue. The model may select among admitted
profiles only if the session policy explicitly permits it; no profile or promotion threshold is accepted by this
design proposal. Schema-only retry is bounded; semantic invalidity returns a blocker rather than model-output
rewriting or code-owned scientific choice.

The target role catalogue permits bounded read-only canonical artifact, lineage, trial-ledger, and evidence-visibility
resources; read-only comparisons and deterministic power/sample, cost, partition, leakage, and protocol validation
capabilities; and local mutation solely for immutable proposed brief and protocol artifacts. The existing
`research_create_experiment_protocol_proposal` is a deterministic service/tool boundary, not a model-backed loop.
Brief persistence currently exists in `trader_research.governance`; a role-scoped MCP adapter and any new validators
must be delivered and documented separately before exposing that mutation to a model. The catalogue excludes
approval application, workflow registration/execution, sealed-evidence reads, coding workspace, direct store writes,
and broker operations. Runtime policy narrows tools further by phase, evidence visibility, approvals, and budget.

## Proposed internal control loop and durable state

```text
accept bounded Coordinator delegation
  -> validate readiness, identities, visibility and budget
  -> inspect permitted canonical refs and declared trial history
  -> draft brief or protocol with explicit assumptions and alternatives
  -> run deterministic scientific/schema/lineage checks
  -> revise within the same pre-result attempt only when new permitted evidence warrants it
  -> persist immutable proposal or return typed blocker/clarification/approval request
  -> hand digest-pinned result to Coordinator
```

The model chooses useful reads and revises the scientific design. Deterministic services bind trusted task fields to
tool arguments, enforce policy, calculate checks, persist idempotently, and return exact canonical refs. A failed
semantic validation cannot be repaired by silently broadening scope. If material design changes after approval or
execution exposure, the Coordinator opens a new attempt/branch and the agent creates a successor artifact.

Checkpoint only task and phase identities, bounded public proposal summaries, action/result receipts, canonical refs
and hashes, visible-evidence manifest, approvals requested, remaining budgets, loop counters, and checkpoint/program
identities. Canonical Experiments storage owns immutable brief and protocol versions, approvals, successor lineage,
and trial/exposure records. Never persist hidden reasoning, raw prompts or tool payloads, credentials, complete source
documents, or sealed results in agent state. On resume, re-read and revalidate accepted refs and receipts; exact retry
returns the same proposal and changed content under an accepted identity is a conflict.

## Proposed evidence return, termination, and escalation

Every return to the Coordinator names delegation/branch/attempt/program identity, mode, proposed artifact ref and
digest if any, exact question and claim addressed, inputs read, assumptions, approval requests, partition/visibility
status, trial/multiplicity implications, uncertainty, contradictions, blockers, consumed budget, and permitted next
actions. A proposal is never an approval or a quality verdict. The Coordinator must verify canonical refs before
advancing the agenda; downstream services consume approved exact artifacts, not a persuasive summary.

Completion means one valid, immutable, prospective proposal or an explicit no-proposal terminal result with
actionable reasons. Missing authority, ambiguous objective, mismatched refs, sealed-data request, contamination,
incompatible candidate, exhausted budget, repeated no-information revisions, model/schema failure, or unavailable
tool stops or escalates through the Coordinator. A denied approval remains visible and cannot be retried as consent.
Cancellation releases reserved resources without deleting prior evidence. The agent cannot call the human or another
specialist directly.

## Proposed evaluation and promotion contract

Qualify both phases with frozen, representative cases: instrument-agnostic question needing clarification; human
accepted brief; two plausible but scientifically different hypotheses inside one scope; admitted candidate mismatch;
partial/stale Data; no baseline; missing cost assumption; insufficient sample; leakage; precommitted parameter search;
multiple comparisons; sealed-holdout request; rejected approval; result-informed successor; duplicate/lost response;
and concurrent alternative protocols. Assert substantive claim/falsifier quality and correct tool/evidence choices,
not merely JSON validity. Negative evidence and every trial must survive review and recovery.

Promotion requires strict schema and policy pass, no forbidden action or protected-evidence exposure, reproducible
proposal/approval lineage, restart/idempotency, and measured claim quality across repeated real-model runs under a
pinned profile, program, catalogue, fixture, environment, cost, and latency budget. The evaluation charter must set
numeric thresholds and choose supported model profiles before promotion. The present deterministic proposal service
and a single scripted fixture cannot qualify this model-backed identity.

## Proposed concurrency, branching, and handoff

The Coordinator may run read-only Experiment Design investigation beside independent Data or Strategy work only when
their input sets are already sufficient and disjoint. Brief acceptance must precede dependent Data/Strategy work;
protocol proposal must await the exact candidate and Data hard join. Two designs over the same input may branch into
alternative immutable proposals with separate attempt identities, declared shared selection opportunity and budget
reservations. They cannot race to overwrite one proposal or present the favorable branch alone. Only the Coordinator
writes shared agenda state or requests deterministic main-protocol execution after approval.

Every return, including partial, failed, or blocked, rejoins the Coordinator. The Coordinator decides whether to
revise, compare alternatives, request human authority, or stop, while preserving all branch evidence. Robustness/WFO
receives only the approved protocol's envelope and stage-permitted canonical evidence through a later Coordinator
delegation. Out-of-envelope specialist needs return to Experiment Design as an explicitly authorized successor
protocol question.

## Review decision required

This is a complete proposal for the standard architecture record, not an accepted charter or implementation
authorization. Human review must explicitly accept or amend the two-phase brief/protocol boundary, especially whether
an agent may propose a `HypothesisBrief` before candidate construction, and then accept the remaining authority,
entry, context, program, capability, loop, state, return, termination, evaluation, and concurrency fields together.
Only after that decision should the parent register mark this record accepted and dependent implementation work move
out of its design gate.
