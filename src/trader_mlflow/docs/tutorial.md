# MLflow Prediction Tutorial

This tutorial explains the adapter without a tracking server. A tiny model and dataframe factory stand in for the
effectful loading boundary while the real predictor performs normalization.

## 1. Keep identity immutable

A predictor is tied to a registered model name/version, content and signature digests, source run, adapter profile, and
adapter version. The caller also supplies a content-hashed point-in-time `FeatureBatch`.

## 2. Predict through the provider-neutral contract

The complete executable example is in [the notebook](mlflow_prediction_tutorial.ipynb) and
`tests/trader_mlflow/inference/test_pyfunc_inference_adapter.py`. It builds a feature batch, runs a fake loaded pyfunc
model through `MLflowPyfuncPredictor`, and inspects normalized observations without importing the optional provider.

<!-- verified: integration:repository tests/trader_mlflow/inference/test_pyfunc_inference_adapter.py -->
```bash
uv run pytest tests/trader_mlflow/inference/test_pyfunc_inference_adapter.py -q
```

## 3. Use real MLflow only at composition

Install the `ml` optional dependency, create `MLflowLocalPyfuncAdapter(profile_name=..., tracking_uri=...)`, register it
with the research inference adapter registry, and resolve only an approved deployment manifest. The adapter and registry
share the core `trader.predictions.InferenceAdapterProfile` contract without depending on one another. The adapter loads
the pinned URI locally and runs its parity fixture before the runtime uses it. That composition is verified separately
because it crosses the `trader_mlflow` and `trader_research` boundary.

<!-- verified: integration:mlflow tests/cross_package/workflows/test_mlflow_inference_adapter.py -->
```bash
uv run pytest tests/cross_package/workflows/test_mlflow_inference_adapter.py -q
```

## 4. Handle failure

Missing optional packages make the adapter profile unavailable. Missing outputs, incompatible shapes, row-count
mismatch, model exceptions, timeouts, and parity mismatch block or return explicit failed batches. The strategy must not
reuse stale predictions or silently substitute another model.

## 5. Inspect, compose, and extend

Inspect batch status, errors, model identity, feature hash, timestamps, requested output coverage, and normalized
observations before mapping predictions into signals. New loaders belong behind the same provider-neutral predictor and
parity boundary; training governance and strategy mapping remain in their owning packages. Continue with the
[usage reference](usage.md) and [architecture](architecture.md).
