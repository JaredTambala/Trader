# MLflow Adapter Architecture

Core prediction contracts, including `InferenceAdapterProfile`, live in `trader.predictions`. Research deployment
manifests and adapter registries live in `trader_research.ml`. Maintained feature providers, mappers, and the
prediction-driven strategy live in `trader_standard`. This package depends only on the core contract and has one job:
bridge a pinned MLflow pyfunc model to the core `Predictor` protocol.

```text
deployment manifest -> MLflowLocalPyfuncAdapter
  -> verify optional dependencies/profile
  -> load exact model URI
  -> MLflowPyfuncPredictor
     -> FeatureBatch -> dataframe -> pyfunc.predict
     -> normalized PredictionObservation values -> PredictionBatch
```

The core-owned adapter profile exposes provider and adapter versions plus a credential-free configuration digest. Deployment
validation executes a fixed parity feature batch and compares the exact normalized output digest. A mismatch blocks the
deployment.

`MLflowPyfuncPredictor` accepts an already-loaded model and dataframe factory, which keeps output normalization directly
testable without importing MLflow. It supports record, column, vector, and scalar shapes subject to the declared output
contract. Row-count, width, requested-output, timeout, and model failures become an explicit failed `PredictionBatch`.

## Verification ownership

Tests under `tests/trader_mlflow/inference/` protect only the adapter's use of core prediction contracts and therefore
must not import `trader_research`. A parity test that creates a research deployment manifest and validates it through a
real local MLflow model belongs under `tests/cross_package/workflows/`: it proves the composition seam while preserving
the package's one-way dependency on `trader`.
