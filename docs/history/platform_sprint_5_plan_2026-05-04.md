# Sprint 5 Plan: AI-Toolable Signal Discovery

## Summary

Sprint 5 turns the research platform into a first-class tool surface for AI systems, automation clients, and scripts.
Codex should be an excellent first customer, but the contracts must be AI-system agnostic.

The target workflow is:

1. A human quant asks a tool-using AI to pull data for specific symbols and research strategy families.
2. The AI maps that request into bounded, explicit tool calls.
3. The platform plans/backfills recent market data, runs data quality checks, expands a controlled research suite,
   executes backtests, compares results, ranks candidates, and proposes next experiments.
4. If a candidate is strong enough, the platform prepares a dry-run paper-promotion packet.
5. No discovery workflow starts or mutates live paper trading. Human/operator action remains required for broker-side
   changes.

Sprint 5 ships the full `S5.1` through `S5.10` backlog from the sprint task breakdown.

## Locked Decisions

- Primary user-facing entrypoint: `run_research_discovery.py`.
- Recommendation entrypoint: `run_research_recommendations.py`.
- Promotion-packet entrypoint: `run_prepare_paper_promotion.py`.
- Tool wrappers live under `src/trader/tools/` and remain thin over existing package APIs.
- Discovery is research-only. It may read Sprint 4 operator status JSON, but it must not start trading.
- Paper promotion emits a proposed config and validation report only.
- Strategy execution still uses explicit Python strategy objects and maintained `trader_standard` paths; Sprint 5 does
  not add a general arbitrary-code loader.
- Tool outputs use stable JSON envelopes suitable for AI systems and scripts.

## Key Deliverables

### 1. Tool Contracts And JSON Envelopes

Add `docs/research_agents/tool_contracts.md` and shared tool response helpers.

Standard JSON envelope:

```json
{
  "ok": true,
  "command": "research_discovery",
  "side_effect": "local_mutating",
  "schema_version": "1",
  "generated_at": "2026-05-04T00:00:00Z",
  "data": {},
  "artifacts": {},
  "warnings": [],
  "errors": []
}
```

Side-effect classes:

- `read_only`
- `local_mutating`
- `broker_read`
- `broker_mutating`

Discovery and recommendation commands must be `local_mutating` at most. Broker-mutating commands require explicit
operator-only command names and must not be reachable through discovery orchestration.

### 2. Discovery Request Contract

Add a typed discovery request model in `src/trader/tools/discovery.py`.

Required concepts:

- symbols
- asset class
- timeframe
- data window (`since`, or explicit `start`/`end`)
- strategy families
- parameter budget / max runs
- assumptions
- risk profile
- output directory
- dry-run flag
- optional Sprint 4 operator-state context files
- optional prior result/strategy artifact files

Example CLI:

```bash
uv run python run_research_discovery.py configs/reproducible_backtest.yaml \
  --symbols AAPL,MSFT,NVDA \
  --asset-class stocks \
  --timeframe 1Min \
  --since 30d \
  --strategies trend_following,mean_reversion \
  --max-runs 25 \
  --cost-profile conservative \
  --json
```

### 3. Recent Data Acquisition

Extend recent-data tooling so AI/tool clients can plan and execute bounded data pulls without editing YAML.

Tasks:

- Add `--json` and `--dry-run`/plan mode to `run_market_data_backfill.py`.
- Add CLI overrides for symbols, asset class, timeframe, and window where missing.
- Return rows requested/written/skipped, source, dataset ID, and artifact paths.
- Chain `run_data_quality.py --output-json` into discovery outputs.
- Ensure repeated data pulls remain idempotent through bar uniqueness.

### 4. Research Suite Execution

Add research suite support on top of the existing experiment runner.

Tasks:

- Define `research.suite` config for strategy families, parameter grids, assumptions, symbols, timeframe, and risk.
- Support discovery-request overrides without rewriting checked-in configs.
- Keep suite expansion deterministic and bounded.
- Persist suite ID, suite hash, member ID, parameters, and source dataset/report IDs in experiment provenance.
- Support follow-up suite generation from previous recommendation/result artifacts.

### 5. Recommendation Engine

Add `src/trader/tools/recommendations.py` and `run_research_recommendations.py`.

Recommendation inputs:

- experiment runs
- comparison JSON
- data-quality report
- assumptions
- prior result artifacts
- Sprint 4 operator JSON: status, health, positions, open orders, halt state

Scorecard fields:

- total return
- Sharpe
- max drawdown
- turnover
- fees
- slippage
- alpha
- beta
- trade count
- warning count
- data quality gap count
- assumption compatibility
- promotion readiness

Hard rejection rules:

- failed run
- missing or stale data-quality report
- insufficient sample size
- excessive drawdown
- excessive turnover
- incompatible assumptions
- too many warnings
- operator state suggests paper review is unsafe, e.g. halted runtime, stale data, stale open orders

Outputs must include accepted candidates, rejected candidates, ranking reasons, artifact paths, and suggested next
experiments.

### 6. Strategy And Result Artifacts

Extend strategy artifact metadata so AI/tool clients can compare prior outputs without importing arbitrary code.

Artifact metadata should include:

- strategy ID/name/version
- source path/package
- parameters
- risk profile
- data assumptions
- suite identity
- recommendation score
- source experiment/run IDs
- output file paths
- source revision and dirty flag
- package/dependency versions
- schema version

Supported artifact inputs:

- `result.json`
- `metrics.json`
- `provenance.json`
- `equity_curve.csv`
- `benchmark_curve.csv`
- `positions.csv`
- `trades.csv`
- strategy artifact metadata JSON
- Sprint 4 operator JSON files

### 7. Promotion Packet

Add `run_prepare_paper_promotion.py`.

The command packages one recommended candidate into:

- proposed paper config
- strategy artifact metadata
- linked recommendation JSON
- linked source experiment/run IDs
- data-quality summary
- cost/assumption summary
- risk profile
- dry-run validation report

Validation checks:

- config references the same strategy metadata and parameters
- broker mode is paper-only
- symbols and asset class match the source research context
- halt state is visible
- stale market data/open orders are surfaced
- no trading process is started

### 8. AI Tool Workflow Docs

Add:

- `docs/research_agents/ai_tool_workflows.md`
- `docs/research_agents/tool_contracts.md`

Document roles:

- data auditor
- strategy researcher
- recommendation reviewer
- risk reviewer
- operator assistant

Document handoff artifacts:

- discovery request
- data-quality report
- suite config/hash
- experiment ID
- comparison JSON
- recommendation JSON
- Sprint 4 operator JSON
- strategy/result artifacts
- promotion packet
- paper dry-run validation

## Implementation Order

1. Tool contract docs and JSON envelope helpers.
2. Discovery request dataclasses and validation.
3. Recent data planning/backfill JSON output.
4. Data-quality chaining into discovery outputs.
5. Research suite expansion and provenance.
6. Recommendation scorecard and rejection rules.
7. Artifact loaders and schema validation.
8. Discovery orchestration CLI.
9. Promotion packet CLI and dry-run validation.
10. AI/tool workflow docs and end-to-end smoke test.

## Test Plan

Unit tests:

- discovery request parsing and validation
- command side-effect classification
- JSON envelope stability
- recent-data plan output
- research suite expansion order and guardrails
- suite hash/member ID stability
- recommendation ranking and hard rejection rules
- follow-up experiment suggestions from prior artifacts
- operator JSON context loading
- strategy/result artifact validation
- promotion packet generation and dry-run validation

CLI smoke tests:

- `run_market_data_backfill.py ... --dry-run --json`
- `run_data_quality.py ... --output-json`
- `run_research_discovery.py ... --json`
- `run_research_recommendations.py ... --json`
- `run_prepare_paper_promotion.py ... --dry-run --json`

Integration tests:

- discovery workflow against checked-in sample data
- experiment persistence with suite metadata
- recommendation output with one accepted and one rejected candidate
- promotion packet links back to the source run and recommendation
- Sprint 4 operator JSON can be used as read-only recommendation context

Acceptance suite:

```bash
uv run pytest
uv run pytest -m postgres
uv run ruff check src tests examples run_*.py external_strategy_demo.py
uv run mypy
```

Manual acceptance workflow:

```bash
docker compose -f docker-compose.postgres.yml up -d
uv run python examples/load_sample_market_data.py
uv run python run_operator.py configs/example.yaml status --json > artifacts/operator_status.json
uv run python run_research_discovery.py configs/reproducible_backtest.yaml \
  --symbols DEMO \
  --asset-class stocks \
  --timeframe 1Min \
  --since 1d \
  --strategies trend_following,mean_reversion \
  --operator-context artifacts/operator_status.json \
  --json
uv run python run_research_recommendations.py configs/reproducible_backtest.yaml --experiment demo_discovery --json
uv run python run_prepare_paper_promotion.py configs/reproducible_backtest.yaml --recommendation-id <id> --dry-run --json
```

## Acceptance Criteria

Sprint 5 is done when:

- A high-level discovery request can be represented as a validated structured payload.
- AI/tool clients can pull or plan recent data for requested symbols/timeframes without editing YAML.
- Data quality, experiment, comparison, recommendation, and promotion artifacts are linked by IDs.
- Research suites run deterministically and remain bounded by explicit guardrails.
- Recommendations include accepted and rejected candidates with concrete reasons.
- Recommendations can consume Sprint 4 operator JSON and prior strategy/result artifacts as read-only context.
- A follow-up experiment suggestion can be generated from previous outputs.
- Promotion packets are traceable to source research and do not start live paper trading.
- Tool contracts and AI workflow docs describe the complete path without requiring source inspection.
- The full quality gate remains green.

## Out Of Scope

- No autonomous live or paper trading.
- No general arbitrary Python strategy loader.
- No new strategy families unless needed as tiny examples.
- No distributed job runner.
- No UI changes.
- No production live trading.

## Assumptions

- Sprint 1 through Sprint 4 are accepted baseline.
- Postgres remains the runtime source of truth.
- Alpaca paper remains the only live broker target.
- DuckDB remains test/support-only.
- Discovery workflows may read operator state, but human/operator commands remain the boundary for broker mutation.
