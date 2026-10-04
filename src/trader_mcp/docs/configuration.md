# MCP Configuration

`load_local_environment` requires an environment file and lets process variables override file values. It accepts only
stdio transport. Required values identify the local environment, artifact root, and the baseline safety flags; optional
values configure providers and gated capabilities.

Configuration has two stages:

1. `load_local_environment` parses the dotenv file, applies process-variable overrides, normalizes booleans and paths,
   and rejects unsupported transport or malformed values.
2. `runtime.composition` turns that policy into lazy providers and registries. A valid environment file does not prove
   that Postgres, a provider, Docker, MLflow, or an embedding endpoint is reachable.

Keep the environment file outside tool arguments and never copy credentials into an envelope, trace, checkpoint, or
documentation example.

## Capability gates

The principal flags cover symbol-provider discovery, data loading, backtests, optimisation, external research writes,
Optuna writes, experiment-tracking writes, ML runtime, and the coding workspace. Broker mutation and raw SQL remain
disabled for research agents. Start from all mutation flags false and enable only the operation family being tested.

| Gate family | Enables | Additional requirement |
| --- | --- | --- |
| symbol discovery | provider catalogue reads | provider policy and network availability |
| data loading | bounded backfill mutation | approved scope, loading policy, and cost envelope |
| backtests | core-backed historical execution | Trader config and event-store access |
| optimisation | parameter trial execution | admitted engine and explicit trial budget |
| external research writes | tracking or external projections | the corresponding sink and write policy |
| ML runtime | model adapter loading/inference | adapter profile and model identity |
| coding workspace | isolated candidate writes/checks | dedicated roots, pinned revision, and image |

Gates control registration and composition; they do not grant an agent permission to choose arbitrary scope or bypass
service validation. A missing optional dependency should appear as an unavailable capability, not as a successful
in-memory result.

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

For a first local inspection, keep provider and mutation gates disabled and use the read-only `mcp_health`,
`mcp_get_config`, and catalogue discovery path. Add one gate at a time, then verify the registered tool set and its
side-effect metadata before an agent can call it.
