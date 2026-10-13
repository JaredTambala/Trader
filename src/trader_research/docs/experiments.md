# Experiments

The Experiments context owns the implementation catalogue, validation, immutable strategy/risk/backtest specifications,
canonical backtest execution, comparison, parameter optimisation, and optional tracking projection.

Execution consumes exact passed implementation and specification versions plus explicit dataset evidence. Runtime code
does not infer missing scientific choices. Backtest results preserve scope, assumptions, warnings, trades, performance,
and provenance. Comparisons reject or disclose incompatible scopes rather than silently ranking unlike runs.

Optimisation records every trial, search space, objective, engine identity, budget, failures, and selected candidate.
Selection evidence is not independent confirmation. Protected evaluation and walk-forward data remain sealed from
tuning, and material changes create a successor protocol.

## Review projection boundary

Evaluation, multiple-testing, and Adversarial/robustness artifacts remain owned by their producer contexts. The Console
consumes a typed `research_review_evidence` projection keyed by exact run identity; it receives artifact identity,
producer, digest, claim scope, protected-data roles, limitations, blockers, and status. Missing or incompatible
references are first-class review outcomes. Optimisation reports can explain search and selection, but their projection
always records `independent_confirmation: false`; a Console review cannot upgrade exploratory output into independent
confirmation. Multiple-testing output that is not persisted as a run-linked artifact remains unavailable.

`OptimizationEngine` is the provider-neutral suggestion boundary, `OptimizationTrialExecutor` runs one exact trial,
and `ExperimentTrackingSink` receives a non-authoritative projection. The built-in grid/random engines, optional Optuna
adapter, and MLflow sink all implement these inward-owned ports; experiment logic never queries the tracking sink to
decide canonical state.

Optuna qualification uses a dedicated non-`public` schema and writer role. Its sampler state is provider state, not the
canonical trial ledger; every suggestion and terminal trial remains recorded by Trader.

## From implementation to evidence

The Console authoring boundary consumes this evidence without taking ownership of admission. A draft carries the exact
implementation version ID, implementation kind, source hash, passed validation-report ID, strategy or risk
specification ID, and the reuse/adaptation/authorship decision. Console preflight compares the nested report IDs and
hashes, rejects blocked reports, and may call a deployment-supplied resolver to re-read the research artifact store.
The immutable Console definition stores the complete projection, so a later review can reconstruct which admitted
source and validation evidence were selected. Import paths and serialized callables never cross this boundary.

A falsifiable `HypothesisBrief` is the upstream intent boundary. It is persisted as an immutable, revisioned
`hypothesis_card` by the governance context before downstream Data and Strategy work begins. The brief carries the
question, mechanism, falsifier, intended universe/timeframe, typed data requirements, strategy intent, risk intent,
assumptions, expected evidence, and an explicit decision rule for each outcome. Consumers receive a digest-pinned
reference and must re-read the canonical brief; they must not copy or silently replace its scope, implementation
intent, or decision.

An experiment is reproducible because each stage names its inputs instead of filling in scientific choices implicitly:

1. Resolve one exact implementation version and passed validation report.
2. Create strategy, risk-stack, and backtest specifications with dataset, model, cost, period, and execution
   assumptions pinned.
3. Validate the specifications and persist their identities before execution.
4. Run the declared specification and persist the canonical run, trades, metrics, warnings, and provenance.
5. Compare only compatible scopes, or return explicit differences and unknowns.
6. Treat optimisation and tracking projections as evidence about the declared search, then send the run to independent
   Evaluation and Adversarial review.

For a qualified Data manifest, step 3 also seals `replay_data_identity`. Step 4 re-reads the exact scope before invoking
`BacktestRunner`; the run receipt records the qualified digest, observed digest, row counts, source semantics, and
validation time. Any bar-content, source-policy, partial-reload, or post-inspection mutation fails closed with a
machine-readable `replay_data_identity_*` error. The existing backtest scope fingerprint remains a comparison identity;
it does not replace this Data-owned qualification contract.

The context owns execution mechanics, not the scientific conclusion. A successful backtest proves that the declared
simulation completed; it does not prove live profitability or authorize paper trading.

## Approved experiment-to-job handoff

`submit_approved_experiment_job` is the deterministic boundary between an
operator-approved `ExperimentProtocol` and durable execution. Its inputs are
typed, digest-pinned `ArtifactReportRef` values for the canonical
`ExperimentProtocolProposal` and approved `ExperimentProtocol`; callers do not
send a copied protocol payload. The service re-reads both records, checks that
every approval decision matches the requested approver and proposed design, and
revalidates every implementation and Data reference before admission. It then
persists one source-free `experiment_job_request` containing the exact
proposal, protocol, implementation, and Data evidence references before
admitting one `ResearchJob` through the durable lifecycle service.

The handoff accepts only the workflow executor or Quant Research Supervisor
actor. Exact repeats return the same request and job; changed proposal,
approval, scope, code, environment, or actor identity fails closed. A repeat
with changed execution pins cannot create another attempt for the same proposal;
an already-terminal job is returned for reconciliation or review. This boundary
grants no worker, broker, evaluation, robustness, or paper-trading authority.
The worker slice consumes the request and re-reads the pinned Data manifest to
validate replay identity before invoking the canonical backtest.

The integrated UJ-08 qualification adds the Console-side
`ApprovedExperimentBacktestExecutor` at the worker boundary. It resolves the
source-free request, rereads proposal and approval records, revalidates every
Data and implementation reference, and checks the returned `backtest_run`
receipt before retaining success. Evaluation and Robustness records remain
independent producer-owned artifacts; their absence, negative result, or
identity mismatch remains visible to `EvidenceJoinResult`. The public Postgres
campaign reconstructs its full chain from canonical storage in a fresh process.
Single-backtest independent review producers are currently unavailable: separate
branch preflights retain typed blockers in the canonical terminal outcome rather
than writing simulated review artifacts. Model-backed handoff and scientific
review remain separate feature limits.

The worker producer uses the same canonical specification and execution services
as other research backtests. It records real strategy/risk/backtest artifacts,
seals the approved request reference and digest in specification runtime limits,
and calls `run_backtest_specification` with an admitted `run_id` and
`progress_callback`. The service always checks retained-run provenance, including
explicit run identities, before returning an idempotent receipt. Errors after
runner execution begins are classified as ambiguous; failures to retain a run
receipt likewise require worker reconciliation. Unsupported or conflicting
approved cost semantics fail during compilation before the runner starts.

## Optimisation and projection boundaries

`OptimizationEngine` suggests candidates, `OptimizationTrialExecutor` runs one exact candidate, and the canonical trial
ledger records every suggestion, result, failure, and selected candidate. Optuna and MLflow are optional provider
adapters. Tracking projections help operators inspect runs but are non-authoritative and are never queried to decide
whether canonical work passed.

## Verification ownership

Package-owned contracts live under `tests/trader_research/experiments/`. Implementation catalogue and maintained
template suites verify bounded discovery, trust tiers, exact source disclosure, comparison evidence, family filters,
and real maintained entrypoints. Optimisation is separated into canonical workflow/selection, source and dependency
isolation, and Optuna provider-profile contracts. The provider-profile suite validates configuration without opening a
database connection; the separately marked Postgres projection suite verifies typed plan, run, trial, and authority
rows against the guarded local database. Prediction-binding contracts remain here because they protect canonical
strategy specifications, deployment and mapper pins, and dependency revalidation; ML deployment records are
collaborators owned by the ML context. These tests do not treat tracking projections or optimisation selection as
independent evaluation.

## Deterministic hypothesis-to-candidate handoff

`create_strategy_candidate_handoff` is the research-owned handoff from a resolved
`HypothesisBriefHandoff` to one reviewable strategy/risk candidate. It re-reads
the canonical brief, requires a catalogue comparison whose decision authority is
Strategy Engineering, and requires independent passed validation reports for the
strategy implementation, strategy specification, and ordered risk stack. The
persisted `strategy_candidate_handoff` contains references and decisions only:
it carries no source code, execution authority, broker permission, or model
acceptance claim. `resolve_strategy_candidate_handoff` revalidates every edge and
fails closed when a report is missing, blocked, stale, or points to an
incompatible specification. This deterministic boundary is qualified by
`tests/cross_package/workflows/test_candidate_handoff.py`; the controlled
third-party-model and Console/browser variants remain separate work in TRD-288.
