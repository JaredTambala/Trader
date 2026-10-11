# Durable Research Operation Model

Status: accepted design decision (2026-10-11). This document resolves the long-running operation gate in TRD-105. It
specifies the execution boundary for deterministic backtest, optimisation, walk-forward (WFO), and training work. It
is a contract and ownership decision, not a claim that the future WFO or training producers are implemented.

## Decision

Costly or externally effectful research execution uses a durable job boundary. A caller performs synchronous preflight,
validation, compilation, status, and reconciliation reads; it does not hold an MCP request open while running a backtest,
optimisation, WFO, or training operation. All four operation kinds use the same lifecycle and recovery semantics so a
future producer cannot invent a second retry or ambiguity model.

The job service is a deterministic execution service, not an agent. The Research Coordinator or the owning specialist
chooses whether to submit a permitted operation. Code owns admission, scheduling, leases, retries, persistence,
reconciliation, and resource enforcement. Human approval remains required for material assumptions, protected-data
access, external research mutation, and any operation outside the approved envelope.

| Call | Mode | Contract | Authority |
| --- | --- | --- | --- |
| preflight/validate/compile | synchronous bounded | typed request and validation result | owning deterministic service; no execution side effect |
| submit | synchronous admission | idempotency key returns a `ResearchJob` in `queued` state | Coordinator/specialist may submit only an approved request |
| get/list status | synchronous bounded | bounded public job projection | read-only; never recomputes research truth |
| cancel | synchronous command | append-only cancellation receipt | operator or explicitly authorised workflow; best effort after a child starts |
| reconcile | synchronous bounded | canonical child/provider identity and next action | worker or operator; required after an ambiguous outcome |
| execute | durable worker | `ResearchJob` state plus canonical child artifacts | deterministic executor under pinned policy and lease |

A synchronous fast path is intentionally not retained for the operation itself. If an implementation is small enough to
finish quickly, it still enters the same job contract; the worker may complete before the submit response is observed.
This prevents callers from branching on timing and makes recovery, audit, and test isolation consistent.

## Typed contract

The canonical owner is `trader_research.governance.orchestration.operations`. `ResearchJob` is operational state, not a
research artifact. Its public fields are:

- `job_id`, `operation_kind`, `request_ref`, and `request_digest` identify the immutable request;
- `idempotency_key` prevents duplicate submission;
- `requested_by`, `actor`, `code_identity`, and `environment_identity` preserve authority and reproducibility;
- `status`, `attempt`, and `retryable` expose lifecycle state without worker internals;
- `produced_artifact_refs`, `warnings`, and `blockers` expose bounded canonical evidence and degraded outcomes.

`ResearchOperationKind` is closed over `backtest`, `optimization`, `walk_forward`, and `training`. `ResearchJobStatus`
is closed over `queued`, `running`, `partial`, `succeeded`, `failed`, `cancelled`, `ambiguous`, and
`reconciliation_required`. Ambiguous and reconciliation-required states always carry a blocker and cannot be retried
until canonical child/provider state has been inspected. Partial state is non-terminal and must retain the completed
child refs and the blocker for the unfinished work. Terminal records are append-only; a retry creates a new attempt
record under the original idempotency lineage.

The projection never includes prompts, hidden reasoning, credentials, raw provider payloads, checkpoint bytes, or a full
MCP transcript. Canonical research artifacts remain owned by their domain contexts. A job reference is not evidence by
itself; consumers re-read each exact artifact ref before interpretation.

## Lifecycle and recovery

1. **Preflight** validates the request, approvals, scope, resource budget, policy gates, and pinned code/provider
   identities. It returns blockers synchronously and writes no execution result.
2. **Submit** derives a stable idempotency key from the approved request identity and actor. An exact repeat returns the
   existing job; a conflicting payload under that key fails closed.
3. **Claim** creates a lease for one worker and increments the attempt. A lease heartbeat is operational state only.
4. **Execute** writes child artifacts through their owning deterministic services. Each child is idempotent by its exact
   specification and attempt identity. Workers may run independent optimisation trials or WFO folds concurrently, but
   joins and terminal job transitions are serialized by the job owner.
5. **Complete** records all produced refs and a terminal success, failure, cancellation, or partial outcome. Evidence is
   append-only; later review never edits the job's historical outcome.
6. **Recover** first reloads the job, request digest, lease, and child artifacts. A lost response is
   `ambiguous`/`reconciliation_required`, never an automatic replay. Reconciliation either recovers a complete
   terminal receipt, records a partial/failed outcome, or explicitly authorises a new attempt after proving no accepted
   side effect will be duplicated.

Resource exhaustion, worker death, lease expiry, provider timeout, and external MLflow loss are public blockers. A
provider run is not declared failed merely because the transport response was lost. Training reconciliation must compare
the pinned MLflow run/model identity and Trader artifact lineage before accepting or retrying a fit.

## Operation-specific obligations

- **Backtest:** pin the passed specification, implementation versions, Data/replay identity, costs, initial state, and
  runtime profile before submit. The result artifact is accepted only after the execution service revalidates those
  identities.
- **Optimisation:** pin the immutable protocol, engine profile, seed, search budget, objective, and trial ledger. Each
  trial is a child operation; rejected trials and exceptions remain visible. Selection and sealed holdout execution are
  separate child stages.
- **WFO:** pin folds, purge/embargo, selection/OOS boundaries, candidate budget, and stop policy before submit. Fold
  joins cannot expose OOS results to same-fold selection; stitched OOS review is a later Evaluation-owned artifact.
- **Training:** pin dataset/split/feature identities, trainer source, dependency environment, model profile, and MLflow
  policy. MLflow writes, fitting, evaluation, registry mutation, and alias promotion have separate gates. Training
  recovery reconciles external run identity before a retry.

## Ownership and delivery consequences

The MCP adapter will expose submit/status/cancel/reconcile projections only after the deterministic job service and
persistence schema are implemented. Existing synchronous validation and read tools remain bounded. Backtest and
optimisation producers must migrate their execution entry points to this contract before WFO or training execution is
claimed. This decision therefore unblocks design work for the blocked job lifecycle and evidence-join items while
preserving their separate implementation and qualification gates.
