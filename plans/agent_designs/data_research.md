# Data Research Agent Design

Status: architecture record accepted; implementation and qualification remain pending.

Last reviewed: 2026-09-01.

This document is the canonical build-lifecycle architecture record for the Data Research Agent. Review status and
shared principles are maintained in the parent [Agent Designs](../agent_designs.md) tracker. System-level direction
remains in [Agentic Research Orchestration Redesign](../agentic_orchestration_redesign.md), and delivery status remains
in the [Research Capability Roadmap](../research_capability_roadmap.md).

## Established requirements

The Data Research Agent works against the role-scoped catalogue of registered MCP capabilities to identify and prepare
the complete data scope required by a research brief and its intended backtest. It is not designed around one asset,
symbol, or pair.

The accepted requirements established in design review are:

- Interpret the brief and supplied research artifacts to identify every relevant asset, universe member, reference
  series, timeframe, frequency, field, and data role needed by the requested backtest.
- Support multi-asset and universe research as a normal case. A pair is only one possible scope shape.
- Discover what relevant data already exists, assess its coverage and fitness, and identify material gaps or quality
  defects.
- Use approved MCP ingestion or backfill capabilities, where policy permits, to make missing data ready for use rather
  than merely reporting that it is absent.
- Return complete canonical Data evidence for downstream work, or an explicit partial/blocked result that identifies
  missing scope, unavailable capabilities, quality defects, and possible remediation.
- Evolve through the MCP capability plane. Additional data types, providers, discovery mechanisms, quality checks, and
  loading operations become usable when their tools are registered, role-authorized, described, and qualified; the
  agent architecture must not assume a permanently fixed provider or data-type catalogue.

## Mission and exclusive decisions

Given a bounded research request, determine the complete data scope required to test it, use available Data MCP
capabilities to discover and prepare that scope, and return canonical evidence stating whether the requested data is
ready and fit for the intended backtest.

The mission covers data readiness. It does not cover experiment design, strategy selection, performance judgment, or
choosing a more favorable asset after seeing results.

The Data Research Agent exclusively decides:

- how to decompose an approved composite Data scope into evidence obligations;
- which permitted discovery, inventory, quality, acquisition, and revalidation operations to use;
- whether independently investigated scope elements require specialist-owned reconciliation;
- whether available Data is fit, conditionally fit, partial, or blocked for the declared use; and
- which bounded remediation or approval request to recommend when readiness is incomplete.

It does not decide research merit, implementation behavior, experiment design, acceptable trading performance,
material scope changes, provider admission, acquisition policy, or whether an unfit scope can be ignored. The
coordinator may verify the returned evidence and route the next action but cannot replace the Data readiness verdict.

## Scope model

The agent must reason over a role-labelled composite scope rather than a single symbol tuple. A scope may contain:

- one or many traded instruments;
- dynamic or fixed universe membership;
- paired, basket, benchmark, hedge, market, sector, or reference series;
- price, quote, trade, corporate-action, fundamental, alternative, feature, or other registered data types;
- market calendar, session, timezone, frequency, field, adjustment, and availability requirements;
- warmup and lookback coverage before the nominal experiment period; and
- role-specific quality requirements and permitted providers.

The exact scope schema remains to be designed. It must preserve the origin of each requirement—operator brief,
strategy/implementation contract, implementation brief, experiment proposal, or explicit working assumption—so the
agent cannot silently introduce or remove data.

The first implementation normalizes this model into a typed composite scope containing one or more role-labelled scope
items. Each item pins its instruments or universe rule, data role and type, fields, frequency, calendar, timezone,
adjustment semantics, requested period, warmup/lookback, permitted providers, quality requirements, and requirement
origin. Scope identity is stable under ordering normalization and changes whenever a behaviorally material field
changes.

## Entry contract

A delegation is ready only when it contains:

- session, delegation, branch, and attempt identity;
- the exact research question and intended downstream use;
- a validated composite Data scope or the bounded requirements from which the agent is asked to complete it;
- canonical implementation/build-contract refs where those refs add Data obligations;
- approved provider, asset/universe, period, frequency, volume, cost, environment, and credential envelopes;
- explicit quality and completeness rules;
- tool, model, token, time, mutation, and concurrency budgets; and
- any prior canonical Data refs or failed-attempt summaries relevant to this attempt.

Missing non-material detail may produce a recorded working assumption only when session policy explicitly permits it.
Missing material scope, quality, provider, cost, or mutation authority produces an operator question or partial/blocked
return through the coordinator before the affected action.

## Context and trust boundary

The agent may see its delegation, the approved composite scope, bounded brief excerpts, relevant build-contract fields,
prior public Data-attempt summaries, active acquisition policy, role-scoped tool descriptions, and bounded canonical
Data resources. It does not receive unrelated conversation, strategy performance, other specialists' hidden reasoning,
credentials, database handles, unrestricted datasets, or complete tool transcripts.

Provider metadata, symbol descriptions, field names, dataset content, quality diagnostics, prior summaries, and tool
results are untrusted observations. Embedded instructions cannot change scope, authority, budgets, quality rules, or
the available catalogue. Deterministic middleware validates every proposed mutation and every returned canonical ref.

## Model program

The versioned Data Research program instructs the model to plan evidence obligations, choose from the active MCP
catalogue, inspect results, revise queries, reconcile scope elements, and emit a structured readiness return. Its
outputs are validated typed decisions rather than prose-parsed control commands.

The program identity pins instructions, output schemas, supported tool-contract version, model profile, and context
policy. Model or program changes require evaluation before promotion. The provider and sampling configuration remain
profile choices; they cannot change the Data authority boundary.

## Capability-catalogue model

The agent receives a role-scoped, state-aware MCP catalogue rather than a hard-coded sequence of data calls. Its model
may choose among available discovery, inventory, quality, ingestion, backfill, snapshot, and evidence-read operations,
observe their results, and revise its investigation.

The current deterministic baseline includes symbol discovery, bounded inventory, quality summarisation, approved
loading/backfill, and canonical research-snapshot creation. These tools are a starting capability surface, not the
permanent definition of the agent. A newly registered provider or data-type tool is not automatically usable: its
schema, side effects, approval policy, role exposure, output evidence, idempotency, and evaluation coverage must first
be accepted through the MCP inventory and normal release process.

Tool descriptions and resource metadata must make at least the following discoverable to the model:

- supported asset classes, instruments, fields, frequencies, calendars, and time ranges;
- provider identity and source authority;
- read-only, local-mutation, or external-mutation posture;
- expected cost, volume, latency, and bounded execution limits;
- approval and credential requirements;
- canonical outputs and quality evidence;
- idempotency, retry, cancellation, and recovery behavior; and
- known provider or data-quality limitations.

The agent never receives provider credentials, database handles, arbitrary filesystem access, raw SQL, or generic
network access in model context.

The initial role surface contains bounded health/config reads, symbol and universe discovery, inventory, quality,
approved loading/backfill, exact snapshot creation, and canonical Data-resource reads. Runtime middleware removes
mutation tools when the acquisition envelope, environment gate, approval, or remaining budget does not permit them.
Newly registered tools are unavailable to the agent until the role catalogue and program version explicitly admit
them.

## Internal control loop

```text
validate delegation and composite scope
  -> plan Data evidence obligations
  -> select independent read-only investigations
  -> deterministic policy validates ready calls and reservations
  -> call role-scoped MCP capabilities
  -> inspect coverage, quality, conflicts, and missing roles
  -> refine or reconcile bounded investigation
  -> if useful remediation is permitted, request estimate and mutate
  -> re-run inventory and quality after every mutation
  -> create one exact canonical snapshot for the final represented scope
  -> return complete, conditional, partial, or blocked readiness evidence
```

The model owns investigation and interpretation. Deterministic services own request normalization, provider access,
data mutation, quality calculations, persistence, idempotency, cancellation, and policy enforcement. Repeating an
equivalent call without a changed scope or new evidence consumes the loop budget and cannot reset an attempt.

## Readiness outcome

A successful result must cover the complete declared composite scope. It returns canonical dataset-manifest and
quality-report refs, plus bounded findings that state:

- which requested roles and elements are ready;
- the exact data generations, providers, periods, frequencies, fields, and transformations represented;
- whether warmup and intended backtest coverage are complete;
- material defects, limitations, assumptions, and uncertainty;
- ingestion/backfill work performed and its canonical evidence;
- unresolved or unavailable scope elements; and
- whether the scope is fit, conditionally fit, partial, or blocked for the intended use.

An available dataset is not automatically fit. A technically executable backtest is not sufficient when missing or
misaligned data could invalidate the research claim.

## Acquisition authority

The Data Research Agent may determine what investigation is necessary and recommend how a missing or defective scope
could be remediated. It may not silently change the research question, substitute assets because they appear more
promising, narrow a universe or date range, change frequency or adjustment semantics, or accept a material quality
defect on the operator's behalf.

The accepted acquisition boundary is:

- Read-only discovery, inventory, and quality operations are autonomous inside the role's active MCP catalogue and
  session budgets.
- The agent may invoke ingestion or backfill autonomously only inside a pre-approved acquisition envelope covering
  provider, data type, asset or universe constraints, dates, frequency, volume, cost, credentials, runtime, and
  environment.
- After a mutation, the agent must repeat inventory and quality checks and create an exact canonical snapshot before it
  can report that the affected scope is ready.
- Work outside the envelope becomes a structured approval request returned through the Research Coordinator, together
  with partial readiness evidence and bounded remediation options.
- The agent cannot evade the envelope by substituting assets, shrinking the requested universe or period, changing
  frequency, or weakening a quality requirement.

An environment or session policy supplies the concrete envelope. The agent can explain why more authority would help,
but it cannot grant that authority to itself.

## Durable state and recovery

Durable specialist state contains only the delegation identity and digest, normalized scope and policy identities,
planned evidence obligations, completed tool-call receipts, bounded public observations, canonical refs, budget use,
loop fingerprints, current status, and pending approval or cancellation state. Raw datasets, credentials, hidden model
reasoning, unbounded tool payloads, and unrestricted transcripts are never checkpointed as product state.

Each mutation uses a stable idempotency key derived from session, delegation, attempt, scope, and operation identity.
After interruption, the agent validates accepted receipts and canonical refs before deciding whether an incomplete call
may be safely resumed or reissued. A lost response does not authorize repeating a mutation whose accepted result can be
resolved.

## Evidence-return contract

The structured return includes:

- agent-program, model-profile, tool-catalogue, session, delegation, branch, and attempt identities;
- the normalized composite scope and the exact questions answered or unresolved;
- readiness status and findings for every requested Data role;
- manifest, quality, acquisition, and snapshot refs with expected type, owner, producer, and hashes;
- performed mutations and their idempotency receipts;
- assumptions, uncertainty, limitations, contradictions, blockers, and missing capabilities;
- consumed model, tool, time, volume, cost, and mutation budgets; and
- advisory remediation, approval, revision, or downstream handoff actions.

The coordinator may reject a malformed or unresolvable return and request a bounded revision. It cannot relabel a
partial or blocked Data verdict as ready.

## Termination and escalation

The agent completes when every required scope element has matching canonical evidence and it can issue the justified
readiness verdict. It returns partial or blocked when a required role is unavailable, quality remains materially
defective, a provider or tool is missing, or safe remediation cannot complete.

It escalates before any out-of-envelope acquisition, material working assumption, scope substitution, quality waiver,
or additional budget. It stops fail closed on exhausted budgets, cancelled authority, inconsistent canonical evidence,
repeated equivalent low-information work, unresolvable tool-contract failure, or attempted instruction/authority
injection.

## Evaluation contract

Evaluation covers:

- single-asset, paired, basket, benchmark, hedge, reference-series, and multi-role composite scopes;
- complete, partially available, missing, stale, misaligned, duplicate, and materially defective Data;
- correct warmup, calendar, timezone, frequency, field, adjustment, and provider reasoning;
- legal in-envelope backfill followed by mandatory revalidation and exact snapshot creation;
- denied out-of-envelope mutation, unavailable provider, cost overrun, cancellation, and partial returns;
- disjoint parallel investigation and specialist-owned reconciliation without dropped negative evidence;
- prompt injection and misleading provider metadata resistance;
- malformed tool responses, lost responses, restart, cancellation, and idempotent recovery; and
- grounding, scope fidelity, loop termination, latency, token/tool use, acquisition cost, and result quality over
  repeated real-model runs.

Deterministic invariants—authority, scope, mutation gates, canonical-ref validity, no silent substitution, and no
duplicate accepted mutation—must pass every run. Model-quality thresholds and operating limits are frozen in the
qualification profile rather than embedded in the agent program.

## Concurrency and handoff rules

Read-only investigation of disjoint assets, roles, providers, or periods may proceed concurrently inside the reserved
budget. Mutations may overlap only when their identities and writes are disjoint and the provider/environment policy
permits it. Inventory and quality revalidation for an affected scope occurs after its mutation is terminal.

No first-result-wins behavior is permitted. The complete readiness verdict waits for every declared required scope
element to complete, fail, block, or cancel. Partial returns first rejoin the coordinator; when Data synthesis is still
needed, the coordinator delegates reconciliation back to a Data Research invocation. The agent never hands work
directly to Strategy Engineering or changes shared coordinator state.
