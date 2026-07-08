# Research Agent Workflows

Research workflows are built as deterministic MCP tool chains first, then composed by LangGraph agents once the tool
surface is useful. All workflows stay outside live trading.

## Data Agent Workflow

```text
mcp_health
  -> mcp_get_config
  -> data_discover_symbols
  -> data_get_inventory
  -> data_summarize_quality
  -> data_ensure_loaded, only when policy permits
  -> data_summarize_quality
```

The Data Agent owns symbol discovery, dataset manifests, data-quality reports, and explicit load evidence. Downstream
strategy, backtest, and evaluation tools should consume Data Agent dataset/quality artifacts rather than loose symbols,
timeframes, or date windows.

## Method-To-Backtest Toolchain

```text
approved source evidence
  -> method card
  -> validated indicator or signal implementation
  -> method package manifest
  -> strategy candidate manifest and source
  -> strategy validation report
  -> Data Agent dataset manifest
  -> baseline backtest run bundle
  -> evaluation performance report
```

This is the current meaningful MCP toolchain. Strategy candidates are source-backed, but data scope is supplied by the
backtest through a Data Agent `dataset_manifest`.

## Backtest Result Review

```text
backtest_run_ref
  -> research_get_backtest_results
  -> research_compare_backtest_results, for explicit run refs
  -> evaluation_generate_performance_report
```

Comparison reports warn when runs are not like-for-like. Evaluation reports are descriptive and skeptical; missing or
incomplete data-quality evidence blocks the report status.

## Portfolio Risk Toolchain

```text
method packages
  -> multi-asset strategy candidate
  -> risk-manager candidate(s)
  -> validated strategy/risk stack
  -> risk-scoped portfolio backtest
  -> portfolio and risk evaluation report
```

The first risk-manager tools list generation targets and create backtest-only source-backed candidates. Risk-manager
validation, stack composition, risk-scoped portfolio backtests, exposure telemetry, and portfolio/risk Evaluation
reports are now deterministic MCP surfaces. VaR/CVaR values are pass-through evidence in this slice; Evaluation blocks
when a portfolio backtest omits required risk telemetry.

## Handoff And Blockers

- Each tool returns warnings for non-fatal caveats and blockers/errors for conditions that make downstream use unsafe.
- Agent handoffs preserve the original artifact owner and provenance.
- Supervisor workflows stop early when required specialist artifacts are missing, failed, blocked, or owned by the wrong
  agent.
- Research outputs may become human-reviewed promotion proposals, but they do not trigger live trading.
