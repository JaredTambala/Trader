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

## Trust model

An `ArtifactReference` is a pointer, not evidence by itself. At a trust transition, load the canonical record through
the configured store, require its expected type and accepted status, and compare its digest/scope to the requested
work. Never make an execution decision from an LLM-authored restatement of an artifact.

## Idempotency and revision

Content-derived IDs make equivalent deterministic artifacts converge. Operations with external or filesystem side
effects also use stable operation records. A changed material input creates a new identity or successor record. Accepted
records are not edited to make a later run appear prospective.

## Projection

MLflow and filesystem exports are non-authoritative projections unless a contract explicitly says otherwise. The
canonical Postgres artifact remains the source of workflow truth, while projections support observation, comparison,
and interoperability.
