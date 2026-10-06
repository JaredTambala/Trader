# Checkpointing And Recovery

Operational checkpoints use `langgraph-checkpoint-postgres` through a dedicated DSN and role. They are distinct from
canonical research artifacts: checkpoints answer where execution can resume, while canonical records answer what
research evidence and decisions exist.

Coordinator and specialist threads have deterministic identities derived from session, branch, role, delegation, and
attempt. Every state validates the immutable session/program/model/catalogue pins on load. A mismatch stops recovery
instead of migrating or silently starting again.

The application runtime validates the complete checkpoint shape and the session digest, root branch, Coordinator
program, model profile, and tool catalogue before it returns an interrupted or terminal result, exposes an inspection,
or applies a lifecycle command. This includes terminal replay: changing the operator, scope, budget, or other immutable
session content under an existing session ID fails closed. A retry of `start` after a lost terminal response returns the
persisted result without emitting a second terminal event or recording a second decision receipt. The checkpoint and
canonical decision receipt remain the recovery authority; the diagnostic event stream is not a transactional outbox.

The mutation rule is checkpoint-before-effect where possible and reconcile-after-ambiguity where not. Coordinator
decision application checkpoints the validated decision before append-only receipt mutation. Tool mutations use stable
operation records in their owning service. A fresh process reads the last public checkpoint and canonical operation
state, then continues without replaying accepted work.

At a specialist join, a replacement process can recover a response lost after the specialist terminal checkpoint was
saved. It validates the terminal return against the exact active delegation and current attempt, then admits that
return once. The coordinator retains prior negative and partial returns, but computes downstream eligibility from
the latest ready return for each task; a stale retry cannot requalify an older revision.

`inspect` exposes a redacted projection. `resume` requires an actual pending interrupt and the owning operator identity.
`cancel` stops an in-flight task owned by the runtime, records a terminal cancelled decision, and leaves ambiguous
provider operations to their reconciliation contracts.

The runtime also exposes `interrupt`, which cancels only the active in-process task after its last completed
checkpoint and persists a synthetic `operator_pause` boundary. A fresh runtime process materializes the normal
LangGraph `await_operator` edge before applying a typed `OperatorResponse`; the pause therefore remains resumable
without replaying provider work. An expired Console worker lease becomes ambiguous and is never retried automatically.

The human Console workspace reads the public session and decision projections rather than checkpoint blobs. Its
operator actions are durable command intents, scoped to the session owner and idempotency key; runtime composition
consumes those intents and applies the same interrupt, resume, or cancellation checks described above. Missing or
incompatible producer projections fail closed, and a Console command never grants an agent additional authority.
