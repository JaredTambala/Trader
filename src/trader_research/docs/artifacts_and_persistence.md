# Artifacts And Persistence

Canonical research artifacts are immutable, typed records. Each contains an artifact type and ID, domain owner,
producer tool, requester/actor attribution where required, status, metadata, normalized payload, source hash, schema
version, and timestamps supplied by the concrete store.

`foundation.artifacts` owns the generic record/reference/store contract. `governance.artifacts` maps business artifact
types to their exclusive domain owner. Concrete Postgres persistence lives in `infrastructure.postgres`.

Research knowledge persistence uses a separate, context-specific `KnowledgeStore` port. Its Postgres schema and
adapter live under `infrastructure.postgres.knowledge` and are exposed to composition as
`trader_research.infrastructure.postgres.PostgresKnowledgeStore`. This store owns knowledge sources, evidence units,
embedding indexes and vectors, ingestion reports, and method-card revisions. None of those tables or adapters belongs
to the core `trader` event store.

## Record anatomy and lifecycle

An artifact record answers four questions before another context consumes it:

| Field group | Purpose |
| --- | --- |
| type, ID, schema version | identifies the contract and exact revision |
| domain owner, producer tool, requester, actor | records authority and provenance separately |
| status, timestamps, operation identity | describes lifecycle and recovery state |
| normalized payload, source hash, scope, lineage | makes the evidence reproducible and comparable |

The normal lifecycle is `prepare -> validate -> persist -> read and revalidate`. The application service owns the
deterministic preparation and validation rules; the concrete store owns durable persistence and transaction behavior.
Consumers do not treat a successful write response as a substitute for re-reading the accepted canonical record.

## Trust model

An `ArtifactReference` is a pointer, not evidence by itself. At a trust transition, load the canonical record through
the configured store, require its expected type and accepted status, and compare its digest/scope to the requested
work. Never make an execution decision from an LLM-authored restatement of an artifact.

## Idempotency and revision

Content-derived IDs make equivalent deterministic artifacts converge. Operations with external or filesystem side
effects also use stable operation records. A changed material input creates a new identity or successor record. Accepted
records are not edited to make a later run appear prospective. A later admission for the same candidate must carry
`supersedes_admission_id` pointing to an existing admission for that candidate; unlinked material changes are rejected
at the persistence boundary.

## Projection

MLflow and filesystem exports are non-authoritative projections unless a contract explicitly says otherwise. The
canonical Postgres artifact remains the source of workflow truth, while projections support observation, comparison,
and interoperability.

## Human paper-candidate admission

`paper_candidate_admission` is the governance record between research evidence and paper-runtime startup. It is
owned by the Orchestration domain, but only a human principal may create, approve, reject, or revoke it. The record
pins the candidate reference, exact strategy/risk/data versions, evidence references and payload digests, risk limits,
broker/account scope, monitoring policy, unresolved limitations, decision, approver, decision time, and expiry. A changed evidence payload or
source hash blocks revalidation; approved records also block after expiry or revocation. Revocation creates an
append-only successor and does not mutate the original record. Any later material admission change follows the same
successor rule. Agents and MCP identities have no admission authority,
and this contract performs no broker or runtime mutation.
