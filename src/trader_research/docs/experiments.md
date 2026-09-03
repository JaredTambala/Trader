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
