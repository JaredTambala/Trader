# Robustness & Walk-Forward Agent Design

Status: architecture review in progress; no implementation is authorized by this document.

Last reviewed: 2026-08-28.

This document is the canonical build-lifecycle architecture record for the Robustness & Walk-Forward Agent. Review
status and shared principles are maintained in the parent [Agent Designs](../agent_designs.md) tracker. System-level
direction remains in [Agentic Research Orchestration Redesign](../agentic_orchestration_redesign.md), and delivery
status remains in the [Research Capability Roadmap](../research_capability_roadmap.md).

## Established responsibility boundary

The accepted boundary assigns this agent both specialist plan design and evidence inspection:

- Experiment Design supplies the immutable research claim, evidence partitions, protected-stage rules, stage gates,
  overall budget, and the envelope within which robustness/WFO work is authorized.
- The Robustness & Walk-Forward Agent synthesizes the relevant canonical outputs of multiple agents to create the
  detailed attack and walk-forward plan appropriate to the exact strategy and Data slice.
- Its plan may be authored before results, after declared development evidence, or after prior specialist findings. It
  must identify which evidence was visible and classify the plan as prospective, staged-prospective, or exploratory.
- The plan is immutable and independently validated. Material assumptions and authority outside the pre-approved
  envelope return through the coordinator for approval before execution.
- After approval, the agent may operate role-scoped robustness/WFO MCP tools, monitor and recover bounded deterministic
  jobs, inspect canonical outputs, and issue sensitivity findings.
- It does not change the research claim, approve its own plan, hide failed attacks or folds, treat exploratory evidence
  as untouched confirmation, issue the final Evaluation verdict, or recommend paper trading.

## Mission

Determine how the current research claim should be challenged and tested through time, given the exact implementation,
Data, method assumptions, experiment charter, permitted prior evidence, and available specialist capabilities. Produce
an immutable, epistemically labelled robustness/WFO plan; operate it after approval; and return complete canonical
sensitivity and longitudinal evidence without overstating its inferential status.

## Multi-agent evidence input contract

The agent does not communicate directly with other specialists or consume their raw conversations. Every specialist
return first rejoins the Research Coordinator. The coordinator creates one typed delegation containing canonical refs,
bounded public findings, branch/attempt identity, budgets, approvals, and contamination state.

Depending on the strategy and stage, the delegation may include:

- **Data Research:** dataset manifests, quality reports, calendars, coverage, universe composition, usable periods, and
  known defects;
- **Knowledge Research and Quantitative Methods:** dossier/brief refs, method assumptions, invariants, parameter
  semantics, state, warmup, expected failure modes, and unresolved caveats;
- **Strategy Engineering:** exact implementation/build-contract refs, admission evidence, dependencies, timing/state
  behavior, parent lineage, and limitations;
- **Experiment Design:** the approved charter, hypothesis and claims, evidence roles, stage gates, baseline/selection
  rules, protected inputs, authority envelope, overall budget, and required approvals;
- **Experiment execution services:** canonical baseline/comparison/optimisation refs, complete trial ledgers, execution
  anomalies, costs, and bounded findings only when the charter permits them to be observed;
- **ML Signal Research:** point-in-time feature, model, training, tuning, retraining, prediction, parity, and MLflow refs
  for model-backed strategies; and
- **Prior Robustness or Evaluation:** immutable findings, dissent, identified gaps, and explicit successor requests when
  authoring later plans.

Missing required inputs block plan creation. A summary never substitutes for a canonical artifact when the underlying
evidence is needed to make or validate a material decision.

## Evidence timing and epistemic classification

The plan records an evidence-access manifest listing every result-bearing artifact available to the agent when it was
authored. Deterministic policy derives one classification:

- **prospective:** no performance evidence relevant to the planned attacks or WFO procedure was exposed;
- **staged-prospective:** declared development evidence was exposed, but the evidence the plan will judge remains
  protected; or
- **exploratory successor:** relevant protected or predecessor evidence informed the new plan.

The classification is not model-selected rhetoric. It follows from artifact lineage, evidence roles, access receipts,
and contamination state. If development work already exposed the intended WFO period, the plan cannot claim untouched
confirmation over that period.

## Plan authority and contract

Inside the Experiment Design envelope, the agent decides:

- which claims, assumptions, dependencies, and failure modes to attack;
- cost, latency, timing, parameter-neighborhood, data degradation, window, regime, asset/universe, concentration,
  execution, risk, and other justified perturbation families;
- immutable baseline/variant construction, attack priority, seeds, budgets, multiplicity, early-stop, and sensitivity
  criteria;
- rolling or expanding WFO structure; fold roles and boundaries; calendar, frequency, lookback, warmup, purge, embargo,
  and overlap treatment;
- tuning/retraining/feature-refresh policy, objectives, search spaces, freeze/carry-forward rules, per-fold budgets, and
  failed-fold treatment; and
- stitching, aggregation, exposure and cost normalization, degradation/stability criteria, and required output
  evidence.

The immutable plan also pins its parent experiment charter, input artifacts and hashes, evidence-access manifest,
epistemic class, requested approvals, capability-catalogue version, resource estimates, prohibited changes, and
successor lineage.

## Plan approval boundary

Every proposed plan returns through the Research Coordinator and passes deterministic schema, lineage, evidence-access,
budget, capability, and authority-envelope validation before protected execution.

The plan does not require a new operator decision when it stays entirely inside an already approved Experiment Design
envelope and introduces no material assumption. After validation, the coordinator may advance the existing stage gate
and redelegate the exact immutable plan for execution; this is policy application, not coordinator approval of a new
research decision.

The plan must interrupt for explicit operator authority when it changes or introduces a material claim, assumption,
asset or universe scope, protected-data access, cost/compute exposure, external mutation, dependency, model-training
policy, or other field outside the approved envelope. The agent cannot split work into smaller actions to evade that
boundary. Rejection, modification, or partial approval creates a new plan identity and preserves the original proposal.

## Plan, execution, and revision loop

The model may inspect allowed evidence, identify unresolved design obligations, select read-only planning or estimation
tools, propose the structured plan, and revise it against deterministic validation findings before approval. It cannot
execute protected work while material approvals are pending.

After plan approval, the agent may choose permitted tool ordering, create exact immutable variants/folds, start bounded
jobs, inspect status and canonical results, retry idempotent operational failures, and synthesize sensitivity findings.
It may not modify plan fields in response to results. A new attack, fold rule, tuning policy, or evidence scope creates
an immutable successor plan through the coordinator; exceeding the parent charter also requires a successor Experiment
Design protocol.

## Specialist execution boundary

After approval, the Robustness & Walk-Forward Agent invokes a role-scoped, plan-pinned deterministic MCP execution
surface. Every variant, fold, tuning job, and stitch request must be derivable from the exact approved plan; policy
rejects an operation that changes or lacks that parent lineage.

Main-protocol execution and RWFO execution may use the same deterministic specification, backtest, optimisation, job,
and aggregation engines beneath MCP. The Research Coordinator invokes the main-protocol execution capability for
baseline backtests, comparisons, and optimisation. RWFO invokes the specialist capability for variants and folds under
its approved child plan.

RWFO decides the specialist plan and may inspect job status and canonical outputs, but code owns execution ordering,
safe concurrency, idempotent recovery, resource enforcement, and reconciliation whenever those are mechanically
derivable. It cannot use tool invocation to redesign an attack, fold, objective, protected-data role, or acceptance
criterion. All partial and terminal returns still rejoin the coordinator before another agent is invoked.

## Evidence return

Every return to the coordinator includes plan and validation refs; consumed input refs; epistemic classification;
attack, fold, job, ledger, stitch, and report refs produced so far; claim-relative findings; failed and missing work;
uncertainty, dissent, contamination, budgets consumed, blockers, and bounded successor requests. Aggregate stability
never replaces fold-level or attack-level evidence.

## Remaining architecture record

The following sections remain pending structured review:

- complete exclusive-decision and hard-boundary wording;
- exact entry/readiness, plan, approval, and return schemas;
- context and trust boundaries, including malicious implementation comments and artifact content;
- model program and structured-output requirements;
- final role-scoped MCP/resource surface and long-running job model;
- durable state, recovery, cancellation, and partial completion;
- termination and escalation limits;
- evaluation scenarios and promotion evidence; and
- concurrency, attack/fold fan-out, joins, mutation conflicts, and handoff rules.
