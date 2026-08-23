# Research Agent Workflows

Research workflows are built as deterministic MCP tool chains first, then composed by LangGraph agents once the tool
surface is useful. All workflows stay outside live trading.

The procedures in this document describe callable tool graphs, not unrestricted autonomous behavior. Data and
Experiment Design are specialists on the common resumable task/result boundary. The Research Coordinator selects a
bounded next action, and composition executes their registered routes, pauses for explicit operator decisions over the
immutable proposal, then enters the one registered implementation-to-evidence workflow. The fixed executor runs that
plan mechanically through MCP. See
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

This is the target higher-level agent path. Bounded Data-and-design-to-fixed-workflow composition is implemented.
Optional producer, general Robustness and final Evaluation specialist graphs are not:

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

The immutable protocol proposal owns the proposed test design: strategy/risk refs, Data requirements, costs, initial state,
selection/holdout policy, tunable dimensions, objective, constraints, search budget, robustness requirements,
evaluation questions and approval points. It cannot be rewritten after observing results. The workflow executor is not
an agent and makes no design, selection or quality judgment.

Quantitative Methods and ML are optional producers. Neither is required when the operator supplies validated
strategy/risk implementations and no model lifecycle work is requested.

### Specialist Task And Result Flow

Every specialist integration uses the same bounded connection:

```text
SpecialistTask
  -> specialist policy selects a registered action, prerequisite, completion or blocker
  -> registered handler parses role-specific input and may call MCP
  -> shell validates canonical handoffs and requested output-slot bindings
  -> SpecialistResult returns handoffs, prerequisites, blockers or errors
```

The task permits side-effect classes and policy gates explicitly. Policy decisions bind only registered action IDs,
canonical input URIs and declared output slots; they cannot inject MCP tool names or arguments. The handler owns the
role-specific typed request and strips raw transport data before returning. The shell requires canonical artifact URIs
for accepted handoffs and can use an injected checkpointer. A stable task digest and accepted-action digests prevent
task drift or accepted-action replay. The Data and Experiment Design action catalogs are operational through the
default composition routes. The Coordinator selects routes by task identity, authority, digest and version;
composition performs the calls and validates the returned evidence.

The implemented composition sequence is:

1. The caller supplies one approved objective and explicit specialist tasks; composition never derives Data scope or
   experiment choices from objective prose. The Design task must reference Data evidence that already exists.
2. The Coordinator selects the first unaccepted task through the unique code-owned route. The Data graph returns a
   manifest and quality handoff or a typed prerequisite/blocker.
3. The Experiment Design graph validates its complete request and exact input refs, calls
   `research_create_experiment_protocol_proposal`, reloads the immutable proposal and returns its canonical handoff.
4. Composition resolves the proposal, checkpoints a bounded receipt and pauses for the requested approvals. The
   operator applies explicit decisions with `apply_experiment_protocol_approvals` and resumes with that unchanged
   approved protocol. Its design digest and Data refs must match the accepted proposal.
5. The Coordinator selects the fixed template; composition runs the executor and gives its canonical outcome back to
   the Coordinator for terminal reporting.

Exact replay does not repeat accepted specialist actions, workflow registration, workflow steps or outcome recording.
Changed request/task/proposal/protocol content, route ambiguity, invalid handoffs and transition-budget exhaustion fail closed.

### Declaration, Resume, And Deterministic Execution

The target flow has a bounded coordinator policy, a concrete declaration vocabulary, an operational resume shell and
one executable fixed template:

1. A `ResearchObjective` fixes operator intent, success criteria, supplied refs and constraints.
2. An `ExperimentProtocol` fixes implementation refs, role-labelled Data requirements, costs, initial state,
   optimisation design, robustness requirements, falsification criteria and material approval decisions.
3. The Research Coordinator emits one closed `CoordinationDecision`: execute a registered specialist task, request a
   prerequisite, request approval, execute a registered workflow, report terminal state or block. It contains no tool
   arguments or experiment overrides.
4. A code-owned `WorkflowTemplateCatalog` accepts only registered template IDs and versions. Exactly one eligible
   template must match an approved protocol before compilation.
5. A `WorkflowPlan` selects only versioned `CapabilityDefinition` entries, binds their inputs and outputs to typed
   `ArtifactSlot` values, and names all `Prerequisite` and approval gates.
6. Plan construction validates the dependency graph and readiness. It rejects invented capabilities or arguments,
   artifact authority mismatches and dependency cycles before an executor can run.
7. The fixed-template compiler reads and hashes the supplied canonical refs and deterministically creates the fixed capability
   DAG. Compilation itself writes nothing.
8. The workflow executor calls `research_register_experiment_workflow` to persist the approved objective, protocol and
   ready plan before any plan step runs.
9. The resume layer compiles the ready plan into a deterministic LangGraph shell. The next step emits a bounded interrupt naming
   the plan, capability, producer tool, side effect, attempt and configuration digest.
10. The workflow executor builds arguments only from pinned artifact slots and closed invocation recipes, calls the
   registered MCP tool, validates its command/owner/side-effect envelope and resolves every returned canonical ref.
11. The executor adapts the response to a `WorkflowStepResult`. The shell validates identity, attempt, command, side effect and
   output cardinality, then checkpoints only a bounded summary and canonical refs.
12. Retryable blockers repeat the same step with an incremented attempt. Exact duplicate result keys are ignored;
   conflicting content, changed plan digests and invalid refs fail closed.
13. At terminal state, the executor calls `research_record_workflow_outcome` to persist a `WorkflowOutcome` containing
    produced refs, Review refs, blockers and next
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
  -> [when optimisation is declared]
       provider-neutral optimisation
       -> selected specification on sealed holdout
       -> Evaluation report
       -> [when robustness requirements are non-empty]
            Adversarial plan, immutable variants and robustness report
  -> canonical workflow outcome
```

Use `data_create_research_snapshot` to persist each exact Data manifest/quality pair before protocol approval.
Compilation pins payload hashes; any input drift before use blocks the workflow. Backtest and optimisation gates remain
authoritative, and a blocked tool prevents later nodes from running. A controlled interruption retains the operational
checkpoint and resumes without replaying accepted steps. The coordinator can select only catalogued templates and
typed prerequisite-resolution actions; unrestricted planning is not an intended capability.

The library entry point makes the remaining caller responsibilities explicit:

| Caller supplies | Orchestration supplies |
| --- | --- |
| Approved `ResearchObjective` and matching approved `ExperimentProtocol` | A deterministic, content-addressed `WorkflowPlan` |
| Canonical strategy/risk implementation refs and matching Data snapshot refs | Revalidation, specification construction and registered MCP execution |
| Passed optimisation-objective validation when optimisation is declared | Selection, sealed holdout, Evaluation and declared robustness branches |
| Stable workflow ID, `McpToolClient`, artifact store and checkpointer | Bounded retries, resumable progress and one terminal `WorkflowOutcome` |

The artifact store visible to the compiler/executor must resolve the same canonical records returned by the MCP server.
The workflow ID selects checkpoint state and execution provenance; it is not a substitute for the immutable plan ID.

## Worked Implementation-To-Evidence Walkthrough

This is the shortest current journey from supplied strategy and risk-manager code to durable trading evidence.
A method card is not required. Handwritten, maintained, and externally generated source all enter through the same
content-addressed implementation boundary. Steps 1-3 prepare approved inputs; steps 4-8 describe what the current
compiler/executor automates. The same MCP tools remain callable individually for explicit operator-driven procedures.

1. **Fix the data scope outside the executor.** Call `data_discover_symbols` when discovery is needed, then
   `data_create_research_snapshot` to persist an exact Data Agent dataset manifest and matching quality report for each
   baseline/selection/holdout role. The canonical refs, rather than loose symbol or date arguments, define the rows
   available to the experiment.
2. **Register supplied behavior outside the executor.** Call `research_register_strategy_implementation` and
   `research_register_risk_manager_implementation` for the supplied source. Direct callers may preflight with
   `research_validate_strategy_implementation` and `research_validate_risk_manager_implementation`; the compiled plan
   runs those validations again from the pinned implementation refs before creating specifications.
3. **Propose and approve the design outside the executor.** Build a complete `ExperimentDesignRequest` and run the
   Experiment Design specialist, or call `research_create_experiment_protocol_proposal` through an explicit operator
   procedure. Inspect its canonical proposal, decide every requested `Approval`, and use
   `apply_experiment_protocol_approvals` to obtain the unchanged approved protocol. When optimisation is
   declared, first use `research_register_optimization_objective` and
   `research_validate_optimization_objective`; the protocol must pin the passed validation plus separate selection and
   sealed-holdout Data snapshots.
4. **Compile without side effects.** `compile_supplied_implementation_workflow` resolves and hashes every supplied ref,
   builds the fixed capability/artifact DAG, and returns a ready plan. Missing approvals, mismatched identities,
   unsupported robustness without optimisation, unresolved artifacts or failed objective validation stop here.
5. **Run the mandatory baseline.** `execute_compiled_research_workflow` registers the objective/protocol/plan, then the
   plan validates implementations, calls `research_create_strategy_specification` and
   `research_validate_strategy_specification`, calls `research_create_risk_stack_specification` and
   `research_validate_risk_stack_specification`, and creates/validates/runs the backtest through
   `research_create_backtest_specification`, `research_validate_backtest_specification` and
   `research_run_backtest_specification`.
6. **Inspect canonical evidence.** The baseline produces a Postgres ref such as
   `research://postgres/backtest_run/{run_id}`. `research_get_backtest_results` reads its bounded bundle, including
   trades, performance, final positions, per-symbol measures, exposures, risk decisions and breach evidence. The
   executor checkpoints the ref and hash, not that full payload.
7. **Optimise and evaluate only when declared.** The compiled optional branch calls
   `research_create_parameter_optimization_plan` and `research_run_parameter_optimization`, then creates, validates and
   runs the selected specification against the sealed holdout. It calls
   `evaluation_generate_parameter_optimization_report` over the complete optimisation ledger and matching holdout run.
   The selected specification remains exploratory.
8. **Challenge the procedure when robustness requirements are declared.** The compiled branch calls
   `adversarial_create_parameter_optimization_audit_plan`, executes the requested immutable variants through
   `research_run_parameter_optimization_variants`, and calls
   `adversarial_generate_parameter_optimization_audit`. Review owns attack selection and sensitivity judgment while
   deterministic Experiment services execute variants. The terminal workflow outcome collects both Review refs and
   permits human review; it does not grant deployment.

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
approved objective + normalized bounded Data request
  -> validate_market_data_scope -> data_discover_symbols
  -> [optional, separately approved] ensure_market_data_available -> data_ensure_loaded(sample)
  -> capture_market_data_evidence -> data_create_research_snapshot
  -> resolve both refs through the canonical store
  -> completed manifest/quality handoffs, typed prerequisite, or Data-fitness blocker
```

The deterministic policy names registered responsibilities, never MCP commands or argument bodies. Only checked-in
sample loading is registered because its writes are replay safe; arbitrary backfill is not a specialist action. The
snapshot handler validates artifact type, Data ownership, producer, requester, actor, captured status, exact scope,
payload digest and matching dataset identity. Incomplete evidence blocks the task but retains both canonical refs for
inspection. Direct Data MCP tools remain available to explicit operator callers.

The Data domain is authoritative for symbol discovery, dataset manifests, data-quality reports, and explicit load
evidence. Downstream strategy, backtest, and evaluation tools should consume Data Agent dataset/quality artifacts
rather than loose symbols, timeframes, or date windows.

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
