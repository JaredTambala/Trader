# Checkpointing And Recovery

Operational checkpoints use `langgraph-checkpoint-postgres` through a dedicated DSN and role. They are distinct from
canonical research artifacts: checkpoints answer where execution can resume, while canonical records answer what
research evidence and decisions exist.

Coordinator and specialist threads have deterministic identities derived from session, branch, role, delegation, and
attempt. Every state validates the immutable session/program/model/catalogue pins on load. A mismatch stops recovery
instead of migrating or silently starting again.

The mutation rule is checkpoint-before-effect where possible and reconcile-after-ambiguity where not. Coordinator
decision application checkpoints the validated decision before append-only receipt mutation. Tool mutations use stable
operation records in their owning service. A fresh process reads the last public checkpoint and canonical operation
state, then continues without replaying accepted work.

`inspect` exposes a redacted projection. `resume` requires an actual pending interrupt and the owning operator identity.
`cancel` stops an in-flight task owned by the runtime, records a terminal cancelled decision, and leaves ambiguous
provider operations to their reconciliation contracts.
