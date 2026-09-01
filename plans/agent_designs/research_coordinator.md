# Research Coordinator Agent Design

Status: architecture record accepted; shared pattern review and implementation remain pending.

Last reviewed: 2026-08-28.

This document is the canonical build-lifecycle architecture record for the Research Coordinator. Review status and
shared principles are maintained in the parent [Agent Designs](../agent_designs.md) tracker. System-level direction
remains in [Agentic Research Orchestration Redesign](../agentic_orchestration_redesign.md), and delivery status remains
in the [Research Capability Roadmap](../research_capability_roadmap.md).

The responsibility boundary and complete architecture record were accepted in design review on 2026-08-24. The shared
agent-pattern review, concrete schemas, model profiles, and measured operating limits remain open and do not invalidate
that boundary.

## Mission and exclusive decisions

The Research Coordinator owns the research session. It interprets the operator brief, maintains a visible research
agenda, selects specialists, reviews every specialist return, controls branch progression, requests authority, and
produces the final grounded synthesis.

It exclusively decides whether to:

- advance evidence to a downstream responsibility;
- request a bounded revision from the same specialist;
- revisit an earlier responsibility through a new immutable attempt;
- propose a new method, candidate, asset, protocol, or model branch;
- request an operator decision;
- invoke deterministic main-protocol execution when its approved stage gate and prerequisites are satisfied;
- conclude with the evidence currently supported; or
- stop fail closed.

The coordinator may explore only inside approved scope and budgets. It does not overwrite specialist evidence,
overrule the independent Evaluation verdict, silently alter an approved protocol, expand asset/data/cost/research
scope, retune against confirmatory evidence while preserving the original claim, approve its own material assumptions,
admit code, promote models, create deployment authority, or initiate paper/live trading.

## Entry contract

A research session starts with:

- operator and session identity plus a natural-language research brief;
- explicit constraints, success criteria, and known exclusions;
- initial asset, data, source, cost, time, token, and compute scope;
- approval and escalation policy;
- an allowed model profile and total session budgets; and
- any supplied canonical artifact refs.

Material ambiguity triggers operator clarification before the affected mutation or experiment. A non-material working
assumption may be recorded only where policy permits it, with its origin and effect visible. Missing authority is not
inferred from silence or from approval granted to another session.

## Context and trust boundary

The coordinator sees:

- the operator conversation and public session summaries;
- the current agenda, branch/attempt lineage, budgets, loop state, and approvals;
- structured specialist returns, including partial, blocked, failed, and dissenting returns;
- bounded canonical artifact reads and comparisons needed to verify those returns; and
- previous public coordinator decisions and their cited criteria.

It does not receive specialist hidden reasoning, unrestricted source corpora, complete datasets or feature matrices,
raw coding transcripts, credentials, or an automatically accumulated copy of every tool payload. Independent
Evaluation evidence cannot be replaced by a more persuasive specialist narrative.

All specialist returns, source text, strategy code, artifact metadata, tool results, and model-generated summaries are
untrusted data. They can inform a decision but cannot grant tools, scope, approval, budget, or authority. Canonical refs
are dereferenced through controlled readers, and policy is enforced outside model output.

## Model program

The coordinator is model-backed. Its versioned program contains the role instructions, current brief and bounded
session context, available specialist descriptions, decision schema, evidence-review requirements, and explicit
authority limits. It produces structured agendas, delegations, evidence-review decisions, approval requests, and final
synthesis rather than relying on prose parsing for control flow.

The first-slice framework spike selected LangGraph 1.2.2 with the 3.1.x Postgres checkpointer and strict Pydantic
structured outputs. The development model profile is `ollama-qwen35-9b-json-v1`: Ollama `qwen3.5:9b`, temperature zero,
thinking disabled for bounded control decisions, provider-neutral JSON-schema requests, and at most one validation
repair. Exact prompts and agent-program identities remain versioned production artifacts. A model, program, schema, or
sampling-policy upgrade is a product change and must be evaluated before promotion.

## Capability surface

The coordinator receives only:

- role-scoped specialist delegation capabilities;
- read-only canonical artifact/resource and comparison capabilities;
- a specialized deterministic main-protocol execution/job capability that accepts an approved protocol ref and
  exposes bounded status, cancellation, and canonical result resources;
- research-session agenda, branch, attempt, budget, and loop-state capabilities; and
- approval request, interrupt, resume, and cancellation capabilities.

It does not receive granular or unpinned backtest/optimisation mutations, specialist-plan execution, coding-workspace
access, direct SQL, source/data acquisition, model promotion, broker access, or deployment controls. The main-protocol
tool deterministically compiles the approved artifact, enforces its exact Data/candidate/cost/search/budget lineage,
and owns scheduling, retries, reconciliation, and persistence; the coordinator cannot construct or alter those details
through tool arguments. Middleware may narrow its available specialists, execution capability, and reads further
according to session state, permissions, and remaining budget.

## Control loop

```text
interpret or clarify brief
  -> establish/revise visible agenda
  -> identify independent ready work
  -> propose bounded specialist delegations
  -> deterministic policy validates scope, dependencies, conflicts, approval, and budget
  -> dispatch permitted work
  -> receive every specialist return
  -> dereference and assess cited evidence
  -> propose advance/revise/revisit/fork/execute-main-protocol/ask/conclude/stop
  -> deterministic policy validates authority, lineage, partitions, and loops
  -> dispatch, interrupt, or terminate
```

The coordinator is an evidence-aware supervisor, not a fixed router. The model chooses work and revises the agenda;
deterministic services enforce permissions, side-effect policy, identity, idempotency, budgets, and scientific guards.

## Parallel coordination model

The coordinator maintains a dynamic agenda whose delegation tasks declare required input refs, dependencies, branch
and attempt identity, expected outputs, read/mutation scope, budget reservation, approval requirements, and expected
information gain. The model proposes work; a deterministic scheduler computes the legal ready set.

Specialist delegations may run concurrently only when:

- every input dependency is satisfied;
- neither task requires the other's result;
- their canonical writes are disjoint or otherwise concurrency-safe;
- all required approvals already exist;
- their combined reserved cost fits the session and environment budgets; and
- partition, multiplicity, evaluation-independence, and branch policy permit concurrency.

The coordinator remains the single writer of agenda and branch state. It never runs competing coordinator decisions
against the same session. Each specialist invocation is isolated and carries its own delegation, branch/attempt,
checkpoint, idempotency, model/tool budget, and trace identity.

Safe parallel work includes:

- Data fitness investigation alongside independent approved-source research;
- separate Knowledge Research invocations over different sources or evidence obligations;
- read-only maintained-implementation discovery alongside source investigation;
- independently approved strategy branches in isolated coding workspaces;
- deterministic backtest or optimisation jobs over disjoint immutable specifications; and
- independent robustness attacks against one immutable accepted baseline.

When several invocations of one specialist produce partial domain evidence, every return first rejoins the coordinator.
The coordinator validates the returns and then delegates reconciliation to the owning specialist. It does not take over
the domain synthesis. For example, source-specific Knowledge returns are consolidated by a later Knowledge Research
invocation, not by coordinator-authored methodology claims.

Two join modes are permitted:

- A **soft join** lets the coordinator review each completed return and dispatch unrelated work while other tasks are
  still running.
- A **hard join** prevents dependent work until every declared prerequisite is complete, blocked, failed, or cancelled.

There is no uncontrolled first-result-wins join. Completion order cannot discard slower negative evidence, dissent, or
failed trials. Decisions that depend on a declared evidence set wait for the hard join.

Work remains sequential when one step creates the evidence or authority required by another. This includes source
ingestion before retrieval from that generation, dossier before implementation brief, accepted brief before
knowledge-backed authoring, code admission before experiment specification, protocol approval before execution,
baseline before result-driven robustness planning, complete required evidence before final Evaluation, and approval
before the gated action.

Inside one specialist invocation, independent read-only MCP calls may execute concurrently. Observation-dependent
query refinement remains sequential. Canonical mutations may run concurrently only for disjoint immutable identities.
Specialists do not create or hand off to peer agents in the initial architecture; additional specialist fan-out always
returns to coordinator authority.

The accepted parallelism boundary is:

> Specialist reasoning and deterministic jobs may run concurrently; coordinator state transitions, conflicting
> mutations, approvals, and evidence-dependent stages remain serialized.

## Durable state and recovery

The coordinator persists only:

- the brief, constraints, success criteria, and bounded budgets;
- the agenda and immutable research branch/attempt lineage;
- delegation identities, statuses, dependencies, and bounded public summaries;
- canonical artifact refs and accepted-return receipts;
- coordinator decision receipts with concise public rationale and cited criteria;
- approval requests and decisions;
- transition fingerprints, expected information gain, and loop counters; and
- model-profile, agent-program, tool-catalog, checkpoint, and trace identities.

It does not persist hidden reasoning, credentials, complete evidence bodies, unrestricted transcripts, or raw tool
payloads as product state.

Each parallel invocation has an isolated checkpoint namespace. Accepted returns are incorporated atomically into
coordinator state. After a crash, accepted mutations are not replayed; incomplete work is resumed, cancelled, or
safely reissued according to the operation's side-effect and idempotency contract.

## Evidence review and return contract

Every specialist return contains its delegation/program/branch identities, exact questions answered and unresolved,
bounded findings, canonical supporting refs, assumptions, uncertainty, contradictions, blockers, consumed budget, and
advisory next steps. The coordinator dereferences material refs and records one structured decision with the evidence,
brief criteria, affected lineage, expected information gain, and remaining budget.

The final coordinator response distinguishes:

- established and provisional findings;
- contradictory evidence and specialist dissent;
- unresolved questions and blockers;
- scope, partition, budget, and qualification limitations;
- the independent Evaluation verdict; and
- permitted next actions and any required operator authority.

The coordinator's synthesis is not itself financial evidence. Every material research claim resolves to canonical
domain artifacts, and coordinator wording cannot alter their status or ownership.

## Termination and escalation

The coordinator concludes when the brief's evidence requirements are satisfied and required independent review is
complete. It requests an operator decision when useful work requires material scope, assumption, budget, provider,
external mutation, model-promotion, or paper-candidate authority not already granted.

It stops fail closed when evidence is terminally adverse, a required source or capability is unavailable, evaluation
would be contaminated, an action is outside all permitted authority, budgets are exhausted, or materially equivalent
delegations repeat without new evidence. An exact or paraphrased loop cannot reset counters or manufacture information
gain.

## Evaluation contract

Coordinator evaluation covers:

- accurate brief interpretation and material-ambiguity handling;
- appropriate specialist selection, omission, and safe parallel dispatch;
- verification of specialist claims against matching canonical evidence;
- different advance, revision, revisit, fork, approval, conclusion, and stop decisions for materially different
  evidence;
- preservation of negative evidence, failed branches, complete trial ledgers, and independent dissent;
- correct scope, partition, approval, authority, and budget behavior;
- correct invocation, monitoring, cancellation, and evidence review of deterministic main-protocol execution without
  changing approved experiment semantics;
- rejection of duplicate low-information work and safe termination under exhausted limits;
- restart, cancellation, lost-response, and idempotent-resume behavior;
- prompt-injection and misleading-artifact resistance; and
- trace completeness, latency, token use, compute cost, and quality across repeated model runs.

A successful demonstration is not acceptance. Promotion thresholds and representative fixtures are established through
the design/evaluation charter and framework measurements.

## Measured implementation decisions

The framework comparison resolved the primary runtime, development model profile, structured-output mechanism,
Postgres checkpoint direction, and MLflow trace projection. The following tuning choices remain measurement-driven
during production qualification:

- promotion model providers and any per-role profile overrides;
- final field limits within the accepted structured agenda, delegation, decision, and evidence-return contracts;
- exact scheduler use of LangGraph subgraphs, parallel dispatch, and cancellation;
- initial concurrency, revision, fork, token, time, and cost limits;
- scheduler batching behavior when several returns arrive together;
- trace redaction and retained payload policy; and
- numeric behavioral promotion thresholds.

These decisions may refine implementation without reopening the coordinator's mission, authority, context, evidence,
single-writer, or parallelism boundaries. A result that contradicts those boundaries requires explicit charter review.
