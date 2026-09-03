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

## Stored state

Checkpoints store validated public values, stable identities, accepted observations, branch/delegation lineage,
lifecycle summaries, pending interrupts, terminal results, and cumulative usage. They exclude raw prompts, raw model
responses, hidden reasoning, credentials, and complete unbounded tool payloads.
