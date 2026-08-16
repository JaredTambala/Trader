# Research Agent Workflows

Research workflows are built as deterministic MCP tool chains first, then composed by LangGraph agents once the tool
surface is useful. All workflows stay outside live trading.

The procedures in this document describe callable tool graphs, not autonomous behavior. The Data Agent is the only
specialist with an operational tool-calling graph. Separately, ORCH-3 mechanically executes one already approved
implementation-to-evidence protocol through MCP; the Quant Research Supervisor does not yet formulate that protocol or
select the workflow. See
[product_state.md](product_state.md#agent-state) and the
[orchestration roadmap](../../plans/research_capability_roadmap.md#orchestration).

## Current Delivery Focus

Knowledge-base creation and bounded methodology extraction are now maintained dependencies, not the active expansion
track. The Data Agent workflow also remains supported and maintained. New delivery work should concentrate on a direct
implementation-to-evidence chain:

```text
handwritten or AI-produced indicator / strategy / risk-manager source
  -> immutable implementation registration and provenance
  -> interface, import, source-hash, fixture, and safety validation
  -> Data Agent dataset manifest and quality report
  -> immutable strategy/risk and backtest specifications
  -> canonical baseline or risk-scoped backtest
  -> optional provider-neutral parameter optimisation over selection data
  -> sealed untouched-holdout backtest
  -> ML model-version refs when the strategy uses a model
  -> Evaluation and independent Adversarial report
```

The implementation intake must not depend on the platform generating the source. Handwritten code and AI-produced code
are both untrusted supplied artifacts; both must satisfy the same platform interfaces and deterministic validation
gates. Bespoke method-card or source refs may be attached as provenance when available, but knowledge extraction is not
a prerequisite for testing an explicitly supplied implementation.

Implementation intake, specifications, canonical backtests, parameter optimisation, holdout Evaluation, and
optimisation audit are implemented. ML versioning and broader cost/data perturbation tooling remain planned.

## Target Orchestrated Supplied-Strategy Workflow

This is the target higher-level agent path. The middle deterministic execution segment is implemented by ORCH-3, but
the specialist planning and routing around it is not yet an executable coordinator graph:

```text
operator brief with supplied strategy and risk-manager refs
  -> Research Coordinator resolves prerequisites
  -> Data Agent returns scope and quality evidence
  -> deterministic services validate the supplied implementations
  -> Experiment Design Agent proposes an experiment protocol
  -> operator approves material assumptions
  -> deterministic compiler creates immutable specifications
  -> workflow executor runs baseline, optimisation and sealed holdout
  -> Robustness Agent declares attacks
  -> workflow executor runs immutable variants
  -> Robustness Agent reports sensitivity findings
  -> Evaluation Agent issues the final research-quality assessment
  -> Research Coordinator returns refs, blockers and permitted next actions
```

The experiment protocol owns the proposed test design: strategy/risk refs, Data requirements, costs, initial state,
selection/holdout policy, tunable dimensions, objective, constraints, search budget, robustness requirements,
evaluation questions and approval points. It cannot be rewritten after observing results. The workflow executor is not
an agent and makes no design, selection or quality judgment.

Quantitative Methods and ML are optional producers. Neither is required when the operator supplies validated
strategy/risk implementations and no model lifecycle work is requested.

### ORCH-1 Declaration, ORCH-2 Resume, And ORCH-3 Execution

The target flow has a concrete declaration vocabulary, an operational resume shell and one executable fixed template:

1. A `ResearchObjective` fixes operator intent, success criteria, supplied refs and constraints.
2. An `ExperimentProtocol` fixes implementation refs, role-labelled Data requirements, costs, initial state,
   optimisation design, robustness requirements, falsification criteria and material approval decisions.
3. A `WorkflowPlan` selects only versioned `CapabilityDefinition` entries, binds their inputs and outputs to typed
   `ArtifactSlot` values, and names all `Prerequisite` and approval gates.
4. Plan construction validates the dependency graph and readiness. It rejects invented capabilities or arguments,
   artifact authority mismatches and dependency cycles before an executor can run.
5. ORCH-3 deterministically compiles the approved supplied-implementation protocol into the fixed registered
   capability DAG and persists the objective, protocol and plan.
6. ORCH-2 compiles the ready plan into a deterministic LangGraph shell. The next step emits a bounded interrupt naming
   the plan, capability, producer tool, side effect, attempt and configuration digest.
7. The ORCH-3 executor builds arguments only from pinned artifact slots and closed invocation recipes, calls the
   registered MCP tool, validates its command/owner/side-effect envelope and resolves every returned canonical ref.
8. ORCH-3 adapts the response to a `WorkflowStepResult`. The shell validates identity, attempt, command, side effect and
   output cardinality, then checkpoints only a bounded summary and canonical refs.
9. Retryable blockers repeat the same step with an incremented attempt. Exact duplicate result keys are ignored;
   conflicting content, changed plan digests and invalid refs fail closed.
10. At terminal state, ORCH-3 persists a `WorkflowOutcome` containing produced refs, Review refs, blockers and next
    permitted actions.

The Postgres checkpoint can survive a connection restart, but it is operational state rather than research evidence.
`research_register_experiment_workflow` accepts the approved objective, protocol and compiled `WorkflowPlan`;
`research_record_workflow_outcome` accepts only a terminal outcome. The executor itself is a Python library over
`McpToolClient`, not a generic high-level MCP command.

The implemented template is `supplied_implementation_to_evidence` version 1:

```text
validate strategy and ordered risk implementations
  -> create and validate strategy/risk specifications
  -> create, validate and run baseline backtest
  -> optional provider-neutral optimisation
  -> selected specification on sealed holdout
  -> Evaluation report
  -> optional Adversarial plan, immutable variants and robustness report
  -> canonical workflow outcome
```

Use `data_create_research_snapshot` to persist each exact Data manifest/quality pair before protocol approval.
Compilation pins payload hashes; any input drift before use blocks the workflow. Backtest and optimisation gates remain
authoritative, and a blocked tool prevents later nodes from running. A controlled interruption retains the ORCH-2
checkpoint and resumes without replaying accepted steps. ORCH-4 will add bounded template selection rather than
unrestricted planning.

## Worked Implementation-To-Evidence Walkthrough

This is the shortest current journey from supplied strategy and risk-manager code to durable trading evidence.
A method card is not required. Handwritten, maintained, and externally generated source all enter through the same
content-addressed implementation boundary.

1. **Fix the data scope.** Call `data_discover_symbols` when discovery is needed, then
   `data_create_research_snapshot` to create and persist an exact Data Agent dataset manifest and matching quality
   report. The manifest ref, rather than loose symbol or date arguments, defines the rows available to the experiment.
2. **Admit executable behavior.** Call `research_register_strategy_implementation` and
   `research_validate_strategy_implementation`, then the corresponding
   `research_register_risk_manager_implementation` and `research_validate_risk_manager_implementation` tools. Each
   validation pins source identity and checks its interface, declared parameters, static safety rules, and deterministic
   fixture behavior.
3. **Configure strategy and risk behavior.** Create and validate a `strategy_specification` with
   `research_create_strategy_specification` and `research_validate_strategy_specification`. Create and validate an
   ordered `risk_stack_specification` with `research_create_risk_stack_specification` and
   `research_validate_risk_stack_specification`. These specifications bind validated implementation versions and
   parameters; they do not own symbols, timeframes, or date windows.
4. **Bind one reproducible experiment.** Call `research_create_backtest_specification` with the strategy and risk-stack
   specifications, exact dataset manifest and quality evidence, cost assumptions, initial state, and seed. Then call
   `research_validate_backtest_specification` to recheck source hashes, upstream validation, data snapshots, and scope.
5. **Execute and inspect.** With `TRADER_MCP_ALLOW_BACKTESTS=true`, call
   `research_run_backtest_specification`. The result is a canonical Postgres artifact such as
   `research://postgres/backtest_run/{run_id}`. Call `research_get_backtest_results` to read the run and its bundle,
   including trades, performance, final positions, per-symbol measures, exposures, risk decisions, and breach evidence.
6. **Optimise only when the question requires it.** Register and validate a closed-input objective with
   `research_register_optimization_objective` and `research_validate_optimization_objective`. Create a provider-neutral
   plan with `research_create_parameter_optimization_plan`, pinning the passed selection-region backtest specification
   and a sealed later holdout. With the backtest and optimisation gates enabled,
   `research_run_parameter_optimization` executes built-in grid, seeded-random, or configured optional Optuna
   suggestions as immutable child specifications and runs. The selected specification remains exploratory.
7. **Test the untouched holdout.** Create, validate, and run a separate backtest specification over the sealed holdout
   using the selected strategy specification. Generate
   `evaluation_generate_parameter_optimization_report` from the complete optimisation ledger and matching holdout run.
8. **Challenge the procedure independently.** Call `adversarial_create_parameter_optimization_audit_plan`; the
   Supervisor executes the requested immutable variants through `research_run_parameter_optimization_variants`; then
   `adversarial_generate_parameter_optimization_audit` judges the supplied evidence. Robustness owns attack selection
   and sensitivity judgment, while deterministic Experiment services execute variants.

| Evidence stage | What it proves | What it does not prove |
| --- | --- | --- |
| Implementation validation | The pinned source satisfies its declared interface, safety checks, and deterministic fixtures. | Profitability or correct economic intent. |
| Validated backtest run | One immutable strategy/risk/data/cost configuration executed reproducibly and produced inspectable evidence. | Generalisation beyond that data scope. |
| Optimisation selection | A declared objective selected one configuration from a complete, bounded selection ledger. | Holdout performance or freedom from selection bias. |
| Holdout Evaluation | The selected configuration's matching untouched-holdout evidence satisfies Evaluation checks. | Robustness to alternative procedures or production readiness. |
| Adversarial report | Declared variants and stresses support or challenge the optimisation procedure independently. | Permission to deploy or trade live. |

No stage in this workflow places an order, mutates the live runtime, or promotes a strategy automatically. Its product is
a connected graph of immutable Postgres artifacts whose identities and lineage can be queried independently.

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

The Data domain is authoritative for symbol discovery, dataset manifests, data-quality reports, and explicit load evidence. Downstream
strategy, backtest, and evaluation tools should consume Data Agent dataset/quality artifacts rather than loose symbols,
timeframes, or date windows.

## MLflow Model Lifecycle And Runtime Integration

The feature/training/evaluation/registry stages remain planned under 39A-G, while deployment and model-backed execution
are implemented by 39H-I. Until 39A-G is delivered, the registered deployment tools require passed feature-set and
immutable model-version artifacts supplied through controlled direct/test setup rather than a complete MCP-only
training graph.

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

MLflow is authoritative for ML training telemetry, logged model packages, registered-model versions, tags, and aliases.
Trader remains authoritative for generic optimisation and trading-specific lineage. A request may name an alias such as
`champion`, but backtests and runtime deployments pin the immutable version resolved at validation time. Alias movement
cannot alter an active run.

The model-backed strategy uses a core prediction interface and the same version-pinned inference/feature adapter in
backtests and the trading loop. The hot path does not call MCP or perform per-prediction MLflow writes. It emits bounded
prediction events with feature/model versions so the ML Agent can compute drift later. Initial deployment evidence is
limited to backtest and paper environments; live runtime changes remain explicit operator actions.

Model evaluation and strategy evaluation remain separate. The ML Agent can establish predictive performance,
calibration, stability, and leakage status. Only downstream strategy backtests and Evaluation reports can establish
whether those predictions produce useful trading evidence after costs and risk controls.

The implemented execution segment is:

```text
persisted immutable model version + passed feature-set validation
  -> ml_create_deployment_manifest
  -> ml_validate_deployment, with TRADER_MCP_ALLOW_ML_RUNTIME=true
  -> strategy implementation declaring prediction_requirements
  -> research_create_strategy_specification with typed prediction_bindings
  -> strategy/backtest specification validation
  -> research_run_backtest_specification with backtest and ML-runtime gates
  -> prediction_events -> mapped signal_events -> order decision_evidence -> risk/fill/backtest evidence
```

Manifest creation is DB-only. Validation and backtest inference load the pinned model once through the configured
adapter; neither resolves a mutable alias or calls MCP/MLflow tracking APIs per decision. Cross-sectional and portfolio
deployments become `universe_snapshot` strategy decisions and run once only when the complete symbol set shares one
decision timestamp.

## Parameter Optimisation And Independent Audit

```text
passed selection-region backtest specification
  -> sealed later holdout manifest and quality report
  -> validated closed-input objective
  -> provider-neutral optimisation plan
  -> grid, seeded-random, or configured optional Optuna suggestions
  -> immutable child specifications and canonical selection runs
  -> complete trial ledger and deterministic exploratory selection
  -> separately created holdout backtest using the selected strategy specification
  -> evaluation_generate_parameter_optimization_report
  -> adversarial_create_parameter_optimization_audit_plan
  -> Supervisor-executed immutable optimisation variants and backtest stresses
  -> adversarial_generate_parameter_optimization_audit
```

Optuna only proposes parameters and stores resumable sampler state in its dedicated schema. Built-in engines and
canonical result reads do not import it. `research_project_experiment_tracking` may mirror a completed canonical run to
a configured sink, but that report is explicitly non-authoritative and is not a prerequisite for Evaluation or audit.
The selected specification is exploratory until its sealed holdout Evaluation and Adversarial audit both pass.

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

Optimisation procedure artifacts have Experiments-domain authority; neither their current Supervisor tool steward nor
the workflow coordinator owns the performance or robustness verdict. ML folds delegate
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
  -> evidence-backed method-card draft
  -> approved method card
  -> optional maintained or external implementation producer
  -> normal content-addressed implementation registration and validation
  -> immutable strategy/risk specifications
  -> Data Agent-scoped backtest specification
  -> canonical backtest run
```

Knowledge and method cards remain supported, but candidate artifacts are no longer an execution boundary. Produced
source enters the same registry as handwritten source, and data scope is supplied only by the backtest specification.

For statistical-arbitrage evidence, an external or maintained producer may use an approved method card to author
source based on the `pairs_mean_reversion` template. That source still enters the normal implementation registry;
method-card lineage is optional provenance, while symbols, timeframe, and dates remain Data Agent scope.

The historical 33N regression remains methodology evidence; its candidate/stack handoff is superseded by the canonical
implementation/specification path.

## Methodology Operator Workflow

Use this workflow when the goal is to turn an ingested source into a complete, cited method description that may inform
an external implementation producer.

This workflow is maintained at the 33AB functional baseline. It is appropriate for bounded, locally identifiable
methods and should fail closed when the source cannot support the requested fields. Composite book-scale framework
method card.

```text
source registration
  -> full-document ingestion
  -> retrieval or source-scoped candidate discovery
  -> family-role evidence assembly
  -> methodology field extraction
  -> methodology candidate validation
  -> evidence-backed method-card draft
  -> explicit publish approval
  -> optional implementation producer
  -> content-addressed implementation registration and validation
  -> immutable strategy/risk/backtest specifications
  -> canonical backtest
  -> Evaluation or Adversarial report
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
Publishing preserves the complete payload. Search derives a compact summary at read time, while methodology engineering
uses the narrow approved-card read port. There is no writable summary card, alternate card format, or compatibility
reader for old payloads.

The 33V open-world MCP regression proves this flow with method names that do not exist in the maintained source code.
It discovers and publishes one technical-indicator card and one statistical-arbitrage card, preserves their stable
method-card set lineage, and passes the approved statistical-arbitrage card into the maintained pairs strategy template.
The same regression blocks a definition-only technical method that lacks formula evidence and rejects a target field
contaminated with evidence from an adjacent named method.

That controlled regression is not sufficient evidence for arbitrary extracted PDF text. Evidence units are
non-exclusive context containers: one unit may legitimately support several methods, and adjacent method text is not by
itself a reason to reject the unit. Before materializing a canonical draft, inspect the candidate identity, packet
diagnostics, cited local claims, and extracted field values. Stop only when a populated field is not supported for the
selected target by its cited claim text, when required meaning cannot be assembled across cited units, or when
assumptions and failure modes are absent from accepted target-bound evidence. Do not repair those gaps with title
overrides, caller-authored prose, or publication; stronger claim-level semantic extraction must produce valid evidence
first.

Approved method cards can drive only maintained bounded templates. The pairs mean-reversion template requires an approved
statistical-arbitrage card with strategy-template readiness plus evidence for spread or legs, relationship testing or
hedge-ratio logic, entry logic, exit logic, and price/input requirements. Risk templates can consume approved risk-model
or portfolio-construction cards with risk-manager readiness, but numeric limits must be explicit structured values;
prose does not become a VaR, CVaR, concentration, or drawdown limit.

Operator examples:

- Pairs trading or cointegration: ingest a textbook or paper section covering pairs, spreads, hedge ratios,
  cointegration or stationarity tests, entry thresholds, and exits. Discover statistical-arbitrage candidates by source
  ID or query, validate the extracted fields, publish the method card, and use it with the pairs mean-reversion template.
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
canonical backtest_run ID or URI
  -> research_get_backtest_results
  -> research_compare_backtest_results, for explicit run refs
  -> sealed-holdout Evaluation when the run is an optimisation selection
```

Comparison reports warn when runs are not like-for-like. Evaluation reports are descriptive and skeptical; missing or
incomplete data-quality evidence blocks the report status.

## Portfolio Risk Toolchain

```text
validated strategy and risk implementation versions
  -> strategy specification and ordered risk-stack specification
  -> one Data Agent-scoped backtest specification
  -> canonical risk-scoped backtest
  -> exposure, decision, breach, and risk-measure evidence
```

Risk limits must be explicit in validated implementation/spec parameters. VaR/CVaR values are never invented from
prose; Evaluation blocks when required risk telemetry is absent.

## Handoff And Blockers

- Each tool returns warnings for non-fatal caveats and blockers/errors for conditions that make downstream use unsafe.
- Agent handoffs preserve `domain_owner`, `producer_tool`, `requested_by`, `actor`, warnings, blockers and canonical
  artifact identity.
- Coordinator workflows stop early when required specialist artifacts are missing, failed, blocked, or declare the
  wrong domain authority.
- Research outputs may become human-reviewed promotion proposals, but they do not trigger live trading.
