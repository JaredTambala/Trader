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

The UJ-09 evidence-graph fixture composes those retained identities with exact
revisioned artifact references. `SessionEvidenceGraph` preserves branch and
edge identity while `verify_session_evidence_graph` reports complete, partial,
or blocked evidence without converting missing, incompatible, or negative
producer results into a positive claim. Its atomic JSON store is reopened in a
fresh process by `tests/trader_agents/observability/test_evidence_graph.py`;
the resulting projection is deterministic for Console rendering and contains
no prompts, hidden reasoning, or raw tool payloads.

The UJ-04 lifecycle qualification exercises the actual Coordinator runtime with
two concurrent sessions sharing one checkpointer. It covers the legal creation,
inspection, operator response, cancellation, and terminal-replay transitions;
uncreated and foreign-operator commands fail with named checkpoint or authority
errors. A replacement runtime instance recovers a lost cancellation response
without another terminal event or canonical receipt. Tampered session content or
root-branch identity is rejected before inspection or terminal replay. The
in-process tests use static model and MCP collaborators. A guarded Postgres
test opens a new operating-system process after a lost cancellation response,
inspects the exact persisted terminal state, and proves start/cancel retries
execute no model call, decision write, or terminal event. Neither test claims
cross-process writer exclusion or promotes the gated model.

The UJ-07 handoff-lineage qualification uses the public two-specialist fixture to exercise the coordinator's actual
join and checkpoint validators. It rejects run/session, task scope/branch, role, delegation, attempt, and artifact
revision drift; exact duplicate delivery remains idempotent and changed content conflicts. A fresh Python process
reconstructs both branch identities and verifies retained return digests from public checkpoint state. These checks
qualify deterministic admission and recovery, not model judgment or a live canonical-store campaign.

The exact-resolution qualification uses a separately supplied canonical reader
against each named graph revision. It checks session, branch, run, scope,
strategy version, URI, owner, hash, and revision before exposing assessment
facts. The retained graph is reopened, then the cross-package test reads a
canonical research artifact record; replacing revision one with revision two
returns `stale` rather than silently using the newer report. Missing,
incompatible, redacted, and negative evidence remain separate, and review
uncertainty, exclusions, statistical/robustness status, and blockers remain
visible. This test does not substitute for independent scientific review or a
real-model qualification gate.

Run the retained exact-resolution verifier with
`uv run pytest tests/cross_package/qualification/test_session_review_resolution.py -q --basetemp=/tmp/trader-uj09-resolution`.

The test writes

`/tmp/trader-uj09-resolution/test_retained_graph_resolves_e0/uj09-review-resolution-verifier.json`.
The bounded JSON names fixture `uj09-exact-review-resolution-v1`, the
`SessionReviewResolution` contract version, the checkout commit, the named
artifact revision, and the initial and stale-after-replacement verdicts. It is
qualification output from the actual retained graph and canonical-store read,
not a product artifact. Existing Evaluation/Robustness producers do not all
carry the complete session/branch/scope/strategy attribution required by this
resolver; they fail closed until a trusted product composition supplies it.
