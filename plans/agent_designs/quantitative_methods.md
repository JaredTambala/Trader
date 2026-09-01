# Quantitative Methods Agent Design

Status: architecture review in progress; no implementation is authorized by this document.

Last reviewed: 2026-08-25.

This document is the canonical build-lifecycle architecture record for the Quantitative Methods Agent. Review status
and shared principles are maintained in the parent [Agent Designs](../agent_designs.md) tracker. System-level direction
remains in [Agentic Research Orchestration Redesign](../agentic_orchestration_redesign.md), and delivery status remains
in the [Research Capability Roadmap](../research_capability_roadmap.md).

## Established design constraints

The system-level review has already established these starting constraints:

- Knowledge Research owns source investigation and the validated research dossier.
- Quantitative Methods owns the implementation brief that translates an accepted dossier into explicit mathematical,
  algorithmic, state, parameter, invariant, edge-case, and test obligations.
- Source-backed decisions, Trader engineering decisions, and unresolved decisions remain separate in the brief.
- Unsupported equations, defaults, timing, initialization, or other material method semantics cannot be supplied from
  model memory. They block or branch the brief.
- Strategy Engineering, not this agent, authors executable code and submits it for independent admission.
- The agent may choose from role-scoped dossier, method-contract, formal-validation, reference-calculation, and
  implementation-brief MCP capabilities. Deterministic services calculate, validate, persist, and enforce policy.
- Source fidelity is not evidence of profitability. Experiment Design, execution, Robustness, walk-forward analysis,
  and Evaluation retain their own decisions.

## Mission

Turn a validated research dossier into an explicit, auditable, implementation-ready quantitative brief before any
strategy code or backtest exists. The brief states exactly what Strategy Engineering may implement, what the approved
sources support, which Trader integration choices are necessary, what remains unresolved, and how mathematical
fidelity can be checked.

The agent is pre-code and outcome-blind. It does not serve as a general post-result quantitative analyst.

## Accepted responsibility boundary

The agent starts only from a validated research dossier and relevant Trader interface constraints. It produces a
proposed implementation brief containing:

- method and variant identity plus component ordering;
- typed inputs, outputs, units, timing, and data-frequency requirements;
- normalized equations and symbol definitions linked to exact evidence;
- ordered algorithm stages, state transitions, warmup, missing-value behavior, and termination;
- evidence-supported parameter semantics and bounds;
- invariants, edge cases, failure behavior, and test obligations; and
- separately labelled source-backed, engineering, unresolved, and approval-requiring decisions.

It cannot reopen source research silently. Missing evidence returns a precise request through the coordinator to
Knowledge Research. Only an independently validated and accepted brief can reach Strategy Engineering.

It may use deterministic MCP calculations only to validate the formal translation before code—for example, resolving a
method contract, checking dimensions and units, evaluating a cited reference example, or testing that normalized
equations preserve stated invariants. Those operations support the implementation brief; they are not permission to
inspect strategy or backtest outcomes.

The responsibilities previously grouped into a second quantitative-analysis mode belong elsewhere:

- Experiment Design selects prospective metrics, statistical tests, optimisation objectives, and multiple-testing
  controls and records them in the protocol.
- Deterministic experiment execution MCP services invoke the protocol-declared calculations and engines.
- Strategy Engineering and independent admission tooling run implementation fixtures and signal-level conformance
  diagnostics.
- Robustness and Evaluation interpret experimental evidence within their own authorities.
- A method change motivated by outcomes starts a new coordinator-managed research branch. It cannot mutate the
  original dossier, implementation brief, or prospective protocol.

The agent must not receive backtest, optimisation, robustness, walk-forward, or evaluation outcomes in its normal
context. Admission failures may return only the bounded implementation-conformance evidence needed to revise a brief;
they do not grant general outcome access.

## Trader integration and software-engineering boundary

The accepted brief boundary distinguishes quantitative behavior from code construction:

- Quantitative Methods owns behaviorally material integration decisions needed to make the sourced method precise in
  Trader: input roles, units, observation and execution timing, warmup, state, missing-value behavior, numerical
  constraints, and no-lookahead invariants.
- A necessary behaviorally material choice that is not source-backed is labelled as a Trader adaptation, with its
  rationale, consequences, uncertainty, and approval requirement. It is never presented as sourced semantics.
- Strategy Engineering owns non-semantic software decisions such as module layout, type implementation, class
  structure, naming, internal decomposition, and performance technique, subject to repository standards and the
  accepted brief.
- Strategy Engineering cannot reinterpret or silently alter the brief's behavior. If implementation exposes a
  behaviorally material ambiguity or required change, it returns a blocker through the coordinator for a revised brief.

## Remaining architecture record

The following sections remain pending structured review:

- final exclusive decisions and hard boundaries;
- complete entry and readiness contracts;
- context and trust boundaries, including strict outcome-evidence isolation;
- model programs and structured-output requirements;
- final role-scoped MCP/resource surfaces;
- internal tool-use and validation loops;
- durable state and recovery;
- evidence-return contracts;
- termination and escalation;
- evaluation scenarios and promotion evidence; and
- concurrency and handoff rules.
