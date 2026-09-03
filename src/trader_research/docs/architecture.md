# Research Capability Architecture

## Purpose

The package provides deterministic, inspectable research operations beneath both human-written workflows and
model-backed agents. It turns normalized requests into plain application results and immutable canonical artifacts. It
does not decide which research action should happen next.

## Context map

```text
foundation <- governance
     ^            ^
     |            |
     +-- data ----+
     +-- knowledge/methodology
     +-- coding
     +-- experiments
     +-- review
     +-- ml

outer composition -> infrastructure/provider adapters
trader_mcp -> public context facades
trader_agents -> trader_mcp (never directly to context internals)
```

`foundation` cannot depend on a business context. Contexts exchange stable artifact references and bounded handoff
values, not another context's internal database rows. `infrastructure` implements ports defined inward.
Provider SDK payloads are normalized before reaching application logic, never inside the domain model.

## Application boundary

Public context functions return `ApplicationResult`: `ok`, operation, data, artifact references, warnings, structured
errors, and schema version. They must not add MCP metadata. The MCP adapter supplies tool ownership and side-effect
classification without changing the domain result.

Canonical writes use `ResearchArtifactStore` and a domain owner fixed by artifact type. IDs and content hashes are
stable over normalized payloads. A reference of the form `research://postgres/{artifact_type}/{artifact_id}` identifies
the durable record; it is not permission to trust an arbitrary caller-provided payload. Consumers re-read and validate
the exact canonical record.

## State and authority

Agents own bounded decisions. Domain contexts own canonical artifacts. A persisted record separates `domain_owner`,
`producer_tool`, `requested_by`, and `actor`; none of those fields silently grants another kind of authority.
A deterministic execution service is not an agent and owns no research claim.

The canonical proposal remains immutable while material assumptions are decided through explicit approvals on an
`ExperimentProtocol`. Robustness findings feed Evaluation rather than being overwritten by the coordinator.
Backtest execution, optimisation scheduling, and risk evaluation do not become agents merely because the coordinator
invokes them. Deterministic services own those mechanics; Strategy Engineering is a bounded specialist because it must
reason about catalogue comparison, reuse, adaptation, and source authoring.

Artifact domain ownership is distinct from the tool that produced the artifact, the workflow that requested it, and
the actor that invoked it. Governance validates those dimensions before persistence. Existing canonical evidence is
append-only: revision creates a successor or new branch rather than rewriting an accepted record.

The package can run deterministic backtests and bounded provider operations when explicitly enabled by composition.
It has no live-trading authority. It cannot use a research result to bypass strategy admission, approvals, protected
evidence roles, or operational controls in `trader`.

## Deterministic core and effectful shell

Domain normalization, identity, validation, comparison, and decision helpers stay deterministic. Postgres, filesystem,
Docker, provider network calls, clocks, and tracking sinks are injected effects. A mutating operation records enough
identity and status to distinguish an unstarted call, a prepared call, and an accepted terminal result, so a recovered
caller never blindly repeats a potentially successful mutation.

## Extension process

Add capability to the owning context, expose it through that context's `__init__.py`, define artifact authority when it
creates evidence, and test deterministic behavior before adapters. If agents need the capability, add a separately
reviewed MCP contract and role policy; do not import the new service from agent code.

The public ownership maps are implemented in `src/trader_research/governance/ownership.py` and
`src/trader_research/governance/artifacts.py`. Context facades are the supported import boundary; removed monolithic
modules have no aliases or dual-write path.
