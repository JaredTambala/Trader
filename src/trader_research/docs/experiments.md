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

The context owns execution mechanics, not the scientific conclusion. A successful backtest proves that the declared
simulation completed; it does not prove live profitability or authorize paper trading.

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
