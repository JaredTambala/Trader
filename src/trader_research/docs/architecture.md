# Research Capability Architecture

## Purpose and product boundary

The package provides deterministic, inspectable research operations beneath both human-written workflows and
model-backed agents. It turns normalized requests into plain application results and immutable canonical artifacts. A
service validates one bounded operation, calls injected ports, and returns an `ApplicationResult`; it does not decide
which research action should happen next.

The package may read bounded Trader core evidence and run explicitly enabled backtests or provider operations. It has no
live-trading authority. It cannot clear a halt, mutate a broker, bypass strategy admission, or turn a research result
into an order. The trading runtime does not call MCP and does not depend on research services to execute its hot path.

The package boundary is:

```text
core market/event evidence
          |
          v
  request normalization -> context service -> canonical artifact
          |                                      |
          +---------- ApplicationResult --------+
                                                 v
                                  MCP adapters and model agents
```

MCP adds transport, tool metadata, side-effect policy, and environment gates. It does not replace the deterministic
service or reinterpret its result.

## System principles

### Evidence before interpretation

Every durable claim has an owning context, stable identity, source or input lineage, and a status. A headline metric is
not a conclusion. Evaluation and Adversarial review consume canonical experiment evidence and retain their own findings
instead of rewriting the experiment.

### Explicit authority

Artifact domain ownership is separate from the tool that produced an artifact, the workflow that requested it, and the
actor that invoked it. Persisted records distinguish `domain_owner`, `producer_tool`, `requested_by`, and `actor`.
Governance validates those dimensions before a write; one field never silently grants another authority.

### Deterministic core, effectful shell

Domain normalization, identity, validation, comparison, and decision helpers stay deterministic. Postgres, filesystem,
Docker, provider network calls, clocks, and tracking sinks are injected effects. Provider SDK payloads are normalized at
the adapter boundary before application logic sees them.

### Append-only evidence

Existing canonical evidence is not edited in place. A revision creates a successor or a new branch, and a content
conflict is an integrity error. This lets a recovered caller distinguish an unstarted operation, a prepared operation,
and an accepted terminal result without blindly repeating a mutation.

### References are capabilities only after validation

`research://postgres/{artifact_type}/{artifact_id}` identifies a durable record; it is not permission to trust an
arbitrary caller payload. Consumers re-read the exact canonical record and validate its type, owner, status, scope,
lineage, and content identity before using it.

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

### Context responsibilities

Each context has one job and a public facade. The facade is the supported import boundary; implementation modules and
concrete adapters remain behind it.

| Context | Owns | Typical question |
| --- | --- | --- |
| `foundation` | identities, results, artifact references, and persistence ports | What stable value crosses this boundary? |
| `governance` | ownership, authority, handoffs, sessions, approvals, protocol values, and paper admission | Who may create or consume this artifact? |
| `data` | symbol discovery, inventory, quality, bounded loading, and dataset evidence | Is the requested market data complete and fit? |
| `knowledge` | registered sources, chunks, retrieval, claim spans, citations, and method-card state | Which source-backed claims support this method? |
| `methodology` | method contracts, implementation validation, diagnostics, kernels, and packages | Does a supplied method satisfy its contract? |
| `coding` | isolated candidate workspaces, bounded checks, and inert packages | Can a candidate be inspected and admitted safely? |
| `experiments` | implementation admission, specifications, backtests, optimisation, and projections | What exactly was run, under which assumptions? |
| `review` | independent evaluation and adversarial evidence | What could invalidate or weaken the result? |
| `ml` | deployment manifests, adapter registries, and provider-neutral runtime resolution | Can this exact model identity be resolved? |
| `infrastructure` | Postgres and optional provider implementations | How does an outer effect implement the inner port? |

The package's public ownership maps are implemented in
`src/trader_research/governance/ownership.py` and `src/trader_research/governance/artifacts.py`.
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

## Application boundary and evidence flow

The usual supplied-implementation workflow is:

```text
bounded request
   -> data inventory and quality evidence
   -> exact implementation and validation
   -> strategy/risk/backtest specifications
   -> canonical backtest run
   -> comparison or optimisation evidence
   -> independent Evaluation and Adversarial reports
```

Knowledge-backed authoring adds source registration, ingestion, retrieval, claim-span selection, field extraction,
candidate validation, and a draft method card before implementation work. The method card is evidence about a method,
not permission to ship code.

At each edge, the caller should be able to answer four questions:

1. What exact input scope and revision did this operation use?
2. Which context owns the resulting artifact?
3. Which assumptions, warnings, or blockers were recorded?
4. Which stable references must be re-read before the next mutation or conclusion?

## State and authority

Agents own bounded decisions. Domain contexts own canonical artifacts. A persisted record separates `domain_owner`,
`producer_tool`, `requested_by`, and `actor`; none of those fields silently grants another kind of authority.
A deterministic execution service is not an agent and owns no research claim.

The canonical proposal remains immutable while material assumptions are decided through explicit approvals on an
`ExperimentProtocol`. Robustness findings feed Evaluation rather than being overwritten by the coordinator.
Backtest execution, optimisation scheduling, and risk evaluation do not become agents merely because the coordinator
invokes them. Deterministic services own those mechanics; Strategy Engineering is a bounded specialist because it must
reason about catalogue comparison, reuse, adaptation, and source authoring.

Paper operation has a separate human-owned admission boundary. `paper_candidate_admission` records exact candidate,
strategy, risk, data, and evidence identities plus limits, broker scope, monitoring, expiry, and revocation. Its
validator re-reads canonical evidence before reporting eligibility; no research agent, MCP adapter, or admission
projection can create broker state or approve on behalf of a human.

Artifact domain ownership is distinct from the tool that produced the artifact, the workflow that requested it, and
the actor that invoked it. Governance validates those dimensions before persistence. Existing canonical evidence is
append-only: revision creates a successor or new branch rather than rewriting an accepted record.

The package can run deterministic backtests and bounded provider operations when explicitly enabled by composition.
It has no live-trading authority. It cannot use a research result to bypass strategy admission, approvals, protected
evidence roles, or operational controls in `trader`.

### State and source of truth

There are three related but different kinds of state:

| State | Owner | Meaning |
| --- | --- | --- |
| `ApplicationResult` | the invoking service | one bounded operation outcome; useful for the current call only |
| canonical research artifact | owning research context and its store | durable evidence, identity, status, lineage, and payload |
| tracking projection or agent checkpoint | its outer adapter/runtime | operational convenience; never authoritative research evidence |

The `knowledge` context owns its `KnowledgeStore` port and domain values. Concrete SQL is an outward concern under
`infrastructure.postgres.knowledge`, whose schema, row normalization, low-level repository, and
`PostgresKnowledgeStore` adapter implement that port. The same inward dependency rule applies to the canonical
research artifact store.

When a mutation response is lost, the caller reads by stable operation or artifact identity and reconciles the canonical
record. A read-only operation may be retried within its deadline. An ambiguous provider or persistence mutation is not
blindly repeated; it returns a reconciliation-required error when the terminal state cannot be established.

## Deterministic core and effectful shell

Domain normalization, identity, validation, comparison, and decision helpers stay deterministic. Postgres, filesystem,
Docker, provider network calls, clocks, and tracking sinks are injected effects. A mutating operation records enough
identity and status to distinguish an unstarted call, a prepared call, and an accepted terminal result, so a recovered
caller never blindly repeats a potentially successful mutation.

## Extension process

Add capability to the owning context, expose it through that context's `__init__.py`, define artifact authority when it
creates evidence, and test deterministic behavior before adapters. If agents need the capability, add a separately
reviewed MCP contract and role policy; do not import the new service from agent code.

Update the package usage guide, the relevant MCP catalogue and contract pages, and the cross-package workflow when the
public path changes. Keep the deterministic service and its focused tests independent of adapters. Context facades are
the supported import boundary; removed monolithic modules have no aliases or dual-write path.

The public ownership maps are implemented in `src/trader_research/governance/ownership.py` and
`src/trader_research/governance/artifacts.py`.

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
