# MLflow Adapter Usage Reference

## Public classes

- `MLflowLocalPyfuncAdapter(profile_name, tracking_uri)`: reports availability, validates a deployment, and builds a
  predictor from an immutable manifest.
- `MLflowPyfuncPredictor(model, dataframe_factory, identity, output_contract)`: adapts one already-loaded pyfunc-like
  object to the core predictor protocol.
- `InferenceAdapterProfile` is the return type of `profile()` and is imported from `trader.predictions`; this package
  does not obtain it through the research package.

## Optional dependency

<!-- verified: integration:mlflow tests/cross_package/workflows/test_mlflow_inference_adapter.py -->
```bash
uv sync --extra ml
```

Importing `trader_mlflow` does not import MLflow or pandas. `profile()` reports them unavailable when absent;
`build_predictor()` raises rather than substituting another backend.

## Output contract

Each output declares a name, semantics, horizon, and optional units. `PredictionRequest.requested_outputs` must be a
supported subset. Normalized observations carry model identity, feature-batch hash, decision timestamp, symbol,
semantics, value, horizon, and units through the enclosing `PredictionBatch`.

## Operational rule

Load only an approved immutable model/deployment version and validate its parity fixture in the target environment.
Tracking URI configuration and credentials stay in the adapter process; they are not model context or canonical
prediction values.
