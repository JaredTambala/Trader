# Strategy Engineering Agent Design

Status: architecture review in progress; no implementation is authorized by this document.

Last reviewed: 2026-08-25.

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

## Provisional mission

Produce the smallest admissible, inspectable strategy or risk candidate that faithfully implements an accepted build
contract. Use the isolated Coding Workspace MCP to inspect relevant Trader interfaces and maintained patterns, decide
whether to reuse, adapt, or author code, run bounded development checks, package the exact candidate, and respond to
independent admission evidence without expanding the research question.

The mission ends at an admitted candidate reference and an explicit account of limitations, deviations, tests, and
unresolved blockers. It does not design the research method, approve a quantitative adaptation, define the experiment,
judge performance, or deploy the candidate.

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

Passing admission completes the mission; the agent cannot continue polishing or optimizing admitted code. Budget
exhaustion returns complete attempt lineage, the strongest available candidate and admission evidence, unresolved
blockers, and a recommended next action to the coordinator. Initial numeric limits are selected from measured framework-
spike recovery scenarios and then frozen in the active policy profile.

## Remaining architecture record

The following sections remain pending structured review:

- exact build-contract schema and validation details;
- exclusive decisions and final hard boundaries;
- complete readiness conditions;
- context and trust boundaries, including malicious repository or dependency content;
- model program and structured-output requirements;
- final Coding Workspace MCP/resource schemas;
- durable candidate lineage and recovery;
- evidence-return contract;
- termination and escalation;
- evaluation scenarios and promotion evidence; and
- concurrency, workspace isolation, and handoff rules.
