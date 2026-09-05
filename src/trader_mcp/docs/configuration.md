# MCP Configuration

`load_local_environment` requires an environment file and lets process variables override file values. It accepts only
stdio transport. Required values identify the local environment, artifact root, and the baseline safety flags; optional
values configure providers and gated capabilities.

## Capability gates

The principal flags cover symbol-provider discovery, data loading, backtests, optimisation, external research writes,
Optuna writes, experiment-tracking writes, ML runtime, and the coding workspace. Broker mutation and raw SQL remain
disabled for research agents. Start from all mutation flags false and enable only the operation family being tested.

## Coding workspace

Enabling coding requires a dedicated workspace root, a pinned read-only repository root and revision, and a
digest-pinned container image. Missing or inconsistent values fail composition; the server does not fall back to host
execution.

## Providers

Embedding provider/model/base URL and knowledge-store selection configure source ingestion and retrieval. Optuna and
MLflow settings configure optional optimisation/tracking/inference adapters. Credentials remain process-local and must
not appear in tool results, agent checkpoints, traces, or documentation examples.

The root [environment guide](../../../docs/environment.md) contains the repository-level variable inventory and local
service setup. Exact tool-to-flag mappings are in [Tools](tools.md).
