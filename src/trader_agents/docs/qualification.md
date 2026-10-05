# Agent Qualification

Qualification is layered because a scripted graph pass cannot prove model behavior and a good model transcript cannot
prove security or recovery.

## Evidence layers

- contract tests: strict schemas, policy, budgets, identities, envelope normalization, and graph invariants using
  deterministic fakes
- model-choice tests: the exact local model must choose appropriate specialists and stop on materially ambiguous briefs
- production-boundary tests: real stdio MCP, Postgres roles, Docker isolation, failure injection, recovery, idempotency,
  redacted traces, and retained public trajectory verification
- vertical behavioral scenarios: natural-language briefs exercise Data and Strategy selection, evidence review,
  revision, interruption, loop termination, and prohibited actions
- bounded scale and final acceptance: repeated runs against one immutable code/model/tool/environment freeze

## Current status

The implementation passes its focused scripted, security, isolation, observation, persistence, and recovery checks.
The active LFM profile selected Data correctly for equivalent readiness briefs but returned executable work for a brief
with material ambiguity. A later diagnostic execution of the still-gated Data contract failed twice at strict
turn-schema validation before any MCP call. The combined model gate therefore remains failed and the broader campaign
was not promoted. No fallback or post-hoc output rewrite counts as acceptance.

The canonical current statement is in [Product State](../../../docs/product_state.md). When qualification resumes, all
mandatory phases must run against the same clean revision, exact model digest, isolated Postgres profile, tool catalogue,
program identities, and container image before a canonical acceptance record can be written.

The deterministic retained trajectory fixture uses `RetainedTrajectorySink` with the existing event and checkpoint
projections. Its optional atomic JSON `storage_path` is reloaded by a fresh Python process in the qualification test,
so process replacement proves recovery from retained public evidence rather than only changing an in-memory process ID.
It also proves concurrent Data and Strategy branch attribution, terminal decision receipt lineage, recursive redaction,
duplicate rejection, and fail-closed sink outage handling. The UJ-04 session qualification fixture runs isolated completed,
failed, and cancelled cases with stable session, branch, run, and artifact identities; it includes a missing-checkpoint
case whose recovery and terminal-lineage verdicts remain false. This fixture qualifies the public evidence boundary; it
does not promote a model profile or make diagnostic events canonical research artifacts.
