# Experiments

The Experiments context owns the implementation catalogue, validation, immutable strategy/risk/backtest specifications,
canonical backtest execution, comparison, parameter optimisation, and optional tracking projection.

Execution consumes exact passed implementation and specification versions plus explicit dataset evidence. Runtime code
does not infer missing scientific choices. Backtest results preserve scope, assumptions, warnings, trades, performance,
and provenance. Comparisons reject or disclose incompatible scopes rather than silently ranking unlike runs.

Optimisation records every trial, search space, objective, engine identity, budget, failures, and selected candidate.
Selection evidence is not independent confirmation. Protected evaluation and walk-forward data remain sealed from
tuning, and material changes create a successor protocol.

`OptimizationEngine` is the provider-neutral suggestion boundary, `OptimizationTrialExecutor` runs one exact trial,
and `ExperimentTrackingSink` receives a non-authoritative projection. The built-in grid/random engines, optional Optuna
adapter, and MLflow sink all implement these inward-owned ports; experiment logic never queries the tracking sink to
decide canonical state.

Optuna qualification uses a dedicated non-`public` schema and writer role. Its sampler state is provider state, not the
canonical trial ledger; every suggestion and terminal trial remains recorded by Trader.

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
