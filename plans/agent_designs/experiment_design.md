# Experiment Design Agent Design

Design status: architecture review in progress; this document does not authorize implementation.

Last reviewed: 2026-08-26.

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

## Provisional mission

Given an authorized research question, admitted candidate set, canonical Data evidence, research-branch state, and
operator constraints, produce the smallest prospective protocol capable of fairly supporting or falsifying the stated
claim. Make every material assumption, comparison, selection opportunity, resource bound, and approval visible before
execution.

The mission ends at an immutable proposed protocol and structured approval requests. It does not approve, execute,
repair, or evaluate the experiment.

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

## Research-question and hypothesis authority under review

The coordinator owns which research branch and operator objective should be pursued, its allowed scope, budgets, and
whether a specialist should be invoked. Experiment Design must not silently replace that objective with a more
interesting or favorable one.

The working recommendation is that Experiment Design may formulate the precise testable hypothesis needed to
operationalize the delegated question. It may define null and alternative claims, falsification conditions, baselines,
and discriminating comparisons; identify when the supplied question is not testable; and return bounded clarifying or
prerequisite requests.

This authority remains inside the coordinator-authorized scope. The agent cannot introduce a new asset universe,
method, candidate family, outcome target, or research purpose merely because it would make a stronger experiment. Such
changes return as optional successor-branch proposals through the coordinator and require the relevant Data, build-
contract, multiplicity, and approval treatment.

For successor protocols, the agent receives the predecessor protocol, canonical evidence refs, contamination state,
and the coordinator's explicit redesign question. It may use those results to design a labelled exploratory successor,
but cannot edit the predecessor or reuse exposed evidence as untouched confirmation.

## Remaining architecture record

The following sections remain pending structured review:

- acceptance of the research-question and hypothesis boundary;
- exclusive decisions and final hard boundaries;
- complete entry and readiness contracts;
- context and trust boundaries, including result and sealed-evidence isolation;
- model program and structured-output requirements;
- final role-scoped MCP/resource surface;
- internal design, validation, revision, and approval loop;
- durable proposal and successor state;
- evidence-return contract;
- termination and escalation;
- evaluation scenarios and promotion evidence; and
- concurrency, alternative-protocol branching, and handoff rules.
