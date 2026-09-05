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

### Knowledge persistence boundary

The `knowledge` context owns typed source, evidence-unit, embedding, ingestion, and method-card values together with
the `KnowledgeStore` port. Concrete SQL is an outward concern under
`infrastructure.postgres.knowledge`: its schema, row normalization, low-level record repository, and
`PostgresKnowledgeStore` adapter all live there. The Postgres infrastructure imports the knowledge port and domain
values; the knowledge context never imports back from infrastructure.

Application composition imports `PostgresKnowledgeStore` from `trader_research.infrastructure.postgres`. It is not
available from `trader`, and the public `trader_research.knowledge` facade deliberately exposes only the inner
knowledge contract and services. This direction keeps the deterministic context usable with local and in-memory
stores without loading psycopg or acquiring a connection.

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

## Verification ownership

Tests mirror the package's bounded contexts under `tests/trader_research/`. Foundation tests protect transport-neutral
results, generic artifact records and stores, and projection-registry dispatch. Governance tests protect the closed
artifact-authority vocabulary, bounded specialist handoffs, agent-session decisions, orchestration plans, strict
experiment-protocol proposals and approvals, canonical-input drift checks, and typed Postgres projections. The
Postgres projection modules include offline schema assertions, but their marked adapter tests run only against the
guarded verification database; a filename does not make every test inside it an external integration.

The context that owns the asserted contract determines placement. A foundation identity helper or the generic
Postgres artifact store can be a real collaborator without taking ownership away from a governance contract.

Knowledge tests likewise remain under `tests/trader_research/knowledge/` across domain, local application, embedding,
filesystem-store, and Postgres-adapter levels. That ownership includes method-card lifecycle, open-world methodology
candidate discovery, target-bound evidence packets, field extraction and validation, and claim-span isolation because
those contracts are implemented by the Knowledge context. Computational method contracts, supplied implementation
validation, diagnostics, kernels, and packaging remain under `tests/trader_research/methodology/`. The concrete schema
and row helpers live in infrastructure, but their tests protect the knowledge context's persistence contract. Execution
requirements remain markers and collaborator descriptions rather than directory axes.

Coding tests live under `tests/trader_research/coding/`. Their workspace lifecycle-and-isolation contract uses the
real filesystem service, an injected check runner, and a fake Docker-compatible executable to prove command
construction and host-enforced limits without launching a real container. Implementation catalogue search,
comparison, and maintained templates remain Experiments contracts even when Strategy Engineering consumes them.

Experiments tests live under `tests/trader_research/experiments/`. Catalogue and template modules protect
implementation discovery separately from admission. Parameter optimisation is split into canonical workflow and
selection, objective/strategy isolation policy, and the optional Optuna provider profile so deterministic behavior,
security failures, and provider configuration do not obscure one another. A typed Postgres projection module combines
offline schema assertions with one explicitly marked guarded adapter test. Prediction-bound strategy specifications
also live here: research ML supplies a deployment read port and maintained mappers supply semantics, but Experiments
owns the strategy specification, its dependency pins, and revalidation.

Research ML tests live under `tests/trader_research/ml/`. Deterministic deployment creation, immutable dependency
validation, and adapter parity form one offline lifecycle contract. Schema registration and typed deployment
projections form a separate module with one marked guarded Postgres case. Their shared provider-neutral adapter and
canonical upstream builders remain package-owned fixtures beside those tests.
