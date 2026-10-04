# Development harness

Trader has several product tracks that can move independently: MCP capabilities, agent identities and third-party
model qualification, the Console, data sources, backtest realism, and strategy research loops. This harness keeps those
tracks connected to their human purpose while giving each one an isolated local worktree and declared validation.

The harness owns local execution state only. Notion remains authoritative for work intake, assignment, priority,
dependencies, status, and delivery progress. The repository owns this manifest, the evidence contract, executable checks,
and the implementation documentation.

## Capabilities, work items, and merge strategy

The six entries in the initial manifest are capability lanes for product intent and attention. A worktree belongs to a
unique work-item ID, not to a capability. Multiple work items can therefore share one `capability_id` while keeping
separate branches, checks, evidence, and disposable test databases. The capability is the roll-up used to explain why
the work matters; the work item is the unit that can be started, tested, reviewed, and merged.

Each work item declares a merge strategy:

- `independent` can merge directly into its target when its evidence is complete.
- `contract-first` lands a shared contract before dependent work proceeds.
- `stacked` records an ordered branch relationship; the dependent item is rebased and rechecked after its predecessor.
- `integration` is used when overlapping changes need one explicit integration branch before landing.

The harness records this strategy and order in reports. It does not merge branches automatically, because conflict
resolution and the decision to preserve or redirect a product change remain human decisions.

## Boundary contract discipline

Create a shared contract only when a capability crosses a process, trust, package-ownership, persistence, recovery, or
external API boundary, or when a concrete failure mode requires an explicit schema. The work item and branch evidence
must name the boundary, the canonical semantic owner, the adapter consumers, the identity or version and provenance
fields, and the contract tests that prove the failure behavior.

The owning domain package defines the meaning. MCP, Console, persistence, and other adapters validate and translate
that meaning into their wire or storage representations; they do not create competing domain truth. When several
items in one capability need the same semantic contract, land the contract-owning change first and rebase or merge
the consumers against it. If the work does not cross a boundary, keep the type local and do not create a DTO merely to
make layers look symmetrical.

Hard cutover is the default for an internal process, contract, schema, import surface, or persisted state that the new
work replaces. The work item must update active callers, tests, fixtures, and documentation together and remove the
obsolete path. A compatibility reader, alias, shim, fallback, dual write, or silent translation is allowed only when
an explicitly approved work item names a currently supported consumer or bounded migration, an owner, a removal
condition, and verification that prevents old and new semantics from being confused.

## Product intent baseline

The canonical intent record is [Trader Product Intent](product_intent.md). It preserves the human's natural-language
vision, then records the collaboratively reviewed user journeys and functional requirements derived from it. The
manifest points to this document and every work item names at least one product feature/user journey and requirement;
those references provide traceability and are not the work-item identity, so a low-level branch can be reviewed against
the product behavior it is meant to enable. The decision and scenario map in the manifest is
supporting review scaffolding; it does not replace the human vision or the intent document.

Inspect and record that review locally:

<!-- verified: integration:repository tests/cross_package/documentation/test_development_harness.py -->
```bash
uv run python tools/development_harness.py intent
uv run python tools/development_harness.py review-intent accept --notes "The journeys and requirements match the current product direction."
```

Use `review-intent revisit` when the interpretation is wrong or incomplete. A track cannot become `ready-to-merge`
until its checks pass, its own human review says `merge`, and the product-intent artifact has been explicitly accepted.
Changing the intent document invalidates the recorded acceptance and requires another human review.

The manifest also names the canonical [Trader Product State](product_state.md) document and checks its review date,
required evidence markers, and forbidden contradictory markers. Inspect it with:

<!-- verified: integration:repository tests/cross_package/documentation/test_development_harness.py -->
```bash
uv run python tools/development_harness.py current-state
```

The command exits successfully only when the source is present, recently reviewed, and consistent with its declared
markers. A stale, incomplete, future-dated, or contradictory product-state document blocks merge readiness and makes
the report show the reason.

## Track contract

Every work item records seven things:

- **User outcome** — what the human should be able to do or decide.
- **Instrumental purpose** — why the implementation matters to the product path.
- **Product alignment** — which human product decisions this track serves.
- **Intent traceability** — which user journeys and functional requirements this work advances.
- **Acceptance scenarios** — the situations, desired outcomes, and evidence that make product alignment reviewable.
- **Scope** — the bounded surface for this branch.
- **Evidence** — what must be inspectable before a merge decision.
- **Human review** — the question and decision point that keep the track aligned.

The manifest is [plans/development_tracks.yaml](../plans/development_tracks.yaml). It is deliberately declarative so the
same track definition can drive a worktree, focused checks, and a progress report.

## Local commands

From the repository root:

<!-- verified: integration:repository tests/cross_package/documentation/test_development_harness.py -->
```bash
uv run python tools/development_harness.py validate
uv run python tools/development_harness.py current-state
uv run python tools/development_harness.py status
uv run python tools/development_harness.py report
uv run python tools/development_harness.py start mcp-capabilities
uv run python tools/development_harness.py prepare mcp-capabilities
uv run python tools/development_harness.py check mcp-capabilities --profile focused
uv run python tools/development_harness.py review mcp-capabilities continue --notes "The tool contract is clear enough to continue."
```

`start` creates `.worktrees/<track-id>` from the configured base branch, gives it the declared branch name, and copies
only the track's declared tracked templates into missing worktree files (for example, `env.template` to the ignored
`local.env`). It refuses to overwrite existing local files or reuse an existing path. `prepare` repeats that safe
non-overwriting preparation for an existing worktree. `provision-db` creates a disposable PostgreSQL database whose name is
derived from the track ID, such as `trader_mcp_capabilities_test`; it requires the explicit `PG_ADMIN_*` settings and
never resets a database unless `--reset` is supplied. This database boundary keeps SQL that explicitly references the
`public` schema isolated while worktrees run concurrently. `test-env` prints the derived environment identity.

Checks marked `requires_database: true` receive the isolated `PG_TEST_DB` automatically after provisioning. They fail
before execution when the database has not been provisioned. `check` runs only the selected profile in that worktree
and records the commit-bound results under `.trader-development/state/`. `review` records your local decision as
`continue`, `merge`, `pause`, or `redirect`; it does not merge or publish anything. `report` explains each track's
product purpose, local phase, product decisions, acceptance scenarios, evidence obligations, and human review question.

The local state directories are ignored by Git. They are operational breadcrumbs, not a second planning database. A
track is ready to merge only after its checks pass against the current worktree commit and the human review decision is
`merge`, the product-intent baseline is accepted, and current-state evidence is fresh and consistent; the harness does
not perform the merge automatically.

## Development loop

1. Choose a user story and the human decision it serves, then confirm its Notion work item and dependencies.
2. Audit the repository and current product documentation against the story's acceptance criteria before proposing new implementation.
3. Turn each unmet criterion into an atomic Notion work item, with an explicit owner, dependency, merge strategy, and verification path.
4. For every new type or schema, record the boundary or failure mode it protects and select one canonical semantic owner.
5. Decide whether a replaced path is a hard cutover; record any explicitly approved compatibility exception before implementation.
6. Start a worktree for one item and keep the branch limited to the declared scope.
7. If the item uses PostgreSQL, provision its disposable database from the operator-approved admin identity.
8. Implement the smallest user-visible slice, explaining the low-level change in the item's evidence.
9. Run the focused checks, then add broader qualification only when the slice crosses a shared contract or external boundary.
10. Read `report`, inspect the evidence, and record a human decision before merging or redirecting the track.
11. Reconcile the evidence and status back to Notion and the owning repository documentation.

This loop allows several tracks to progress concurrently while preserving serialized decisions at shared contracts,
human approvals, and merge points.

For example, two PostgreSQL tracks can run concurrently with independent databases:

<!-- verified: integration:repository tests/cross_package/documentation/test_development_harness.py -->
```bash
export PG_TEST_DB=trader_orchestration_test
uv run python tools/development_harness.py provision-db mcp-capabilities
uv run python tools/development_harness.py provision-db backtest-reality
uv run python tools/development_harness.py check mcp-capabilities --profile postgres
uv run python tools/development_harness.py check backtest-reality --profile postgres
```
