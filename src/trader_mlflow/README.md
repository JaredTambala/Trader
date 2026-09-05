# `trader_mlflow`

`trader_mlflow` is the optional MLflow inference adapter for Trader. It resolves an immutable MLflow model version into
a provider-neutral `trader.predictions.Predictor`, performs parity validation, normalizes supported pyfunc output shapes,
and reports bounded inference failures.

It does not own feature engineering, strategy mapping, model-training governance, deployment approval, experiment
tracking authority, or agent decisions. MLflow and pandas are optional imports loaded only at the adapter boundary.

Start with the [tutorial](docs/tutorial.md), then use [usage](docs/usage.md) and [architecture](docs/architecture.md).
The [prediction notebook](docs/mlflow_prediction_tutorial.ipynb) exercises normalization with a fake already-loaded
model and therefore needs no MLflow server.

Package-owned tests use only core prediction contracts. Verification that composes an approved research deployment
with a real local MLflow model is a cross-package workflow, because the asserted seam—not either package in
isolation—is its subject.
