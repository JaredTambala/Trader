# AI/Tool Contract Reference

Sprint 5 exposes research-only commands as stable JSON/CLI/Python contracts. Codex is a first-class customer, but the
contracts are generic: any AI system, script, scheduler, or notebook can call the commands and parse the same envelope.

## Envelope

Every Sprint 5 tool command that supports `--json` emits:

```json
{
  "ok": true,
  "command": "research_discovery",
  "side_effect": "local_mutating",
  "schema_version": "1",
  "generated_at": "2026-05-04T12:00:00+00:00",
  "data": {},
  "artifacts": {},
  "warnings": [],
  "errors": []
}
```

Fields:

- `ok`: command success.
- `command`: stable command identifier.
- `side_effect`: declared side-effect class.
- `schema_version`: envelope schema version.
- `generated_at`: UTC timestamp.
- `data`: machine-readable command result.
- `artifacts`: paths to generated or consumed files.
- `warnings`: non-fatal issues.
- `errors`: structured fatal errors when `ok=false`.

## Side Effects

| Class | Meaning | Sprint 5 examples |
| --- | --- | --- |
| `read_only` | Reads config, event store, or local artifacts only. | discovery `plan`, backfill `--dry-run`, data quality, recommendations. |
| `local_mutating` | Writes local files or event-store research rows; does not submit broker orders. | discovery execution, promotion packet generation. |
| `broker_read` | Reads broker state. | Sprint 4 operator `reconcile` and recovery tools, outside discovery orchestration. |
| `broker_mutating` | Mutates broker state. | Not exposed by Sprint 5 discovery tools. |

Discovery orchestration never starts `TraderService`, submits Alpaca orders, clears halt, or reconciles broker state.
Broker mutation remains operator-owned.

## Commands

Backfill planning or execution:

```bash
uv run python run_market_data_backfill.py CONFIG --dry-run --json \
  --symbols AAPL,MSFT --asset-class stocks --timeframe 1Min --since 30d
```

Data quality:

```bash
uv run python run_data_quality.py CONFIG --output-json artifacts/dq/report.json --json
```

Discovery:

```bash
uv run python run_research_discovery.py CONFIG \
  --symbols AAPL,MSFT \
  --asset-class stocks \
  --timeframe 1Min \
  --since 30d \
  --strategies trend_following,mean_reversion \
  --max-runs 25 \
  --cost-profile conservative \
  --risk-profile default \
  --data-mode existing \
  --operator-context artifacts/operator_status.json \
  --json
```

Recommendations:

```bash
uv run python run_research_recommendations.py CONFIG --experiment demo_discovery --json
```

Promotion packet:

```bash
uv run python run_prepare_paper_promotion.py CONFIG \
  --recommendation-json artifacts/recommendations/demo_discovery.json \
  --recommendation-id rec_... \
  --operator-context artifacts/operator_status.json \
  --dry-run \
  --json
```

## Artifact IDs

Discovery creates stable local IDs and artifacts:

- `dataset_id`: hash of symbols, asset class, timeframe, window, and source.
- `suite_id`: hash of the sanitized suite request.
- `suite_member_id`: hash of suite ID, strategy family, and parameters.
- `experiment_id`: `exp_<normalized_experiment_name>`.
- `experiment_run_id`: hash of `experiment_id` and backtest `run_id`.
- `recommendation_id`: hash of recommendation input rows.

Research artifacts remain local JSON/CSV files linked to existing experiment/run IDs. Sprint 5 does not add database
migrations for recommendations or promotion packets.

## Operator Context

Sprint 4 operator JSON can be passed into recommendation and promotion commands:

```bash
uv run python run_operator.py configs/example.yaml status --json > artifacts/operator_status.json
```

The recommendation engine treats halted, unhealthy, stale-data, and stale-open-order contexts as promotion blockers.
This is read-only context: Sprint 5 tools do not clear halt state, reconcile broker orders, or start trading.
