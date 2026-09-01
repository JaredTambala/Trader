# Strategy Engineering Agent Design

Status: architecture record accepted; first-slice implementation in progress and qualification pending.

Last reviewed: 2026-09-01.

This document is the canonical build-lifecycle architecture record for the Strategy Engineering Agent. Review status
and shared principles are maintained in the parent [Agent Designs](../agent_designs.md) tracker. System-level direction
remains in [Agentic Research Orchestration Redesign](../agentic_orchestration_redesign.md), and delivery status remains
in the [Research Capability Roadmap](../research_capability_roadmap.md).

## Established design constraints

The system-level and preceding specialist reviews establish these starting constraints:

- The agent may reuse, adapt, or author candidate strategy and risk implementations, but only inside a disposable,
  isolated coding workspace exposed through a role-scoped MCP catalogue.
- The model may choose among bounded repository search/read, workspace edit, allowlisted test, candidate packaging, and
  admission-request operations. It cannot bypass MCP for raw shell, filesystem, repository, or credential access.
- The product repository is a pinned read-only input to a research coding attempt. Candidate edits occur only in the
  disposable workspace; a research delegation never authorizes commits, pushes, pull requests, merges, or product-code
  modification.
- Candidate code and self-authored tests are untrusted. A content-addressed package must pass independent deterministic
  implementation admission before downstream research can consume it.
- For a knowledge-backed method, an accepted Quantitative Methods implementation brief fixes the behaviorally material
  semantics. The coding agent owns software construction and cannot reinterpret missing evidence or alter the brief.
- Admission failure may cause bounded diagnosis and revision inside a new immutable attempt. Passing admission proves
  interface and conformance requirements, not trading efficacy.
- Before authoring, the agent must use MCP catalogue capabilities to discover and compare relevant maintained and
  previously admitted implementations. Reuse, adaptation, and new authorship are evidence-based alternatives, not a
  fixed preference for generating new code.
- The agent has no broker, paper/live execution, infrastructure, unrestricted network, dependency-install, or
  production credential authority.

## Mission and exclusive decisions

Produce the smallest admissible, inspectable strategy or risk candidate that faithfully implements an accepted build
contract. Use the isolated Coding Workspace MCP to inspect relevant Trader interfaces and maintained patterns, decide
whether to reuse, adapt, or author code, run bounded development checks, package the exact candidate, and respond to
independent admission evidence without expanding the research question.

The mission ends at an admitted candidate reference and an explicit account of limitations, deviations, tests, and
unresolved blockers. It does not design the research method, approve a quantitative adaptation, define the experiment,
judge performance, or deploy the candidate.

Strategy Engineering exclusively decides:

- how to investigate the eligible implementation catalogue for one accepted build contract;
- whether exact reuse, bounded adaptation, or new authorship is the best engineering path;
- how to construct code and candidate-owned tests without changing the contract;
- which allowlisted workspace checks provide useful implementation evidence; and
- whether an actionable admission finding supports another bounded repair attempt.

It cannot decide missing quantitative semantics, approve its own implementation, waive a failed check, alter Data or
experiment scope, infer efficacy from code, use performance evidence for ordinary authoring, or grant execution,
deployment, paper-trading, or broker authority.

## Coding and admission authority

The agent may:

- inspect a pinned, policy-filtered repository snapshot and relevant interface documentation;
- search an approved catalogue of maintained implementations and decide whether reuse, adaptation, or new authorship
  best satisfies the build contract;
- create and revise candidate source and candidate-owned tests inside its disposable workspace;
- invoke allowlisted format, lint, type, unit, fixture, and packaging operations through MCP;
- submit a content-addressed package to the existing independent admission service; and
- diagnose bounded admission findings and produce a revised candidate attempt when the build contract is unchanged.

The agent may not approve its own candidate. Workspace success, plausible code, and self-authored tests are advisory
until the separately owned admission path revalidates source policy, interfaces, fixtures, provenance, and package
identity. The admitted artifact is durable; workspace files, build products, and conversational reasoning are not.

## Implementation catalogue discovery and comparison

Every coding attempt begins with a bounded implementation-catalogue investigation. The agent derives a comparison
signature from the accepted build contract and uses role-scoped MCP tools to search for candidates across relevant
implementation kinds. The signature includes behaviorally material fields such as:

- strategy, signal, indicator, feature, and risk responsibilities;
- runtime interfaces and portfolio mode;
- input roles, data types, frequencies, units, and timing;
- equations or decision rules, state, warmup, and missing-value behavior;
- parameter semantics and tunable boundaries;
- required dependencies and runtime context;
- validation status, source/provenance lineage, licence posture, and known limitations; and
- the exact Trader and implementation-contract versions against which the candidate was admitted.

The model compares plausible candidates against the brief field by field and records supported matches, material
differences, unknowns, reusable components, adaptation cost, and validation risk. Search ranking or textual similarity
is discovery evidence only; it cannot establish semantic equivalence.

The agent then makes one explicit build decision:

- **reuse** an exact pinned implementation version when its admitted behavior satisfies the build contract;
- **adapt** one or more retrieved implementations when the differences are permitted and bounded; or
- **author** a new implementation when no candidate is sufficiently compatible.

Adaptation always creates a new content-addressed candidate with parent implementation refs and a machine-readable
change account. Previous admission does not transfer to modified source: the adapted candidate passes the complete
current admission path. New authorship records the comparison evidence showing why reuse or adaptation was unsuitable.

### Required MCP affordances

The current MCP surface is only a partial baseline. `research_list_strategy_templates` and
`research_list_risk_manager_templates` expose maintained template metadata, while registration and validation tools
admit supplied source. There is no complete target capability for searching all previous admitted versions against a
brief, retrieving bounded implementation content, or comparing compatibility.

The target capability inventory must therefore define role-scoped operations or resources for:

- ingesting/indexing maintained, admitted, and explicitly permitted external implementation records into a versioned
  searchable catalogue without changing their canonical identity;
- searching by typed behavioral signature as well as lexical or semantic similarity;
- resolving exact manifests, admission evidence, provenance, limitations, parent lineage, and bounded source through
  immutable resources;
- producing or validating a field-level brief-to-implementation compatibility record;
- materializing an approved reusable or adaptable version into the isolated workspace; and
- refreshing the index after admission while preserving historical versions and reproducible search identity.

Ingestion, indexing, retrieval, and materialization are deterministic MCP services. The model chooses queries,
interprets comparison evidence, and decides reuse, adaptation, or new authorship. It cannot scrape the repository,
enumerate artifact storage, read arbitrary source paths, or make an unindexed implementation eligible by assertion.

### Catalogue trust and reuse eligibility

The accepted trust model distinguishes discovery from reuse authority:

- Maintained implementations and exact previously admitted implementation versions are eligible for direct reuse when
  a new brief-to-version comparison confirms compatibility with the current build contract and Trader interfaces.
- External, legacy, failed, quarantined, or otherwise unadmitted implementations may be indexed only in an explicitly
  labelled untrusted tier when provenance and licence policy permit. They are reference material, never executable
  reuse candidates.
- Turning reference material into a candidate creates a new content-addressed version with its source and parent
  lineage recorded and requires the full current admission path.
- Any source modification, including an adaptation of an admitted implementation, creates a new candidate. Admission
  status is attached to exact content and never inherited across a change.
- Stale, superseded, incompatible, or revoked versions remain discoverable for audit when policy permits but cannot be
  selected for direct reuse.

The agent may explain why an untrusted candidate appears relevant, but it cannot upgrade a trust tier, waive admission,
or treat past performance as implementation compatibility.

## Implementation entry contracts

Knowledge-backed authoring has a clear entry contract: an accepted implementation brief plus pinned Trader interfaces,
standards, permitted dependencies, workspace policy, resource budget, and requested implementation kind.

The accepted boundary permits the agent to start from either:

- an accepted source-backed implementation brief; or
- an operator-approved, knowledge-independent implementation specification with equivalent behavioral completeness,
  explicit provenance, material assumptions, and validation obligations.

A general research idea, promising result, or coordinator summary is not an implementation specification. Missing
behavioral semantics return to Quantitative Methods, Experiment Design, or the operator through the coordinator; the
coding agent does not fill them opportunistically.

Both routes are normalized into a typed build contract before workspace creation. The contract records its provenance
as `source_backed` or `operator_specified`; pins every behaviorally material decision, interface, dependency policy,
validation obligation, and approval; and identifies the exact artifact or operator decision that authorized it. The
operator-specified route makes no claim of textbook support and cannot use its approval to bypass implementation
admission.

The first build-contract schema contains:

- contract, session, branch, and approval identity;
- implementation kind and runtime interface;
- equations, decision rules, state transitions, timing, warmup, missing-value and failure behavior;
- input Data roles, fields, units, frequency and portfolio mode;
- parameter names, types, defaults, bounds, tunability, invariants and dependency relationships;
- required strategy, signal, indicator, feature and risk responsibilities;
- permitted libraries and pinned dependency policy;
- required deterministic fixtures, properties, edge cases and conformance obligations;
- Trader interface, Python version, code-quality profile and repository-snapshot identity;
- source-backed or operator-specified provenance plus material assumptions; and
- workspace, tool, repair, time, token and compute budgets.

Normalization is deterministic and fails on missing, contradictory, unsupported or unapproved material fields. It
does not use an LLM to complete the contract.

## Readiness, context, and trust boundary

The agent starts only after the build contract, repository snapshot, catalogue identity, workspace policy, model/tool
budgets and required approvals validate. A general idea, performance result, coordinator paraphrase, or unapproved
source is not a ready input.

The agent may see the complete accepted build contract, relevant bounded Trader interface documentation, role-scoped
catalogue results and resolved candidate manifests/source, its isolated workspace, deterministic check/admission
findings, and bounded summaries of its own earlier attempts. Normal authoring does not see experiment, optimisation,
robustness, walk-forward, evaluation, or sealed evidence.

Repository content, implementation records, source code, comments, tests, dependency metadata, workspace output and
tool/admission messages are untrusted observations. Embedded instructions cannot change the build contract, tool
surface, trust tier, dependency policy, budget, approval, or admission result. Deterministic middleware validates paths,
commands, resource use, output size, source hashes, package identity, canonical refs, and every mutation.

## Model program

The versioned Strategy Engineering program requires the model to derive a typed comparison signature, investigate the
catalogue, record a field-level comparison, choose reuse/adapt/author, work only through the Coding Workspace catalogue,
and return a structured candidate outcome. Admission findings may start a bounded diagnosis/repair cycle; successful
admission ends the invocation.

The program identity pins instructions, structured decision and evidence-return schemas, context policy, build-contract
version, tool-contract version and model profile. Provider changes and program revisions require evaluation before
promotion and cannot expand engineering authority.

## Capability surface

The role-scoped surface contains:

- bounded MCP health/config and canonical-resource reads;
- versioned implementation-catalogue search, resolution, compatibility, and approved materialization;
- Coding Workspace create, repository search/read, candidate read/write, allowlisted check, package, status, and destroy
  operations;
- policy-gated pinned dependency resolution when the build contract permits it; and
- strategy/risk registration, independent validation/admission, and exact admission-evidence reads.

It does not contain arbitrary shell, host filesystem, raw Git, general network, provider credentials, direct stores or
SQL, experiment execution, ML model operations, deployment, broker, commit, push, merge, or pull-request capabilities.
Runtime policy narrows even the listed capabilities by attempt state: for example, admission is unavailable before an
exact package exists, and editing is unavailable after accepted admission.

## Internal control loop

```text
validate accepted build contract and policy
  -> derive typed comparison signature
  -> search and resolve eligible catalogue candidates
  -> record field-level compatibility evidence
  -> choose reuse, adapt, or author
  -> provision isolated candidate attempt when code work is required
  -> inspect pinned interfaces and materialize only approved inputs
  -> edit and run bounded allowlisted checks through MCP
  -> package exact content-addressed candidate
  -> submit candidate to independent admission
  -> if actionable unchanged-contract defect and budget remains, revise in a new attempt
  -> otherwise return admitted candidate or explicit blocker
```

The model owns engineering investigation, construction, and bounded repair decisions. Deterministic services own
catalogue identity, workspace isolation, filesystem policy, commands, dependency access, resource enforcement,
packaging, admission, persistence, idempotency, cleanup, and canonical-ref validation.

## Sandbox authority

The accepted coding boundary is an ephemeral, resource-bounded container provisioned for one candidate attempt:

- A pinned Trader repository snapshot is read-only. Only a separate candidate workspace is writable.
- The model has no general network, host filesystem, product repository, infrastructure, broker, cloud, or production
  credential access.
- The agent chooses commands only from the active Coding Workspace MCP catalogue. Policy enforces allowlisted command
  forms plus CPU, memory, disk, process-count, output-size, and wall-time limits.
- Dependency resolution occurs only through a deterministic MCP capability using approved repositories or mirrors,
  pinned versions and hashes, licence policy, vulnerability policy, and the build contract's dependency envelope. The
  model never receives package-repository credentials or arbitrary installer/network access.
- A missing or disallowed dependency becomes a structured approval or build-contract revision request. The agent may
  not fetch, vendor, or substitute it opportunistically.
- Only the content-addressed candidate source, candidate tests, manifests, bounded execution evidence, and canonical
  admission refs leave the workspace. Ephemeral files and build products are destroyed after completion or terminal
  failure.
- Admission leaves the implementation inert research code. It grants no specification, experiment, deployment,
  paper-trading, or live-trading authority.

Exact container technology, base image, package mirror, default resource values, and command schemas remain
implementation/spike decisions. They must implement this boundary and be frozen in qualification evidence.

## Outcome visibility and diagnostic repair

Normal Strategy Engineering work is outcome-blind. Its context may include the build contract, implementation
catalogue comparisons, workspace checks, deterministic fixtures, admission evidence, and previous candidate-attempt
summaries. It does not include backtest, optimisation, robustness, walk-forward, evaluation, or sealed-holdout
performance.

The accepted exception is a coordinator-authorized diagnostic delegation when experiment evidence suggests an
implementation defect rather than weak strategy behavior. That delegation exposes only the bounded execution trace,
state transition, timing record, or invariant failure required to investigate the suspected defect. It does not expose
unrelated performance rankings, candidate-selection evidence, or sealed values.

The agent may repair code only when the accepted build contract remains unchanged. A behavior change, parameter-policy
change, new data role, or performance-driven strategy revision requires a successor build contract and immutable
research branch. Sealed evidence may motivate future research, but it cannot be used to iteratively repair the
candidate it evaluated.

## Admission revision and termination

Each build contract authorizes a bounded repair loop with explicit candidate-attempt, tool-call, elapsed-time, and
compute budgets. A failed admission may lead to revision only when the agent records:

- the exact actionable admission finding;
- a public defect hypothesis explaining the proposed repair;
- the files or components expected to change; and
- why the build contract remains unchanged.

Every revision is a new content-addressed candidate attempt. An equivalent failure without new evidence or materially
changed source terminates the loop. Brief ambiguity, prohibited dependencies, sandbox-policy denial, missing authority,
or a behaviorally material change escalates immediately instead of consuming repair attempts.

The first-slice implementation destroys a failed candidate workspace before admitting a repair transition, increments
the revision budget, derives a new immutable candidate-attempt identity, and requires independent admission again.
Focused tests cover one actionable failure followed by one admitted replacement, irreparable equivalent failures,
repository prompt injection, and replay-safe workspace cleanup. The container command is also fail-closed, digest-
pinned, non-root, networkless, read-only, resource-, deadline-, and output-bounded. Real-container, fresh-process repair
recovery, and repeated real-model qualification remain open.

Passing admission completes the mission; the agent cannot continue polishing or optimizing admitted code. Budget
exhaustion returns complete attempt lineage, the strongest available candidate and admission evidence, unresolved
blockers, and a recommended next action to the coordinator. Initial numeric limits are selected from measured framework-
spike recovery scenarios and then frozen in the active policy profile.

## Durable candidate state and recovery

Durable state contains the delegation and build-contract digests, catalogue/search identity, comparison refs, build
decision, candidate-attempt lineage, workspace policy and opaque workspace identity, completed operation receipts,
package/source hashes, check/admission refs, bounded public diagnostics, budgets, loop fingerprints, status, and pending
approval or cancellation state.

Hidden reasoning, credentials, unrestricted transcripts, raw tool payloads, host paths, arbitrary build products and
complete repository copies are never persisted as product state. A workspace is reconstructable only from its pinned
repository snapshot, build contract, approved materialization refs and retained candidate package. Recovery validates
accepted receipts before reissuing operations; it never edits or resubmits an already admitted package.

## Evidence-return contract

The structured return includes:

- agent-program, model-profile, tool-catalogue, session, delegation, branch, and attempt identities;
- build-contract identity and provenance route;
- comparison signature, considered implementation refs, field-level matches/differences/unknowns, and trust tiers;
- explicit reuse, adaptation, or authorship decision and rationale;
- parent refs and machine-readable changes for adaptations;
- exact candidate package, source, check, validation, and admission refs with expected hashes and owners;
- all candidate attempts and actionable findings, including failed and superseded attempts;
- assumptions, deviations, limitations, uncertainty, blockers and unresolved questions;
- consumed model, tool, time, repair and compute budgets; and
- advisory revision, contract-clarification, approval, or Experiment Design handoff actions.

The coordinator may reject a malformed or unresolvable return and request bounded revision. It cannot upgrade an
unadmitted candidate, erase failed attempts, or replace the engineering build decision without a new delegation.

## Evaluation contract

Evaluation covers:

- exact maintained/admitted reuse, bounded adaptation and justified new authorship;
- misleading lexical similarity, incompatible interfaces, stale admission, revoked versions and untrusted references;
- complete operator-specified and source-backed contracts plus missing/contradictory material semantics;
- isolated repository inspection, candidate edits, tests, packaging, cleanup and resource limits;
- actionable admission repair, equivalent repeated failure, prohibited dependency and required semantic change;
- malicious code/comments/tests/dependency metadata and attempts to access host, network, credentials, Git or broker
  capabilities;
- parallel disjoint candidate attempts without workspace, receipt or canonical-lineage collision;
- malformed tool/admission output, lost response, cancellation, restart and idempotent recovery;
- outcome isolation and rejection of supplied performance-driven instructions; and
- contract fidelity, comparison quality, grounding, loop termination, latency, token/tool use and compute cost across
  repeated real-model runs.

Authority, build-contract fidelity, workspace isolation, admission independence, exact-content identity, no trust-tier
upgrade, no hidden performance use and no duplicate accepted mutation must pass every run. Model-quality thresholds and
operating limits are frozen in the qualification profile.

## Concurrency and handoff rules

Read-only catalogue investigation may run alongside Data work. Independently approved candidate branches may use
separate isolated workspaces concurrently when their budgets and canonical writes are disjoint. One candidate attempt
has one workspace writer; checks may fan out only when they operate on an immutable packaged snapshot or the workspace
service can prove non-conflicting access.

Packaging waits for all required checks. Admission waits for one exact immutable package. A repair attempt waits for
the preceding admission result and always receives new attempt and package identity. Completion order cannot discard a
slower failure or select an implementation by performance.

Every return rejoins the coordinator. Strategy Engineering does not delegate to Data, Experiment Design, or another
coding agent, and it does not mutate shared agenda state. When multiple comparison or candidate branches require
engineering synthesis, the coordinator delegates reconciliation back to a later Strategy Engineering invocation.
