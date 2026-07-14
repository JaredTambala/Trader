# Research Agent Workflows

Research workflows are built as deterministic MCP tool chains first, then composed by LangGraph agents once the tool
surface is useful. All workflows stay outside live trading.

## Current Delivery Focus

Knowledge-base creation and bounded methodology extraction are now maintained dependencies, not the active expansion
track. The Data Agent workflow also remains supported and maintained. New delivery work should concentrate on a direct
implementation-to-evidence chain:

```text
handwritten or AI-produced indicator / strategy / risk-manager source
  -> immutable implementation registration and provenance
  -> interface, import, source-hash, fixture, and safety validation
  -> reproducible backtest specification
  -> Data Agent dataset manifest and quality report
  -> baseline or risk-scoped portfolio backtest
  -> ML model-version refs when the strategy uses a model
  -> Evaluation report
  -> robustness and adversarial variants
```

The implementation intake must not depend on the platform generating the source. Handwritten code and AI-produced code
are both untrusted supplied artifacts; both must satisfy the same platform interfaces and deterministic validation
gates. Bespoke method-card or source refs may be attached as provenance when available, but knowledge extraction is not
a prerequisite for testing an explicitly supplied implementation.

This chain is not fully implemented. Current strategy candidates are maintained-template driven, ML versioning tools
are not registered, and robustness/adversarial tools are not registered. The tracker identifies implementation intake
and backtest specification work as the first dependencies before those evaluation layers.

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

## Planned MLflow Model Lifecycle

This workflow is the target for tasks 39A-39J; its `ml_*` tools are not registered yet.

```text
configured MLflow tracking and registry instance
  -> Data Agent dataset and quality refs
  -> point-in-time feature-set specification and validation
  -> training dataset, target, chronological folds, purge/embargo, leakage report
  -> registered and validated training pipeline
  -> bounded training specification
  -> gated fitting and MLflow experiment run
  -> reconciled MLflow run and logged model ref
  -> time-series model evaluation and incumbent/baseline comparison
  -> immutable registered-model version
  -> explicit promotion evidence and optional alias assignment
  -> alias resolved to an immutable version
  -> deployment manifest and offline/online inference parity validation
  -> model-backed strategy and backtest
  -> prediction monitoring and drift reports
```

Feature engineering and fitting are reproducible product stages, not notebook side effects. Feature specs record source
implementations, hashes, lookbacks, availability times, preprocessing fit scope, schema, and missing/stale policy.
Training specs record Data Agent refs, point-in-time target construction, chronological folds, purge/embargo, code and
environment hashes, hyperparameters, resources, seeds, and the configured MLflow experiment. Maintained, handwritten,
or AI-produced trainer code must be registered and validated before execution.

MLflow is authoritative for experiment runs, logged model packages, registered-model versions, tags, and aliases.
Trader artifacts preserve the trading-specific lineage and policy evidence. A request may name an alias such as
`champion`, but backtests and runtime deployments pin the immutable version resolved at validation time. Alias movement
cannot alter an active run.

The model-backed strategy uses a core prediction interface and the same version-pinned inference/feature adapter in
backtests and the trading loop. The hot path does not call MCP or perform per-prediction MLflow writes. It emits bounded
prediction events with feature/model versions so the ML Agent can compute drift later. Initial deployment evidence is
limited to backtest and paper environments; live runtime changes remain explicit operator actions.

Model evaluation and strategy evaluation remain separate. The ML Agent can establish predictive performance,
calibration, stability, and leakage status. Only downstream strategy backtests and Evaluation reports can establish
whether those predictions produce useful trading evidence after costs and risk controls.

## Deferred Walk-Forward Optimisation Workflow

Chronological walk-forward validation is part of the planned ML training/evaluation workflow above. Full walk-forward
optimisation is deferred to tasks 58-59, after reproducible backtest specifications, model-backed strategy integration,
and core robustness variants exist.

```text
validated immutable strategy or model-backed deployment
  -> immutable base backtest specification
  -> walk-forward plan with folds, search space, objective, costs, and budget
  -> per-fold in-sample fitting or parameter search
  -> selection from declared in-sample/inner-validation evidence
  -> locked parameters or immutable model version
  -> untouched out-of-sample child backtest
  -> repeat with complete candidate and child-run lineage
  -> Evaluation-owned stitched OOS report
  -> Adversarial-owned walk-forward audit
```

The Supervisor owns optimisation procedure artifacts, not the performance or robustness verdict. ML folds delegate
feature/training/run/version work to ML tools; generic strategy folds create parameterized child backtest specs. The OOS
result for a fold is never fed back into that fold's selection.

Evaluation reports only stitched out-of-sample evidence. Adversarial independently perturbs fold boundaries, window
lengths, objectives, neighboring parameter/model choices, costs, data scope, and search budgets, and examines selection
instability, concentration, in-sample/OOS degradation, and multiple-testing risk. Neither stage mutates selections,
assigns a model alias, or promotes a deployment.

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

This remains a supported MCP toolchain, but it is no longer the active expansion focus. Strategy candidates are
source-backed, but data scope is supplied by the backtest through a Data Agent `dataset_manifest`.

For statistical-arbitrage evidence, an approved rich method card can also drive the maintained
`pairs_mean_reversion` strategy template directly. The resulting strategy candidate records rich method-card provenance
and remains data-free; symbols, timeframe, and date windows still come from Data Agent scope.

The 33N MCP regression proves the representative pairs/cointegration route end to end: generated book-style source
registration, full-document ingestion, candidate discovery, field extraction, validation, rich-card approval,
rich-card-driven strategy generation, risk stack validation, two-leg portfolio backtest execution, and Evaluation.

## Rich Methodology Operator Workflow

Use this workflow when the goal is to turn an ingested source into a richer method description that can later drive
bounded strategy or risk candidate generation.

This workflow is maintained at the 33AB functional baseline. It is appropriate for bounded, locally identifiable
methods and should fail closed when the source cannot support the requested fields. Composite book-scale framework
extraction is deferred; do not interpret the existence of the tools as a claim that every source can produce a usable
method card.

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
operator metadata. Ingestion reads the entire document, creates schema-v2 evidence units across the full source, indexes
those units, and makes them citeable by `chunk_id` / `evidence_unit_id`. If retrieval cannot find a topic after
registration, check ingestion status before assuming the knowledge base lacks the method. Legacy broad chunk manifests
are not translated; reset and reingest the source after the evidence-unit schema change. For a registered source,
`knowledge_ingest_documents(force=true)` replaces its active evidence units without loading or translating the legacy
payload first.

The detailed evidence hierarchy, non-exclusive chunk invariant, claim-span model, multi-span synthesis, and semantic
validation process are defined in [semantic_extraction.md](semantic_extraction.md).

Candidate discovery is not approval. Discovery groups candidate spans by discovered method identity, not by broad
heading or family proximity, and writes methodology candidate refs with canonical/source names, aliases, abbreviation
evidence, query alignment, and competing method-label diagnostics. Evidence assembly then applies family-level role
profiles, not known-target profiles, to find definition, input, formula, parameter, signal, limitation, validation, and
other role evidence where applicable. Role evidence counts only when the evidence unit contains role terms and is bound
to the target method identity by direct label, alias, same sentence, same paragraph, or accepted nearby context.
Competing adjacent methods are carried as rejected packet refs and diagnostics. Extraction fills only supported nullable
fields from candidate evidence units or accepted assembled role evidence, and every populated field must carry
source/chunk/locator evidence. Validation blocks candidates with invalid locators, unsupported field names, missing
family minimums, missing source-backed method identity, packet-less lineage, stale evidence-unit hashes, fields sourced
from rejected competing-method refs, insufficient high-risk evidence, excessive quotation, or textbook/primary-source
claims backed only by internal notes.

Draft cards are still review artifacts. Canonical method-card draft materialization requires packet-backed
implementation readiness and a candidate lineage that matches the validation packet. Caller-provided `method_id`,
`title`, or `family` values are accepted only when candidate identity or alias evidence supports them. Drafts can be
searched only when draft visibility is enabled and cannot satisfy strategy/risk generation until they are published.
Publishing preserves the full rich payload and exposes the shallow method-card projection so older citation, contract,
implementation, and packaging workflows continue to work.

The 33V open-world MCP regression proves this flow with method names that do not exist in the maintained source code.
It discovers and publishes one technical-indicator card and one statistical-arbitrage card, preserves their stable
method-card set lineage, and passes the approved statistical-arbitrage card into the maintained pairs strategy template.
The same regression blocks a definition-only technical method that lacks formula evidence, rejects an approved shallow
card for strategy generation, and rejects a target field contaminated with evidence from an adjacent named method.

That controlled regression is not sufficient evidence for arbitrary extracted PDF text. Evidence units are
non-exclusive context containers: one unit may legitimately support several methods, and adjacent method text is not by
itself a reason to reject the unit. Before materializing a canonical draft, inspect the candidate identity, packet
diagnostics, cited local claims, and extracted field values. Stop only when a populated field is not supported for the
selected target by its cited claim text, when required meaning cannot be assembled across cited units, or when
assumptions and failure modes are absent from accepted target-bound evidence. Do not repair those gaps with title
overrides, caller-authored prose, or publication; stronger claim-level semantic extraction must produce valid evidence
first.

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
