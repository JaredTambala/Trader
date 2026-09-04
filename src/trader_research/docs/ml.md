# ML Research Capability

The ML context owns feature, model, prediction, deployment, and drift artifact contracts plus the registry that resolves
provider-neutral adapters. The credential-free `InferenceAdapterProfile` value is a core prediction contract under
`trader.predictions`, shared by research and concrete provider packages. Point-in-time availability, chronological
splits, identity pins, signatures, parity fixtures, and output semantics are required to keep model evidence
reproducible and prevent look-ahead leakage.

Actual MLflow model loading belongs to `trader_mlflow`; maintained feature providers, mappers, and strategies belong to
`trader_standard`; core prediction contracts belong to `trader.predictions`. Both the research registry and MLflow
adapter depend directly on that core profile, so `trader_mlflow` has no dependency on `trader_research`. The ML context
coordinates immutable research records without moving provider objects into canonical state.

The broader agentic ML lifecycle is parked in the current product roadmap. The implemented runtime inference boundary
does not imply that autonomous training, promotion, walk-forward retraining, or deployment is qualified.

## ML Lifecycle Architecture

MLflow is authoritative for ML training telemetry, logged model packages, registered-model versions, tags, and aliases.
Trader remains authoritative for the research session, feature/split specifications, evaluation, deployment validation,
and runtime prediction lineage. Trader never queries that tracking projection to decide whether canonical work passed.

Random train/test splitting must not be the default for time-series research. Split plans are chronological and preserve
point-in-time availability. A runtime must never change model behavior merely because an MLflow alias was reassigned;
the approved deployment pins the immutable model version and digest. The trading hot path must not call MCP.

### Implemented Runtime Slice

The implemented slice resolves an approved deployment into a provider-neutral predictor, validates a parity fixture,
records exact model/feature identities, and maps predictions through strategy-owned semantics. Training and promotion
remain separate future capabilities.

Prediction deployment creation and validation belong to this context. Binding a passed deployment and maintained
mapper into a canonical strategy specification belongs to Experiments, which owns that specification and its exact
dependency pins.

## Walk-Forward Validation And Optimisation

Chronological walk-forward validation is foundational model-fitting correctness, not an optional robustness flourish.
The complete multi-stage optimisation and retraining programme is deferred, but future design must preserve immutable
fold plans, training-only selection, stitched out-of-sample evidence, and independent audit.

## Verification ownership

Package-owned contracts live under `tests/trader_research/ml/`. The deployment-lifecycle suite uses in-memory
canonical artifacts and a deterministic provider-neutral adapter to verify stable identities, parity validation,
immutable upstream pins, environment safety, and fail-closed dependency handling. The projection suite separately
verifies schema-writer registration and typed deployment/validation rows; only its marked adapter case requires the
guarded local Postgres database. Strategy prediction bindings remain under `tests/trader_research/experiments/`
because Experiments owns the canonical strategy specification and its dependency revalidation.
