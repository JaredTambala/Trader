# Data Research Agent Design

Status: architecture review in progress; no implementation is authorized by this document.

Last reviewed: 2026-08-24.

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

## Provisional mission

Given a bounded research request, determine the complete data scope required to test it, use available Data MCP
capabilities to discover and prepare that scope, and return canonical evidence stating whether the requested data is
ready and fit for the intended backtest.

The mission covers data readiness. It does not cover experiment design, strategy selection, performance judgment, or
choosing a more favorable asset after seeing results.

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

## Remaining architecture record

The following sections remain pending structured review:

- exclusive decisions and final hard boundaries;
- complete entry and readiness contracts;
- context and trust boundary;
- model-program and structured-output requirements;
- final role-scoped MCP/resource surface;
- internal discovery, quality, remediation, and revalidation loop;
- durable state and recovery;
- evidence-return contract;
- termination and escalation;
- evaluation scenarios and promotion evidence; and
- concurrency, scope aggregation, and handoff rules.
