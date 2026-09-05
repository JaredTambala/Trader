# Agent Contracts And State

All model-produced control values subclass a frozen strict Pydantic base with unknown fields forbidden. Primary values
include `CoordinatorAgenda`, `ToolCallProposal`, specialist turn contracts, `SpecialistReturn`, `CoordinatorDecision`,
operator interrupts/responses/cancellations, canonical evidence references, and terminal results.

## Public context

Models see bounded JSON projections: approved session facts, their role instruction, current phase, remaining budgets,
selected tool descriptions/schemas, normalized observations, and required evidence. They do not see credentials, raw
database rows, another specialist's private history, arbitrary repository contents, or hidden runtime objects.

## Validation layers

1. JSON response parsing occurs at the provider boundary.
2. Pydantic validates shape, types, sizes, enums, and cross-field invariants.
3. Role policy validates authority, scope, phase, side effect, dependencies, budgets, and lifecycle state.
4. MCP schema validation checks the real transport description.
5. Canonical evidence validation re-reads identity, owner, status, hash, and scope.

A single schema-only repair may return public validation errors to the same model invocation. Semantic policy failures
do not trigger a model rewrite or hidden corrective loop; they become explicit public failures or coordinator-visible
issues.

## Public observability events

`AgentObservabilityEvent` is the single public event contract for the console, tests, and later MLflow or approved
durable milestone adapters. Its schema version, semantic name, fixed level, state-authority classification, aware UTC timestamp,
process-local sequence, correlation identities, bounded fields, and optional classified public error are validated
together. Rejection and failure events require an `AgentEventError` with a stable code, category, public message, and
retryability flag. That message is purpose-written public text; instrumentation must not copy an arbitrary exception
string into it.

INFO is the coherent operator narrative. DEBUG adds diagnostic detail but does not expose a larger security boundary.
WARNING and ERROR identify explicit rejection or failure. Schema-specific projectors choose what is visible at each
detail level before the event reaches a sink; renderer or sink selection is not allowed to weaken redaction.

Event authority has three values:

- `diagnostic` describes execution activity only;
- `recovery_state` describes a validated checkpoint transition;
- `canonical_record` describes an already accepted product record, such as a committed coordinator decision.

The observability event itself remains diagnostic regardless of this label. Canonical artifact and decision stores
remain authoritative.

## Stored state

Checkpoints store validated public values, stable identities, accepted observations, branch/delegation lineage,
lifecycle summaries, pending interrupts, terminal results, and cumulative usage. They exclude raw prompts, raw model
responses, hidden reasoning, credentials, and complete unbounded tool payloads.
