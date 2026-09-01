# Agent Designs

Status: active design workbook; no implementation is authorized by this document.

Last reviewed: 2026-09-01.

This is the canonical working record for the architecture of Trader's target model-backed agents. It carries accepted
boundaries and pending decisions across review, implementation, and qualification, preventing the target from
collapsing back into a list of responsibilities. An agent is ready for charter acceptance only when every field in the
standard record has been reviewed. Acceptance here is a planning decision, not an implementation or qualification
claim.

The overall control-plane direction remains in
[Agentic Research Orchestration Redesign](agentic_orchestration_redesign.md); capability status and dependencies remain
in [Research Capability Roadmap](research_capability_roadmap.md).

## Active implementation-slice review

The temporary [First Agentic Implementation Slice — Review Plan](agent_designs/first_agentic_slice_implementation_plan.md)
turns the selected Coordinator–Data–Strategy direction into gates, workstreams, concurrency, evaluation scenarios and a
definition of done for user review. It authorizes no implementation. After acceptance, durable architecture decisions
must be incorporated into the three owning agent records and delivery dependencies into the roadmap; the temporary
plan should then be deleted or reduced to unresolved implementation notes.

## Design review register

| Agent | Responsibility boundary | Complete architecture record | Pattern review | Current review state |
| --- | --- | --- | --- | --- |
| [Research Coordinator](agent_designs/research_coordinator.md) | accepted | accepted | pending shared pattern review | Charter accepted; coordinator-invoked deterministic main-protocol execution was added on 2026-08-28 without granting granular experiment mutation. |
| [Data Research Agent](agent_designs/data_research.md) | accepted | pending | pending | Multi-asset responsibility and bounded acquisition authority accepted; the remaining standard record is still under review. |
| [Knowledge Research Agent](agent_designs/knowledge_research.md) | accepted | pending | pending | Role-scoped MCP ingestion and session-approved source-envelope authority accepted; the remaining standard record is still under review. |
| [Quantitative Methods Agent](agent_designs/quantitative_methods.md) | accepted | pending | pending | Single pre-code, outcome-blind responsibility and quantitative/software design boundary accepted; the remaining standard record is pending. |
| [Strategy Engineering Agent](agent_designs/strategy_engineering.md) | accepted | pending | pending | Build, catalogue, sandbox, admission, outcome-isolation, and repair-loop boundaries are accepted; the remaining standard record is pending. |
| [Experiment Design Agent](agent_designs/experiment_design.md) | in review | pending | pending | Prospective experiment-charter, protected-evidence, and specialist-envelope authority is established; research-question and hypothesis latitude remain under review. |
| [Robustness & Walk-Forward Agent](agent_designs/robustness_walk_forward.md) | accepted | pending | pending | Multi-agent plan design, pre-approved-envelope authority, and direct plan-pinned specialist execution are accepted; the remaining standard record is pending. |
| ML Signal Research Agent | parked | pending | pending | Intentionally deferred on 2026-08-28; it does not block the first Coordinator–Data–Strategy implementation slice. |
| Evaluation Agent | provisional responsibility only | pending | pending | Not yet reviewed through the standard record. |

Hypothesis generation remains a responsibility inside other agents unless a later evaluation justifies a separate
agent. Recommendation synthesis remains with the coordinator unless measured independence benefit justifies a new
identity. Neither is an unreviewed implied agent in this register.

Experiment execution is deliberately absent from the agent register. An approved main protocol is compiled and run by
deterministic MCP execution/job services invoked by the Research Coordinator. Approved robustness/WFO plans use a
separate plan-pinned deterministic execution surface invoked by their owning specialist. Execution has no exclusive
research judgment and therefore does not justify an LLM identity.

ML Signal Research remains a future target, not part of the active architecture gate. Its record, patterns, model
profile, MLflow tool surface, and deterministic ML lifecycle prerequisites are parked until the first non-ML agentic
slice is implemented and qualified.

## Standard agent architecture record

Every agent design must specify all of the following:

1. **Mission**: the bounded outcome the agent exists to produce.
2. **Exclusive decisions**: judgments only this agent may make and decisions expressly reserved elsewhere.
3. **Entry contract**: delegation fields, canonical inputs, approvals, and readiness conditions required to start.
4. **Context boundary**: conversation, artifacts, summaries, and previous work it may see, plus context intentionally
   withheld.
5. **Trust model**: untrusted inputs and defenses against prompt injection, misleading artifacts, and authority claims
   embedded in data.
6. **Model program**: instructions, structured output schema, model-profile requirements, version identity, and any
   permitted model selection.
7. **Capability surface**: MCP tools and resources available to the role, including state- or policy-driven narrowing.
8. **Internal control loop**: how the model plans, selects tools, observes results, revises, and decides it has enough
   evidence.
9. **Durable state**: what survives interruption, what remains ephemeral, and what must never be persisted.
10. **Evidence-return contract**: findings, canonical refs, uncertainty, blockers, unresolved questions, consumed
    budget, and advisory next actions returned to the coordinator.
11. **Termination and escalation**: completion, revision, contradiction, budget exhaustion, missing authority, and
    fail-closed conditions.
12. **Evaluation contract**: representative scenarios, forbidden behaviors, trajectory constraints, grounding,
    independence, recovery, cost, latency, and quality thresholds.
13. **Concurrency and handoff rules**: parallel work, dependency joins, mutation conflicts, cancellation, and the
    requirement that cross-agent work returns through the coordinator.

The record describes product architecture, not one framework API. Pattern and framework choices are reviewed only
after the agent boundaries are complete, so framework conveniences do not determine domain authority.

## Shared design principles

- A component is an agent only when a language model chooses among meaningful actions, observes results, and can revise
  its approach inside a bounded mission. Validators, schedulers, persistence, and deterministic executors are services.
- Architecture is named by stable responsibility, never by roadmap or implementation checkpoint codes.
- Agent reasoning owns research planning, tool choice, interpretation, and replanning. Deterministic services own data
  mutation, validation, calculations, execution, persistence, idempotency, permissions, and safety policy.
- MCP is the normal model-facing capability boundary. Agents do not bypass an available tool to call Trader internals,
  stores, raw SQL, arbitrary shell, or provider credentials.
- The Research Coordinator is the only default user-facing agent and the single writer of shared session/agenda state.
  Every specialist return, including failure and partial work, rejoins it before cross-agent continuation.
- Canonical domain artifacts are research evidence. Agent messages, generated summaries, checkpoints, traces, and
  hidden reasoning are not substitutes for that evidence.
- Revisions, retries, candidate changes, and scope changes preserve immutable branch and attempt lineage. Negative
  evidence, failed trials, and dissent are never overwritten by a later favorable result.
- Context is role-scoped, bounded, and treated as untrusted data. No agent persists or exposes hidden chain of thought,
  credentials, unrestricted transcripts, or unbounded copies of tool payloads.
- Human authority remains explicit for material assumptions, scope expansion, costly/external mutation, model
  promotion, and paper-candidate handoff. Research agents never mutate live or paper broker operations.
- Framework and design patterns must implement accepted agent boundaries. A convenient framework abstraction cannot
  silently redefine authority, artifact ownership, context isolation, or handoff rules.

## Review workflow and shared pattern gate

Every agent must be questioned and recorded through the same template before that identity is implemented.
Responsibility rows above are working hypotheses, not accepted designs. The active review now completes the
Coordinator, Data Research, and Strategy Engineering records and their shared patterns first; parked or later-slice
agents do not block that implementation slice. Create an owning document under `plans/agent_designs/` when review
begins, and link it from the register. For each implementation slice, perform a pattern review of:

- supervisor with subagents and agents exposed as tools;
- custom workflow nodes around model/tool loops;
- repeated same-specialist fan-out and specialist-owned reconciliation;
- context-isolated independent Evaluation;
- coding-agent workspace and admission patterns;
- model-owned versus deterministic routing and validation;
- parallel dispatch, join, interrupt, cancellation, and recovery; and
- whether any proposed standalone agent lacks an exclusive decision and should instead be a tool or responsibility.

The pattern review selects mechanisms that implement the accepted boundaries. It must not silently change authority,
artifact ownership, context isolation, or the requirement that every specialist return rejoins the coordinator.
