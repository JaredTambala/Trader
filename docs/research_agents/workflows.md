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
  -> methodology candidate discovery
  -> methodology evidence assembly
  -> methodology field extraction
  -> methodology candidate validation
  -> rich method-card draft
  -> approved method card
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

For statistical-arbitrage evidence, an approved rich method card can also drive the maintained
`pairs_mean_reversion` strategy template directly. The resulting strategy candidate records rich method-card provenance
and remains data-free; symbols, timeframe, and date windows still come from Data Agent scope.

The 33N MCP regression proves the representative pairs/cointegration route end to end: generated book-style source
registration, full-document ingestion, candidate discovery, field extraction, validation, rich-card approval,
rich-card-driven strategy generation, risk stack validation, two-leg portfolio backtest execution, and Evaluation.

## Rich Methodology Operator Workflow

Use this workflow when the goal is to turn an ingested source into a richer method description that can later drive
bounded strategy or risk candidate generation.

```text
source registration
  -> full-document ingestion
  -> retrieval or source-scoped candidate discovery
  -> family-role evidence assembly
  -> methodology field extraction
  -> methodology candidate validation
  -> rich method-card draft
  -> explicit publish approval
  -> method package, strategy candidate, or risk-manager candidate
  -> validation
  -> backtest or portfolio backtest
  -> Evaluation report
```

Registration and ingestion are deliberately separate. Registration records the source reference, type, file hash, and
operator metadata. Ingestion reads the entire document, creates chunks across the full source, indexes those chunks, and
makes them citeable. If retrieval cannot find a topic after registration, check ingestion status before assuming the
knowledge base lacks the method.

Candidate discovery is not approval. Discovery groups candidate spans from retrieved or source-scanned chunks and writes
methodology candidate refs. Evidence assembly then applies family-level role profiles, not known-target profiles, to
find definition, input, formula, parameter, signal, limitation, validation, and other role evidence where applicable.
Extraction fills only supported nullable fields from candidate chunks or assembled role evidence, and every populated
field must carry source/chunk/locator evidence. Validation blocks candidates with invalid locators, unsupported field
names, missing family minimums, packet role mismatches, insufficient high-risk evidence, excessive quotation, or
textbook/primary-source claims backed only by internal notes.

Draft cards are still review artifacts. A rich method-card draft requires packet-backed implementation readiness, can be
searched only when draft visibility is enabled, and cannot satisfy strategy/risk generation until it is published.
Publishing preserves the full rich payload and exposes the shallow method-card projection so older citation, contract,
implementation, and packaging workflows continue to work.

Approved rich cards can drive only maintained bounded templates. The pairs mean-reversion template requires an approved
statistical-arbitrage card with strategy-template readiness plus evidence for spread or legs, relationship testing or
hedge-ratio logic, entry logic, exit logic, and price/input requirements. Risk templates can consume approved risk-model
or portfolio-construction cards with risk-manager readiness, but numeric limits must be explicit structured values;
prose does not become a VaR, CVaR, concentration, or drawdown limit.

Operator examples:

- Pairs trading or cointegration: ingest a textbook or paper section covering pairs, spreads, hedge ratios,
  cointegration or stationarity tests, entry thresholds, and exits. Discover statistical-arbitrage candidates by source
  ID or query, validate the extracted fields, publish a rich card, and use it with the pairs mean-reversion template.
- Options straddle: ingest a source that describes the option instrument, call/put legs, payoff, strike selection,
  expiry selection, volatility assumption, and risk. Validate an options/derivatives rich card first; strategy
  generation remains blocked until a maintained options template exists.
- RSI or another technical indicator: ingest a source with the indicator formula, input series, lookback period,
  threshold semantics, warmup behavior, and failure modes. Use the approved rich card as method evidence for indicator
  implementation or packaging; strategy generation still needs a maintained template or validated signal package.
- Commodity sentiment indicator: ingest a source that describes the text/news source, raw sentiment signal, entity or
  commodity mapping, aggregation window, scoring model, lag assumptions, and noise/bias controls. Use the rich card to
  validate methodology evidence before implementation or signal diagnostics; do not put commodity symbols or data
  windows in the method card.

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
