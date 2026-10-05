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

## Replay identity evidence

`dataset_manifest.replay_data_identity` is the Data-owned proof attached to a qualified scope. It uses the
`sha256:bar-content-v1` algorithm and records a canonical content digest, row count, source semantics, and inspection
timestamp. A backtest specification snapshots this payload. A successful `backtest_run` adds an execution receipt with
the qualified and observed digests, observed row count/source semantics, and validation timestamp. Consumers must treat
missing or mismatching identity evidence as a refusal to execute; a query-scope `dataset_id` or a copied manifest hash
alone does not prove the bars that the runner replayed.

## Human paper-candidate admission

`paper_candidate_admission` is the governance record between research evidence and paper-runtime startup. It is
owned by the Orchestration domain, but only a human principal may create, approve, reject, or revoke it. The record
pins the candidate reference, exact strategy/risk/data versions, evidence references and payload digests, risk limits,
broker/account scope, monitoring policy, unresolved limitations, decision, approver, decision time, and expiry. A changed evidence payload or
source hash blocks revalidation; approved records also block after expiry or revocation. Revocation creates an
append-only successor and does not mutate the original record. Any later material admission change follows the same
successor rule. Agents and MCP identities have no admission authority,
and this contract performs no broker or runtime mutation.

## Human next-decision revisions

`research_next_decision` is the human-owned review boundary after a backtest. A revision records exactly one
`reject`, `refine`, or `continue` outcome, rationale, operator, decision time, source `backtest_run`, Data artifact,
implementation references, assumptions, review artifacts, and explicit limitations. `refine` and `continue` must carry
a `BoundedNextExperiment` with its own Data and implementation references, evaluation window, run limit, and success
criteria; `reject` cannot carry a successor. The constructor resolves every reference through the canonical store,
checks pinned source or payload hashes, rejects missing or incompatible review evidence, and permits only a human or
operator principal to write.

Decision identity is content-derived. The first revision is `1`; later revisions append a contiguous revision and point
to the immediately preceding artifact through `supersedes_artifact_id`. Existing revisions remain immutable and exact
replays return the original record. The Postgres projection `research_next_decisions` exposes query fields for the
Console while the full payload in `research_artifacts` remains authoritative. The record is a research decision only:
it does not approve deployment, paper trading, profitability, or broker mutation.
