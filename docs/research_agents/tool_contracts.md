# Research Agent Tool Contracts

This document defines the active contract for research-agent tools. The current direction is:

```text
deterministic trader_research services
  -> MCP tools in trader_mcp
  -> LangGraph agent identities in trader_agents
```

MCP is the tool boundary. LangGraph is the agent identity and orchestration layer. Tools must produce structured
artifacts that match the owning agent's responsibilities in [agents.md](agents.md).
The Quant Research Supervisor Agent may coordinate specialist work, but each specialist-owned artifact keeps its own
`agent_owner`.

Use [mcp_tools.md](mcp_tools.md) for the current registered MCP catalog. This file is the detailed contract appendix for
request fields, envelope shapes, artifact payloads, and validation behavior.

## Functional Status Boundary

This appendix contains both implemented contracts and planned contract names. Only tools listed as registered in
[mcp_tools.md](mcp_tools.md) and returned by `mcp_get_config` are callable. In particular:

- current strategy/risk candidate contracts are maintained-template and generated-source contracts;
- no registered tool currently accepts an arbitrary handwritten or externally AI-produced strategy/risk package as a
  first-class versioned implementation;
- no registered immutable backtest-specification tool exists independently of the current candidate/stack inputs;
- ML feature/model versioning, broader Evaluation critique, attribution, robustness/adversarial, recommendation, and
  experiment-runner names in this appendix are planned rather than registered;
- tasks 56-57 define the next implementation intake and backtest-specification contracts, followed by task 39 model
  versioning and tasks 44/46 robustness work.

Knowledge-base and bounded methodology contracts remain implemented and maintained at the 33AB baseline. Composite
methodology expansion is deferred under 33AC.

### Planned MLflow Contract Invariants

Tasks 39A-39J will add the ML contracts; none are currently callable. All ML requests and artifacts must obey these
rules:

- MLflow tracking and registry locations come from approved server configuration, not request payloads.
- MLflow experiment/run/model refs are reconciled into Trader Postgres artifacts with source, dataset, feature,
  environment, signature, and digest evidence.
- Data Agent manifests own market-data scope. Feature and training tools reject loose hidden scope and inconsistent
  dataset refs.
- Training uses explicit chronological split plans with target horizons, purge/embargo, and point-in-time leakage
  evidence. Random splitting is not the default time-series contract.
- Registered-model aliases are mutable selectors. Every training evaluation, backtest, deployment manifest, trading
  session, prediction, and drift report records an immutable resolved model version.
- Model-version tags and aliases represent lifecycle state; deprecated MLflow model stages are not used.
- Supplied trainer code is an immutable validated artifact. MCP does not execute prompt text, arbitrary notebook state,
  or an unvalidated pickle.
- Runtime inference uses a dependency-neutral core contract and an optional MLflow adapter. It does not call MCP or
  perform per-prediction MLflow tracking writes.
- Model evaluation is ML-owned predictive evidence. Strategy profitability remains Evaluation-owned backtest evidence.
- MLflow writes, training, alias assignment, and runtime deployment have separate policy gates. The ML Agent cannot
  mutate live trading or broker state.

### Deferred Walk-Forward Contract Invariants

Tasks 58-59 add full walk-forward optimisation after the reproducible backtest, ML deployment, and robustness
prerequisites. Chronological validation folds in 39C/39F remain earlier ML correctness contracts.

- `walk_forward_optimization_plan` is immutable and records implementation/deployment refs, base backtest spec, fold
  boundaries, purge/embargo, candidate search space, objective, constraints, costs, seeds, budgets, and stop/resume
  policy before execution.
- Each fold records in-sample/selection and untouched out-of-sample boundaries separately. Selected parameters or model
  version are locked before creating the out-of-sample child specification.
- Every evaluated/rejected candidate, score, exception, seed, selected ref, child specification, backtest, and MLflow
  run/model ref remains visible. Results cannot retain only the winner.
- Out-of-sample results cannot alter the same fold's selection. Procedure-level tuning against aggregate results must be
  disclosed and may require nested walk-forward evidence.
- `walk_forward_evaluation_report` contains stitched out-of-sample evidence only; in-sample/selection returns are not
  reported as walk-forward performance.
- `walk_forward_robustness_report` is independently Adversarial-owned and cannot mutate the optimisation run, model
  alias, deployment, or promotion state.
- The optimisation runner declares the maximum side effect it may perform. An ML-enabled run requires the backtest,
  MLflow-write, and training gates in addition to its general execution gate.

## Control Plane And Execution Plane

Research tooling has two separate configuration planes.

The MCP server is the control plane. It owns only:

- process startup and stdio transport
- server identity, registered tool names, descriptions, and static metadata
- artifact root and server-local policy flags
- capability gates such as `TRADER_MCP_ALLOW_DATA_LOADING`

The tool/runtime layer is the execution plane. It owns only:

- typed tool requests and deterministic service contracts
- injected dependencies such as event stores, catalog providers, runners, and policies
- trader runtime YAML used to build execution dependencies
- runtime dotenv values used by that YAML, such as Postgres and Alpaca credentials

These planes must remain one-way and lazy:

- The MCP server must be able to start, list tools, and answer `mcp_health` / `mcp_get_config` without a valid trader
  YAML, broker credentials, database connection, or backtest runtime.
- A broken execution-plane config must fail inside the affected tool call as a structured envelope. It must not prevent
  MCP server startup or tool registration.
- Execution services in `trader_research` must not read `local.env`, inspect MCP transport details, depend on MCP client
  identity, or branch on which process called them.
- MCP adapters may translate JSON-native tool inputs into typed requests and inject dependencies, but deterministic
  services must know only their request objects, dependency interfaces, and explicit runtime policy.
- Runtime `.env` files are for execution-plane YAML expansion only. They are loaded lazily before building the trader
  config for a tool, never as a prerequisite for MCP server startup.
- Duplicating values across env files is acceptable when those values serve different planes. Avoid "DRY" env loading
  that couples MCP process startup to execution runtime secrets, broker settings, database settings, or script defaults.

## Envelope

Every MCP tool returns a stable envelope:

```json
{
  "ok": true,
  "command": "data_get_inventory",
  "agent_owner": "Data Agent",
  "side_effect": "read_only",
  "schema_version": "1",
  "generated_at": "2026-05-26T12:00:00+00:00",
  "data": {},
  "artifacts": {},
  "warnings": [],
  "errors": []
}
```

Fields:

- `ok`: command success.
- `command`: stable MCP tool identifier.
- `agent_owner`: agent that owns the artifact and decision boundary.
- `side_effect`: declared side-effect class.
- `schema_version`: envelope schema version.
- `generated_at`: UTC timestamp.
- `data`: machine-readable result.
- `artifacts`: generated or consumed artifact references.
- `warnings`: non-fatal issues.
- `errors`: structured fatal errors when `ok=false`.

Canonical MCP research artifact refs use `research://postgres/{artifact_type}/{artifact_id}` when the structured
research artifact store is configured. `ArtifactReference.path` remains for fallback direct-service exports and legacy
baseline bundles; MCP clients should prefer `uri` when present.

## Side Effects

| Class | Meaning | Allowed examples |
| --- | --- | --- |
| `read_only` | Reads config, event-store data, local artifacts, or broker/operator snapshots without writing. | Inventory, data quality summary, result lookup. |
| `local_mutating` | Writes local artifacts or bounded research records; never submits broker orders. | Dataset manifest, quality report, sample load, backtest artifact, robustness report. |
| `external_research_mutating` | Future class for mutating an approved external research service without broker or live-runtime mutation. | MLflow run creation, model registration, tags, and aliases. Not implemented in the current enum. |
| `broker_read` | Reads broker state through operator-owned surfaces. | Future read-only operator context tools. |
| `broker_mutating` | Mutates broker state. | Not allowed for research-agent MCP tools. |

Adding `external_research_mutating` requires an implementation change to the shared side-effect enum, MCP metadata,
agent policy, tests, and documentation before any MLflow-writing tool is registered. Training execution and alias
promotion also require independent policy gates even though both use the external research mutation class.

No research-agent tool may start `TraderService`, submit orders, clear halt state, reconcile broker state, run raw SQL,
or bypass core platform validation.

## Initial Data Agent Tools

| Tool | Side Effect | Primary artifact |
| --- | --- | --- |
| `data_get_inventory` | `read_only` | `dataset_manifest.json` payload or reference |
| `data_summarize_quality` | `read_only` | `data_quality_report.json` |
| `data_ensure_loaded` | `local_mutating` | load/backfill evidence plus dataset manifest update |

These tools are implemented first because the Data Agent owns the ingredients that later research agents consume.

## Agent Tool Inventory

| Tool | Owning agent | Primary artifact |
| --- | --- | --- |
| `knowledge_register_source` | Quantitative Methods Agent | `knowledge_source_manifest.json` or `knowledge://postgres/knowledge_source_manifest/...` |
| `knowledge_ingest_documents` | Quantitative Methods Agent | `knowledge_ingestion_report.json`, schema-v2 evidence units stored in Postgres `knowledge_chunks`, `knowledge_embedding_manifest.json` or `knowledge://postgres/...` refs |
| `knowledge_get_ingestion_status` | Quantitative Methods Agent | source and ingestion status summary |
| `knowledge_list_sources` | Quantitative Methods Agent | source manifest listing |
| `knowledge_search_methods` | Quantitative Methods Agent | approved method-card search result |
| `knowledge_list_method_card_sets` | Quantitative Methods Agent | stable method-card set summaries |
| `knowledge_get_method_card_set` | Quantitative Methods Agent | method-card set revision history |
| `knowledge_retrieve_evidence` | Quantitative Methods Agent | `evidence_retrieval_report.json` with lexical/vector/combined rank diagnostics |
| `knowledge_get_evidence_chunks` | Quantitative Methods Agent | `evidence_chunk_dereference_report.json` with bounded stored chunk text |
| `knowledge_discover_methodology_candidates` | Quantitative Methods Agent | `research://postgres/methodology_candidate/...` refs |
| `knowledge_assemble_methodology_evidence` | Quantitative Methods Agent | `research://postgres/methodology_evidence_packet/...` refs |
| `knowledge_extract_methodology_fields` | Quantitative Methods Agent | `methodology_field_extraction_report` and updated `methodology_candidate` refs |
| `knowledge_validate_methodology_candidate` | Quantitative Methods Agent | `methodology_candidate_validation_report` with readiness summary |
| `knowledge_create_method_card_draft` | Quantitative Methods Agent | `method_card_draft.json` |
| `knowledge_create_rich_method_card_draft` | Quantitative Methods Agent | rich `method_card_draft` payload with `card_format="rich_method_card"` |
| `knowledge_publish_method_card` | Quantitative Methods Agent | approved `method_card.json` |
| `knowledge_update_method_card_status` | Quantitative Methods Agent | retired `method_card.json` status update |
| `knowledge_validate_citations` | Quantitative Methods Agent | `citation_validation_report.json` |
| `math_list_method_contracts` | Quantitative Methods Agent | method contract catalog for indicators, transforms, statistical tests, diagnostics, and multiple-testing procedures |
| `math_validate_method_contract` | Quantitative Methods Agent | method contract validation report |
| `math_register_method_implementation` | Quantitative Methods Agent | `method_implementation_manifest.json` |
| `math_run_indicator_fixtures` | Quantitative Methods Agent | `indicator_validation_report.json` |
| `math_run_signal_fixtures` | Quantitative Methods Agent | `signal_implementation_validation_report.json` |
| `math_generate_python_method` | Quantitative Methods Agent | quarantined generated Python source plus registration and fixture-validation results |
| `math_run_signal_diagnostics` | Quantitative Methods Agent | `signal_diagnostic_report.json` |
| `math_run_multiple_testing_report` | Quantitative Methods Agent | `multiple_testing_report.json` |
| `math_generate_cpp_kernel` | Quantitative Methods Agent | draft `cxx_kernel_manifest.json` from an approved template |
| `math_compile_kernel` | Quantitative Methods Agent | local compiled-kernel build evidence |
| `math_package_method_artifact` | Quantitative Methods Agent | source-backed `method_package_manifest.json` for validated Python indicator/signal implementations |
| `math_run_cpp_conformance` | Quantitative Methods Agent | deferred compiled-kernel conformance/equivalence report |
| `ml_get_runtime`, `ml_health`, `ml_list_experiments` | ML Agent | planned configured MLflow runtime/health metadata |
| `ml_create_feature_set`, `ml_validate_feature_set` | ML Agent | planned `ml_feature_set_spec` and validation report |
| `ml_create_training_dataset`, `ml_create_time_series_split_plan` | ML Agent | planned point-in-time dataset and chronological split artifacts |
| `ml_register_training_pipeline`, `ml_validate_training_pipeline`, `ml_create_training_spec`, `ml_run_training` | ML Agent | planned training pipeline/spec and MLflow fitting evidence |
| `ml_get_training_run`, `ml_reconcile_mlflow_run` | ML Agent | planned reconciled `mlflow_run_ref` |
| `ml_evaluate_model`, `ml_compare_model_versions` | ML Agent | planned time-series model evaluation/comparison reports |
| `ml_register_model_version`, `ml_get_model_version`, `ml_list_model_versions`, `ml_resolve_model_alias`, `ml_assign_model_alias` | ML Agent | planned immutable model-version and promotion artifacts |
| `ml_create_deployment_manifest`, `ml_validate_deployment` | ML Agent | planned version-pinned deployment evidence |
| `ml_summarize_predictions`, `ml_compute_drift_report` | ML Agent | planned prediction and drift artifacts |
| `hypothesis_create_card` | Hypothesis Agent | `hypothesis_card.json` |
| `research_create_plan` | Quant Research Supervisor Agent | experiment plan |
| `research_list_strategy_templates` | Quant Research Supervisor Agent | strategy template catalog |
| `research_create_strategy_candidate` | Quant Research Supervisor Agent | `strategy_candidate_manifest.json` and strategy source |
| `research_validate_strategy_candidate` | Quant Research Supervisor Agent | strategy candidate validation report |
| `research_run_backtest` | Quant Research Supervisor Agent | `backtest_run_ref.json` plus backtest artifact bundle |
| `research_run_portfolio_backtest` | Quant Research Supervisor Agent | `portfolio_backtest_run_ref.json` plus risk-scoped portfolio backtest bundle |
| `research_get_backtest_results` | Quant Research Supervisor Agent | result summary and artifact paths |
| `research_compare_backtest_results` | Quant Research Supervisor Agent | `comparison_report.json` over explicit backtest refs |
| `research_list_risk_manager_templates` | Quant Research Supervisor Agent | risk-manager template catalog |
| `research_create_risk_manager_candidate` | Quant Research Supervisor Agent | `risk_manager_candidate_manifest.json` and risk-manager source |
| `research_validate_risk_manager_candidate` | Quant Research Supervisor Agent | `risk_manager_candidate_validation_report.json` |
| `research_create_strategy_risk_stack` | Quant Research Supervisor Agent | `strategy_risk_stack_manifest.json` |
| `research_validate_strategy_risk_stack` | Quant Research Supervisor Agent | `strategy_risk_stack_validation_report.json` |
| `research_create_walk_forward_plan`, `research_run_walk_forward_optimization`, `research_get_walk_forward_results` | Quant Research Supervisor Agent | deferred walk-forward plan/run/result artifacts |
| `evaluation_generate_performance_report` | Evaluation Agent | first practical `evaluation_report.json` from backtest/data-quality artifacts |
| `evaluation_generate_walk_forward_report` | Evaluation Agent | deferred stitched out-of-sample walk-forward Evaluation report |
| `evaluation_generate_report` | Evaluation Agent | later skeptical critique report |
| `adversarial_run_robustness` | Adversarial Agent | `robustness_report.json` |
| `adversarial_audit_walk_forward` | Adversarial Agent | deferred walk-forward robustness report |
| `research_analyze_return_attribution` | Quant Research Supervisor Agent | attribution report |
| `research_generate_recommendation` | Quant Research Supervisor Agent | recommendation report |
| `research_run_experiment` | Quant Research Supervisor Agent | composed experiment output |

## Method Package Artifacts

`math_package_method_artifact` packages a validated Python implementation for downstream strategy tools. It is
local-mutating and writes `method_package_manifest.json`; it does not create strategy candidates.

Request fields:

- `implementation_id` or `implementation_manifest`: a `method_implementation_manifest` whose `status` is `validated`.
- `validation_report_id` or `validation_report`: a passed `indicator_validation_report` or
  `signal_implementation_validation_report` matching the implementation.
- Optional `cxx_kernel_id` or `cxx_kernel_manifest`: compiled C++ metadata for the same Python implementation.

Success data contains `method_package_manifest` with:

- package ID, method ID, runtime contract, implementation ID, entrypoint, class name, source path/hash/provenance, and
  constructor kwargs.
- method contract snapshot, approved method-card refs, validation report ref, validation summary, safety profile, and
  dependency allowlist.
- optional accepted `cxx_kernel_refs`, warnings, blockers, `status="validated"`, and schema version.

Python validation is the gate. Packaging fails closed when the implementation is not validated, source hashes do not
match, approved method-card refs are missing, runtime contracts are unsupported, or the validation report is missing,
failed, blocked, mismatched, or the wrong report type. C++ refs are optimization metadata only: missing, generated,
uncompiled, mismatched, or otherwise invalid C++ refs produce warnings and are excluded without blocking a valid Python
package.

## Strategy Candidate Catalog And Builder

Task 25 implements the deterministic `trader_research.strategy_candidates.list_strategy_templates` service for the
`research_list_strategy_templates` command. Task 26 implements the deterministic
`trader_research.strategy_candidates.create_strategy_candidate` service for the `research_create_strategy_candidate` command.
Task 27 registers both tools through MCP and adds `research_validate_strategy_candidate`.

The read-only success payload is:

```json
{
  "templates": [],
  "template_count": 5,
  "supported_strategy_families": [
    "trend_following",
    "mean_reversion",
    "bollinger_band",
    "cross_sectional_momentum",
    "pairs_mean_reversion"
  ]
}
```

Each template entry includes:

- `template_family`, `display_name`, `description`, `runtime_builder_path`, and `runtime_strategy_id`.
- `parameters` with names, JSON value types, required flags, defaults where available, and validation constraints.
- `required_artifact_types` and `required_artifact_roles`, declarative `method_package_manifest` refs for validated
  signal packages where the maintained template requires packages.
- `entry_semantics`, `exit_semantics`, `sizing`, `risk_assumptions`, `backtest_context_requirements`, and
  `constraints`.

The public catalog exposes only maintained strategy families backed by `trader_standard` builders. Long/flat templates
include `trend_following`, `mean_reversion`, and `bollinger_band`; multi-asset templates include
`cross_sectional_momentum` and `pairs_mean_reversion`. It does not dynamically import arbitrary strategy code, expose
test helpers such as no-op strategies, or allow broker mutation.

`research_create_strategy_candidate` writes two coupled artifacts:

- `strategy_candidate`, the provenance and validation contract.
- `strategy_implementation`, a deterministic Python strategy source artifact.

Under MCP, these artifacts are stored in the configured research artifact store and returned with
`research://postgres/strategy_candidate/{candidate_id}` and
`research://postgres/strategy_implementation/{candidate_id}` refs. Direct services without an artifact store retain
the legacy filesystem export paths under `artifact_root / "strategy_candidates" / ...`.

The generated Python source is the strategy implementation. It must expose a `build_strategy(...)` factory that returns
an object implementing `trader.strategies.Strategy`. The source binds the maintained strategy family and strategy
parameters, while validation or backtest tooling supplies symbols, asset class, and timeframe when instantiating it.
The generated class name is semantic and template-derived, such as `BollingerBandResearchStrategy`; the opaque
`candidate_id` remains in `CANDIDATE_ID`, manifest metadata, `strategy_id`, and `strategy_info` rather than being baked
into the class name.

The `strategy_candidate` manifest records:

- `candidate_id`, `template_family`, `method_package_refs`, optional `methodology_refs`, `signal_refs`,
  `strategy_source`, and template `parameters`.
- `strategy_source` with artifact type `strategy_implementation`, source path or URI, source hash, class name, factory name,
  runtime contract `trader.strategies.Strategy`, template/builder provenance, and portfolio-construction metadata.
- Declarative `entry_semantics` and `exit_semantics`.
- `sizing` assumptions for fixed-quantity long/flat templates.
- Named `risk_assumptions`.
- JSON-safe `execution_assumptions`, including the explicit deferred runtime-instantiation boundary and no-live-trading
  flags.
- Structured `warnings` and `blockers`.

Maintained templates declare `portfolio_mode` (`single_symbol`, `per_symbol_independent`, or `cross_sectional`),
rebalance cadence, allocation bounds, and portfolio-state requirements. Strategy candidates deliberately do not record
symbols, asset class, timeframe, start, or end. Those fields belong to the later backtest or experiment request that
binds a validated strategy candidate to a data window.

`research_create_strategy_candidate` is a local-mutating direct service. It accepts:

- `artifact_root`.
- `template_family`, which must be one of the maintained catalog families.
- `method_package_refs`, where each item supplies a template `role` plus exactly one of `package_id`, `path`, or inline
  `package_manifest`.
- Optional rich method-card input by exactly one of `rich_method_card_id`, `rich_method_card_uri`, or inline
  `rich_method_card`.
- Optional scalar `parameters`, fixed-quantity `sizing`, `risk_assumptions`, and `execution_assumptions`.

Package IDs resolve from the research artifact store when configured, or from
`artifact_root / "method_packages" / "manifests" / f"{package_id}.json"` for legacy direct-service calls. Successful
calls return `data["strategy_candidate_manifest"]` plus `strategy_candidate` and `strategy_source` artifact references.

Candidate construction fails closed before writing when:

- The template family is unsupported.
- Required template roles are missing, duplicated, or unknown.
- A role does not reference a `method_package_manifest` with `status="validated"`, empty blockers, approved method-card
  refs, source hash, package ID, method ID, and the required runtime contract.
- Raw `method_implementation_manifest` inputs are supplied instead of method packages.
- A rich-card-backed template receives a draft, shallow, unapproved, missing, or family-incompatible rich method card.
- `pairs_mean_reversion` is requested without an approved rich `statistical_arbitrage` method card carrying evidence
  for spread or legs, relationship testing or hedge-ratio logic, entry logic, exit logic, and price/input requirements.
- Parameter grids/lists, unknown parameters, invalid numeric bounds, or `must_exceed` violations are supplied.
- Symbols, asset class, timeframe, start, or end are supplied as strategy parameters.
- Fixed-quantity sizing is negative, uses an unsupported sizing model, or conflicts with `target_qty_when_long`.
- Execution assumptions attempt arbitrary strategy code, broker mutation, live trading, dynamic stop-policy
  configuration, or non-market orders.

Task 23N provides validated `method_package_manifest.json` artifacts for these refs. Task 26 creates source-backed
strategy code but does not run backtests, validate executable behavior, or expose MCP tools.

`research_validate_strategy_candidate` is a local-mutating MCP/direct service. It accepts exactly one of:

- `candidate_id`, resolved from `artifact_root / "strategy_candidates" / "manifests" / f"{candidate_id}.json"`.
- `path` to a `strategy_candidate_manifest.json`.
- Inline `strategy_candidate_manifest`.

Validation writes `strategy_candidate_validation_report.json` under
`artifact_root / "strategy_candidates" / "validation_reports" / f"{validation_id}.json"` and returns
`data["strategy_candidate_validation_report"]`.

The validation report contains `validation_id`, `candidate_id`, `template_family`, `status`, `runtime_builder_path`,
`runtime_strategy_id`, `strategy_info`, `checks`, `fixture_summary`, `warnings`, `blockers`, and schema version. Passed
reports have `status="passed"` and no blockers. Resolved candidates that fail validation still persist a failed report
and return an error envelope containing that report.

Validation proves maintained-template runtime compatibility only. It verifies the strategy source ref, checks the
current source SHA-256, imports the generated strategy module, calls its `build_strategy(...)` factory with an internal
multi-symbol synthetic fixture context, runs a deterministic synthetic-bar smoke fixture, and verifies any emitted orders
are bounded market buy/sell intents for the fixture symbols. It does not dynamically load arbitrary package entrypoints,
read market data, touch brokers, mutate SQL, run backtests, or clear runtime/risk state. Task 28 owns baseline backtest
execution after candidate validation passes. Strategy candidates remain data-free; the backtest data scope is supplied
only by a Data Agent `dataset_manifest`.

## Risk Manager Candidate Catalog And Builder

`research_list_risk_manager_templates` is a Quant Research Supervisor read-only tool and direct service. It returns
source-generatable risk-manager template metadata; it does not dynamically import risk code, touch brokers, read market
data, or validate runtime behavior.

The read-only success payload is:

```json
{
  "templates": [],
  "template_count": 5,
  "supported_risk_manager_families": [
    "gross_exposure_cap",
    "per_symbol_exposure_cap",
    "concentration_cap",
    "drawdown_guard",
    "var_cvar_limit"
  ]
}
```

Each template entry includes:

- `template_family`, `display_name`, `description`, `runtime_contract="trader.risk.RiskManager"`, and
  `source_generator`.
- Scalar `parameters` with JSON value types, required flags, defaults where available, and validation constraints.
- Optional `method_package_roles` for sourced risk-measure telemetry; refs must be validated
  `method_package_manifest.json` artifacts.
- Declarative `policy_intent`, no-live-trading `execution_assumptions`, `validation_requirements`, and additional
  constraints.

`research_create_risk_manager_candidate` is a local-mutating MCP/direct service. It accepts:

- `artifact_root`.
- `template_family`, one of the maintained risk-manager catalog families.
- Optional scalar `parameters`.
- Optional `method_package_refs`, where each item supplies a template `role` plus exactly one of `package_id`, `path`,
  or inline `package_manifest`.
- Optional rich method-card input by exactly one of `rich_method_card_id`, `rich_method_card_uri`, or inline
  `rich_method_card`. Approved `risk_models` or `portfolio_construction` rich cards add methodology provenance; the
  `var_cvar_limit` template can map explicit numeric `limit_thresholds` into `max_var_fraction` and
  `max_cvar_fraction`.
- Optional `execution_assumptions`.

Successful calls write two coupled artifacts:

- `risk_manager_candidate` manifest.
- `risk_manager_implementation` deterministic Python source artifact.

Under MCP, these artifacts are stored in the configured research artifact store and returned with
`research://postgres/risk_manager_candidate/{candidate_id}` and
`research://postgres/risk_manager_implementation/{candidate_id}` refs. Direct services without an artifact store retain
the legacy filesystem export paths under `artifact_root / "risk_managers" / ...`.

The generated Python source is a backtest-only research candidate. It exposes `build_risk_manager(...)` and returns an
object implementing `trader.risk.RiskManager`; it records the template family and bounded parameters but does not
mutate brokers, raw SQL, or live risk state. Policy validation/enforcement and portfolio backtest use are deferred to
the later risk-manager validation and strategy/risk stack tasks.

`risk_manager_candidate_manifest.json` uses artifact type `risk_manager_candidate` and records:

- `candidate_id`, `template_family`, optional `method_package_refs`, optional `methodology_refs`, and template
  `parameters`.
- `risk_manager_source` with artifact type `risk_manager_implementation`, source path or URI, source hash, class name,
  factory name, runtime contract `trader.risk.RiskManager`, and template provenance.
- Declarative `policy_intent`, JSON-safe no-live-trading `execution_assumptions`, `validation_requirements`, `status`,
  structured `warnings`, and `blockers`.

Risk-manager candidates deliberately do not record symbols, asset class, timeframe, start, end, or source filters.
Those fields belong to Data Agent dataset manifests consumed by later strategy/risk stack and portfolio backtest tools.

Candidate construction fails closed before writing when:

- The template family is unsupported.
- Required parameters are missing, unknown parameters are supplied, parameter grids/lists are supplied, or numeric
  bounds are violated.
- A rich card is supplied but is a draft, shallow, unapproved, family-incompatible, or lacks the required risk-control or
  threshold evidence for the selected template.
- A `var_cvar_limit` rich card is expected to supply thresholds but `limit_thresholds` is prose-only or lacks numeric
  `max_var_fraction` and `max_cvar_fraction` values.
- A method-package role is unknown, duplicated, unresolved, or references raw `method_implementation_manifest` input
  instead of a `method_package_manifest`.
- A method-package ref is not `status="validated"`, has blockers, lacks approved method-card refs, lacks source hash or
  IDs, or declares an unsupported runtime contract.
- Execution assumptions attempt live trading, broker mutation, raw SQL access, or disable the backtest-only boundary.

`research_validate_risk_manager_candidate` is a local-mutating MCP/direct service. It accepts exactly one of:

- `candidate_id`, resolved from `artifact_root / "risk_managers" / "manifests" / f"{candidate_id}.json"`.
- `path` to a `risk_manager_candidate_manifest.json`.
- Inline `risk_manager_candidate_manifest`.

Validation writes `risk_manager_candidate_validation_report.json` under
`artifact_root / "risk_managers" / "validation_reports" / f"{validation_id}.json"` and returns
`data["risk_manager_candidate_validation_report"]`. The report contains the candidate ID, template family, runtime
contract, source ref, checks, fixture summary, policy intent, required telemetry, warnings, blockers, and schema version.
Validation checks the manifest, source hash, source safety markers, no-live-trading execution assumptions, validation
requirements, runtime instantiation as `trader.risk.RiskManager`, and a deterministic risk-context fixture. It does not
run a backtest, touch brokers, mutate SQL, or enforce live risk policy.

`research_create_strategy_risk_stack` is a local-mutating MCP/direct service. It accepts:

- One passed strategy validation report by `strategy_validation_id`, `strategy_validation_report_path`, or inline
  `strategy_candidate_validation_report`.
- One or more ordered passed risk-manager validation refs, each by `validation_id`, `path`, or inline
  `risk_manager_candidate_validation_report`.
- Optional stack `execution_assumptions`, which must keep the backtest-only, no-broker-mutation, no-live-trading, and
  no-raw-SQL boundaries.

Successful calls write `strategy_risk_stack_manifest.json` under
`artifact_root / "portfolio_stacks" / "manifests" / f"{stack_id}.json"`. The manifest records the validated strategy
candidate ref, strategy validation report ref, ordered risk-manager refs with priority and validation-report provenance,
and stack execution assumptions. Creation fails closed when any validation report is missing, failed, blocked,
duplicated, or mismatched with its candidate.

`research_validate_strategy_risk_stack` is a local-mutating MCP/direct service. It accepts exactly one of `stack_id`,
`path`, or inline `strategy_risk_stack_manifest`. Validation writes `strategy_risk_stack_validation_report.json` under
`artifact_root / "portfolio_stacks" / "validation_reports" / f"{validation_id}.json"`. It verifies stack manifest
integrity, risk-manager ordering, passed validation refs, source hashes, runtime contracts, no-live-trading execution
assumptions, risk telemetry hooks, and a deterministic multi-symbol fixture that instantiates the strategy, instantiates
the ordered risk managers, and runs candidate orders through `trader.risk.RiskPipeline`.

Task 33D registers `research_validate_risk_manager_candidate`, `research_create_strategy_risk_stack`, and
`research_validate_strategy_risk_stack` through MCP. It does not run portfolio backtests or generate portfolio/risk
evaluation reports; those remain later task-33 slices.

## Data-Scoped Baseline Backtests

`research_run_backtest` is a Quant Research Supervisor local-mutating tool and direct service. It runs one baseline
backtest through the platform `BacktestRunner` with `NoOpRiskManager` and a generated strategy source file from a
passed strategy-candidate validation report.

Required request inputs:

- Exactly one strategy candidate ref: `candidate_id`, `candidate_path`, or inline `strategy_candidate_manifest`.
- Exactly one passed validation report ref: `validation_id`, `validation_report_path`, or inline
  `strategy_candidate_validation_report`.
- Exactly one Data Agent dataset manifest input: inline `dataset_manifest`, `dataset_manifest_path`, or
  `dataset_manifest_ref`.

Optional request inputs:

- `data_quality_report` or `data_quality_report_path`; when supplied, it must match the dataset manifest symbols, asset
  class, timeframe, window, source filter, row counts, and completeness.
- `assumptions`, `initial_cash`, `initial_positions`, `max_runs`, and `log_cycle_details`.

Loose backtest scope fields are rejected. Do not pass `symbols`, `asset_class`, `timeframe`, `start`, `end`, or
`source_filter` outside the dataset manifest. The normalized `BacktestDataScope` is derived from `dataset_id`,
`symbols`, `asset_class`, `timeframe`, `requested_window`/`time_range`, `source_filter`, `total_rows`, and `complete`.
The v1 runner records `source_filter` in provenance but fails closed when a non-null source filter is supplied because
the underlying platform bar loader does not yet source-filter replay queries.

The service writes a bundle under `artifact_root / "backtests" / "runs" / run_id /`:

- `backtest_run_ref.json`
- `result.json`
- `metrics.json`
- `provenance.json`
- `equity_curve.csv`
- `benchmark_curve.csv`
- `positions.csv`
- `trades.csv` when trades exist

Success data contains `backtest_run_ref`, summary metrics, the normalized data scope, and artifact paths. The run ref
records `candidate_id`, `validation_id`, `dataset_id`, full data scope, status, warnings, blockers, and bundle paths.

`research_get_backtest_results` is read-only. It accepts exactly one of `run_id`, `artifact_dir`, or inline
`backtest_run_ref`, reads only task-28 bundles, and returns the run ref, summary metrics, data scope, candidate and
validation refs, warning/blocker summaries, provenance, and artifact paths.

`research_compare_backtest_results` is Quant Research Supervisor local-mutating because it writes
`comparison_report.json`. It accepts:

- `backtest_runs`: explicit refs only, minimum 2 and maximum 50. Each ref must contain exactly one of `run_id`,
  `artifact_dir`, or inline `backtest_run_ref`.
- Optional `ranking_metric`, defaulting to `sharpe`.
- Optional `sort_order`, either `ascending` or `descending`; omitted values use the metric default.

The comparison service reads only task-28 bundles: `backtest_run_ref.json`, `metrics.json`, and `provenance.json`. It
does not scan directories, query SQL/event-store experiment tables, run backtests, or recompute metrics from curves or
trades. Reports are written under
`artifact_root / "backtests" / "comparisons" / f"{comparison_id}.json"`.

Supported ranking metrics are `sharpe`, `total_return`, `max_drawdown`, `turnover`, `alpha`, `beta`, `fees`,
`slippage`, `warnings_count`, `trade_count`, `failed_runs`, and `total_runs`. Default sort order is descending for
`sharpe`, `total_return`, `alpha`, `beta`, `trade_count`, and `total_runs`; it is ascending for `max_drawdown`,
`turnover`, `fees`, `slippage`, `warnings_count`, and `failed_runs`. Runs with missing or non-numeric ranking metrics
are included but unranked and placed after ranked rows. Fewer than two rankable rows is blocking.

`comparison_report.json` contains `comparison_id`, `artifact_type="comparison_report"`, `status`, `ranking_metric`,
`sort_order`, `run_count`, `ranked_rows`, `best_run_id`, `comparable_dimensions`, `warnings`, `blockers`, and schema
version. Ranked rows include run ID, candidate ID, validation ID, dataset ID, run status, summary metrics, data scope,
artifact paths, warning/blocker counts, ranking metric value, and rank where available.

The service warns, but does not block, when runs differ in dataset ID, symbols, asset class, timeframe, time range,
source filter, assumptions, candidate ID, or validation ID. It fails closed for too few refs, duplicate run IDs,
unresolved refs, invalid metric/order, missing `backtest_run_ref.json`, invalid artifact type, or missing metrics.

MCP registration exposes all three backtest-result tools. `research_run_backtest` remains execution-gated by
`TRADER_MCP_ALLOW_BACKTESTS=true`; disabled environments still list the tool and return `backtests_not_allowed` before
touching the event store or runtime config. `research_get_backtest_results` is read-only.
`research_compare_backtest_results` is not gated by `TRADER_MCP_ALLOW_BACKTESTS` because it compares persisted bundles
only.

## Risk-Scoped Portfolio Backtests

`research_run_portfolio_backtest` is a Quant Research Supervisor local-mutating tool and direct service. It runs one
portfolio backtest through the platform `BacktestRunner` with a strategy and ordered risk managers from a passed
`strategy_risk_stack_validation_report`.

Required request inputs:

- Exactly one passed strategy/risk stack validation report ref:
  `strategy_risk_stack_validation_id`, `strategy_risk_stack_validation_report_path`, or inline
  `strategy_risk_stack_validation_report`.
- Exactly one Data Agent dataset manifest input: inline `dataset_manifest`, `dataset_manifest_path`, or
  `dataset_manifest_ref`.

Optional request inputs are `data_quality_report` or `data_quality_report_path`, `assumptions`, `initial_cash`,
`initial_positions`, `max_runs`, and `log_cycle_details`. Loose backtest scope fields are rejected; symbols, asset
class, timeframe, date window, and source filter must come from the Data Agent manifest. Non-null source filters still
fail closed until the platform replay loader can enforce source-filtered bars.

The service resolves the persisted stack manifest by `stack_id`, requires passed stack validation with no blockers,
rechecks strategy and risk-manager source hashes and no-live-trading assumptions, then runs the existing
`BacktestRunner` through a research-only recording risk pipeline. The recording pipeline preserves the normal
`RiskManager` approval/rejection contract and writes decision telemetry only as research artifacts.

When a research artifact store is configured, the service writes one structured `portfolio_backtest_run_ref` record with
the run ref plus the standard result, metrics, provenance, equity/trade/position payloads, and portfolio risk sidecars
embedded in a DB payload. The run ref returns `artifact_dir=null`, empty `artifact_paths`, and
`artifact_uris["portfolio_backtest_run_ref"]`. Direct services without an artifact store retain the legacy filesystem
bundle under `artifact_root / "portfolio_backtests" / "runs" / run_id /`:

- `portfolio_backtest_run_ref.json`
- `result.json`, `metrics.json`, `provenance.json`, `equity_curve.csv`, `benchmark_curve.csv`, `positions.csv`, and
  `trades.csv` when trades exist
- `symbol_metrics.json`, `exposure_summary.json`, `risk_decisions.json`, `risk_limit_breaches.json`, and
  `risk_measure_summary.json`

Success data contains `portfolio_backtest_run_ref`, summary metrics, normalized data scope, sidecar summaries, and
artifact refs. The run ref records stack IDs, dataset ID, data scope, status, symbol metrics, exposure summary,
risk-measure summary, warnings, blockers, and paths or URIs. Missing VaR/CVaR or other required risk telemetry is recorded as
portfolio backtest warning evidence; Evaluation decides whether the omission blocks the report.

MCP exposes `research_run_portfolio_backtest` with `agent_owner="Quant Research Supervisor Agent"` and
`side_effect="local_mutating"`. It is gated by `TRADER_MCP_ALLOW_BACKTESTS=true`, like `research_run_backtest`.

## Evaluation Performance Reports

`evaluation_generate_performance_report` is an Evaluation Agent local-mutating tool and direct service. It reads one
persisted baseline or portfolio backtest bundle and writes a descriptive `evaluation_report`; it does not run
backtests, query SQL/event-store tables, create strategies, scan arbitrary directories, or recompute core metrics from
raw curves.

Required request input:

- Exactly one backtest ref: `run_id`, `artifact_dir`, inline `backtest_run_ref`, or inline
  `portfolio_backtest_run_ref`.

Optional request input:

- One data-quality evidence input: inline `data_quality_report`, `data_quality_report_path`, or
  `data_quality_report_ref`.

With a configured research artifact store, the service resolves `portfolio_backtest_run_ref` records by URI or run ID
and writes `evaluation_report` rows back to the store. Baseline filesystem refs still resolve from the legacy bundle
when no matching DB run record exists. Direct services without an artifact store write reports under
`artifact_root / "evaluation" / "performance_reports" / f"{report_id}.json"`.

The report uses `artifact_type="evaluation_report"` and `report_kind="performance_report"`. It contains `report_id`,
`status`, `backtest_kind`, `run_id`, candidate/validation/dataset refs, optional strategy/risk stack refs, normalized
data scope, core metrics, trade stats, cost assumptions and realized costs, benchmark and relative metrics, portfolio
symbol metrics, exposure summary, risk decisions, risk-limit breaches, risk-measure summary, data-quality summary,
artifact paths, caveats, warnings, blockers, and schema version. Core metrics include total return, Sharpe, max
drawdown, turnover, trade count, hit rate when available, fees, slippage, failed runs, warning count, alpha, beta,
tracking error, and information ratio.

Resolved backtest bundles always produce a report. The report has `status="blocked"` when blockers exist and
`status="passed"` otherwise. Missing or incomplete data-quality evidence, data-quality scope mismatches, failed runs,
run blockers, zero-trade backtests, missing portfolio risk sidecars, or missing required portfolio risk telemetry are
blocking. Missing optional benchmark fields, missing hit-rate/trade stats, runtime warnings, and zero fee/slippage
assumptions are caveats or warnings. Unresolved refs, corrupt JSON, invalid artifact type, ambiguous run IDs, missing
`metrics.json`, or missing `result.json` fail closed before writing a report.

MCP exposes `evaluation_generate_performance_report` with `agent_owner="Evaluation Agent"` and
`side_effect="local_mutating"`. It is not gated by `TRADER_MCP_ALLOW_BACKTESTS` because it only reads persisted bundles
and writes an Evaluation-owned report.

Compatibility aliases may be kept while the older Math Coder naming is retired:

| Alias | Canonical tool |
| --- | --- |
| `math_list_indicator_contracts` | `math_list_method_contracts` filtered to indicator and transform families |
| `math_validate_indicator_contract` | `math_validate_method_contract` filtered to indicator and transform families |

The `math_*` namespace is a tool namespace, not a claim that the agent is limited to coding indicators. The owning
identity is Quantitative Methods Agent.

Knowledge-base rules:

- Hybrid retrieval combines lexical and vector indexes; those indexes are retrieval infrastructure, not authority.
- Runtime MCP knowledge storage uses Postgres by default. PostgreSQL full-text search handles lexical retrieval and
  pgvector handles dense retrieval; tests may inject a JSON compatibility store.
- The authority is the approved source registry plus approved method cards.
- Evidence retrieval should return citeable schema-v2 evidence units with source IDs, locators, source approval status,
  local label metadata, neighbor refs, and lexical/vector rank metadata rather than opaque context blobs.
- Evidence dereferencing is explicit: agents call `knowledge_get_evidence_chunks` with retrieved `chunk_id` values to
  receive real stored evidence-unit text, source metadata, locators, text hashes, `hash_verified`, text length metadata,
  and `text_truncated`. The request field remains `chunk_ids`; the values are evidence-unit IDs after schema v2.
- Legacy broad chunk manifests are not translated. A knowledge base created before schema-v2 evidence units must be
  reset and reingested so old chunk refs do not silently contaminate methodology artifacts.
- `knowledge_ingest_documents(force=true)` performs source-scoped replacement without first deserializing existing
  evidence rows. This allows an operator to regenerate incompatible evidence-unit versions without adding legacy
  translation or compatibility reads.
- Ingestion builds and validates the complete embedding generation before replacing active evidence. The Postgres store
  publishes replacement evidence units, vectors, the embedding manifest, and the success report in one transaction;
  provider or publication failure leaves the prior active generation visible.
- Ingestion does not imply approval; `method_card_draft.json` is not executable.
- Sophisticated statistical-test and multiple-testing contracts must cite approved method cards and pass
  `knowledge_validate_citations`. Seeded cards and persisted approved cards in the configured `KnowledgeStore` are both
  visible to citation and math validation.
- Knowledge tools must not expose arbitrary filesystem access, execute code from documents, or reproduce large source
  passages in artifacts.

Rich methodology schema:

The conceptual semantic-extraction design and execution graph are defined in
[semantic_extraction.md](semantic_extraction.md). This appendix defines transport and artifact contracts.

- `methodology_candidate` is a Quantitative Methods artifact for source-backed candidate structure before approval or
  execution. It is not a method card, implementation, strategy, or risk manager.
- `methodology_evidence_packet` is a Quantitative Methods artifact that records family-role evidence assembled from
  candidate evidence units before field extraction. It stores role IDs, found/missing roles, accepted role
  evidence-unit refs, rejected or weak role refs, source/chunk/text hashes, readiness goal, and diagnostics. Each role
  ref records `target_binding`, `accepted_target_binding`, binding terms, competing method labels, and the reason it was
  accepted or rejected. It is not a method card or approval.
- Rich method cards keep the existing `method_card_draft` and `method_card` artifact types and add
  `card_format="rich_method_card"` plus nullable rich fields, so shallow method-card search remains compatible.
- Rich fields are grouped into common core groups: `identity`, `scope`, `data_requirements`, `method_specification`,
  `signal_decision_logic`, `portfolio_execution`, `risk_validation`, and `implementation_notes`.
- Domain extension blocks are nullable and closed: `technical_indicators`, `statistical_arbitrage`,
  `options_derivatives`, `fundamental_valuation`, `sentiment_alternative_data`, `portfolio_construction`,
  `risk_models`, and `execution_methods`.
- Each populated field uses the same shape: `value`, `evidence_refs`, optional `confidence`, optional `quality`,
  `warnings`, and `blockers`. Populated values require at least one field-level evidence ref. Null fields do not require
  evidence.
- Unsupported core groups, extension blocks, or field names fail closed at schema construction.
- Source suitability matters. Internal notes can support operator-local context, but textbook or primary-source claims
  for high-risk families need real textbook, paper, documentation, or comparable curated sources. The validator blocks
  textbook/primary-source claims backed only by internal notes.
- Rich-card fields are descriptive evidence, not executable code. They can provide provenance, defaults, and template
  eligibility only where a maintained service explicitly supports the method family.

Methodology candidate tool contracts:

- `knowledge_discover_methodology_candidates` request: optional `query`, optional `source_ids`, optional
  `method_families`, `top_k=25`, `neighbor_radius=1`, `max_candidates=10`, and `approved_only=true`. At least one of
  `query`, `source_ids`, or `method_families` is required.
- Discovery combines retrieval, direct source evidence-unit scans, neighboring evidence units, local method-label
  evidence, deterministic method-identity grouping, and de-duplication. Source-level method families are scope hints,
  not automatic candidate labels. Candidate records carry `method_identity` with canonical/source name, aliases,
  abbreviations, identity evidence-unit refs, query alignment, and competing method labels. Success writes
  `methodology_candidate` records and returns `research://postgres/...` refs. It does not create method cards,
  implementations, strategies, or approvals.
- `knowledge_assemble_methodology_evidence` request: exactly one of `methodology_candidate_id`,
  `methodology_candidate_uri`, or inline `methodology_candidate`; optional `readiness_goal`, `neighbor_radius`, and
  `max_chunks_per_role`.
- Evidence assembly selects a family-level evidence profile, searches candidate/source evidence units for role-specific
  evidence, and writes `methodology_evidence_packet`. Role profiles are target-agnostic: they define evidence
  categories such as definition, input data, formula, parameters, signal logic, risk controls, limitations, and
  validation requirements, but they do not enumerate known method names. A role item counts only when the evidence unit
  contains role terms and is bound to the target method by direct label, alias label, same sentence, same paragraph, or
  accepted nearby context. Generic family nouns do not satisfy specialized implementation roles by themselves; for
  example, calling something an indicator is not formula or algorithm evidence. Competing labels, missing role terms,
  and weak context are retained under `rejected_chunks` and diagnostics, not counted as readiness evidence. Missing
  required accepted roles produce packet blockers.
- `knowledge_extract_methodology_fields` request: exactly one candidate input or evidence-packet input
  (`methodology_candidate_id`, `methodology_candidate_uri`, inline `methodology_candidate`, `evidence_packet_id`,
  `evidence_packet_uri`, or inline `evidence_packet`); optional `max_chars_per_chunk`.
- Extraction dereferences candidate evidence units and, when a packet is supplied, populates only fields supported by
  accepted target-bound role evidence. Evidence units are non-exclusive; packet refs carry accepted and rejected exact
  claim spans within each unit. Rejected or weak spans never populate fields, even when the surrounding unit also
  contains accepted target evidence. Field-level source/chunk/claim-span refs identify every contributing
  span, including offsets, selected text/hash, role, target binding, and extraction version. Field-specific semantic
  filters prevent generic role evidence from populating specialized fields, and bounded multi-span synthesis retains all
  contributing refs. Unrelated extension blocks remain absent/null. Success writes the updated
  `methodology_candidate` plus `methodology_field_extraction_report`.
- `knowledge_validate_methodology_candidate` request: exactly one candidate input or extraction-report ref
  (`methodology_candidate_id`, `methodology_candidate_uri`, inline `methodology_candidate`, `extraction_report_id`, or
  `extraction_report_uri`).
- Validation checks source/chunk existence, chunk-source consistency, locator matches, closed field groups and names,
  field-level refs, quote limits, family minimums, high-risk family evidence counts, internal-note-only textbook or
  primary-source claims, source-backed method identity, required identity evidence-unit refs, packet role consistency
  against accepted target-bound role refs, stale packet source/locator/text hashes, and fields that cite rejected or
  competing-method evidence. Packet lineage is required for passed semantic validation; packet-less extraction can
  populate fields but cannot validate into a canonical method-card draft. It writes
  `methodology_candidate_validation_report` with status `passed` or `blocked` and readiness summaries for descriptive,
  implementation, signal, strategy-template, or risk-manager use where the family profile defines them.
- Methodology field refs must include exact `claim_span` provenance. Validation re-slices stored evidence-unit text at
  the supplied offsets, recomputes the span hash, checks role and target binding, and verifies specialized field semantics.
  Another method appearing elsewhere in the same evidence unit is not a blocker.
- `knowledge_create_rich_method_card_draft` request: exactly one of `methodology_candidate_validation_id`,
  `methodology_candidate_validation_uri`, or inline `methodology_candidate_validation_report`; optional `method_id`,
  `title`, `family`, and `version`.
- Canonical method-card draft materialization requires a packet-backed passed validation report with `valid=true`, empty
  blockers, implementation readiness, and a loadable matching `methodology_candidate` whose lineage points to the same
  evidence packet as the validation report. Optional `method_id`, `title`, or `family` overrides fail closed unless the
  candidate identity, aliases, abbreviations, and validated families support them. The service revalidates source/chunk
  evidence, derives summary fields from evidence-backed rich fields, and fails closed if assumptions, inputs, outputs,
  or failure modes cannot be populated.
  Success writes a rich `method_card_draft` with nullable field groups, field-level evidence refs, candidate lineage,
  validation refs, source hashes, and chunk hashes while preserving shallow `MethodCard` projection compatibility.
- `knowledge_publish_method_card` preserves rich payloads when publishing rich drafts. Approved rich cards remain visible
  to existing shallow method-card search, citation validation, method contracts, implementation registration, and method
  packaging through their shallow projection.
- Approved rich cards can also become `methodology_refs` on strategy and risk-manager candidates. A maintained template
  decides which readiness gate and rich fields are required and whether structured numeric values may be mapped into
  parameters. Missing readiness, missing rich fields, draft cards, shallow cards, unapproved cards, incompatible
  families, and prose-only numeric limits block candidate generation rather than being inferred.
- These tools are DB-first `local_mutating` tools. MCP requires a configured research artifact store and fails closed
  with `research_artifact_store_unavailable` when canonical DB persistence is unavailable.

`knowledge_get_evidence_chunks` contract:

- Request: `chunk_ids: list[str]` required, maximum 25; optional `source_id`; `include_text: bool = true`;
  `max_chars_per_chunk: int = 4000`, bounded to 1-20000.
- Success data: `evidence_chunk_dereference_report`, top-level `chunks`, `chunk_count`, and `missing_chunk_ids`.
- Each returned item is a schema-v2 evidence unit and includes `chunk_id`, `evidence_unit_id`, `source_id`, source
  title/type/status, `approved_source`, `locator`, `topics`, `method_families`, `text_hash`, `hash_verified`,
  `text_char_count`, `text_word_count`, `text_truncated`, and `text` when requested.
- Missing chunk IDs or source mismatches fail closed with `code="chunk_dereference_error"` and structured
  `missing_chunk_ids` / `source_mismatch_chunk_ids`; no embedding vectors are returned.

`knowledge_create_method_card_draft` contract:

- Request: `method_id`, `title`, `family`, non-empty `assumptions`, `inputs`, `outputs`, `failure_modes`, and
  `evidence_refs`; optional `version`.
- Evidence refs must include at least one source or chunk reference and pass citation validation with
  `require_approved_method_card=false`.
- Success data contains a legacy/projection `method_card_draft`; draft cards are persisted but excluded from default
  approved method search and are not sufficient for canonical rich-methodology readiness.

`knowledge_publish_method_card` contract:

- Request: `draft_method_card_id`, `approved_method_card_id`, `approved_by`, `approval_note`, and `approve=true`.
- Publishing preserves the draft and creates a separate approved `method_card` with approval provenance.
- Publishing preserves `method_card_set_id` lineage, writes a new immutable card revision, supersedes any prior current
  approved card in the same set, and updates the set's current approved pointer.
- Re-publishing the same approved card is idempotent only when the persisted content matches; conflicting content fails
  closed.

Method-card set contracts:

- Method-card rows carry `method_card_set_id`, `revision_number`, and optional `supersedes_method_card_id`.
- Rows or payloads missing `method_card_set_id` or `revision_number` are invalid. The platform does not synthesize
  legacy set IDs or silently backfill old Postgres method-card data; operators should reset/recreate method-card rows or
  run an explicit reviewed migration when old data must be kept.
- A method-card set is the stable aggregate identity for a methodology card; `method_card_id` remains the immutable
  draft or approved revision ID used for exact citations.
- Draft creation derives a set ID from method ID, family, normalized title, and source fingerprint, unless the caller
  supplies an explicit set ID to create an intentional revision.
- Set summaries expose current approved and draft pointers, status counts, source fingerprint, card IDs, and latest
  revision number.
- The set-listing tool is read-only and supports method ID, family, status, retired visibility, and limit filters.
- The set-detail tool is read-only and returns one set plus revision history when requested.
- Postgres exposes pgAdmin-friendly active-card, revision-history, and set-summary views. Active views filter out
  `rejected` and `superseded` card rows; canonical storage preserves those rows for audit.

`knowledge_update_method_card_status` contract:

- Request: `method_card_id`, `status`, `updated_by`, `note`, and optional `superseded_by_method_card_id`.
- `status` is limited to `rejected` or `superseded`; the tool cannot approve cards or bypass
  `knowledge_publish_method_card`.
- `superseded_by_method_card_id` is required when `status="superseded"`.
- The target must be a persisted method card. Seeded cards are not retired by this tool.
- Success updates the stored method-card payload through the configured knowledge store, preserves lifecycle audit
  metadata, repairs method-card set current pointers, and hides the retired card from normal method-card search and
  approved-card checks.

`math_register_method_implementation` contract:

- Request: `method_id`, non-empty `method_card_ids`, optional `method_contract`, optional `entrypoint`, optional
  `source_path`, optional `class_name`, optional `constructor_kwargs`, optional `implementation_kind`
  (`maintained` or `generated`), optional `dependency_allowlist`, and optional `expected_source_hash`.
- Runtime contract: the method contract declares the Trader runtime class. Current supported values are
  `trader.indicators.Indicator` and `trader.signals.Signal`. The entrypoint must resolve to a subclass of the declared
  runtime contract; this reuses Trader package contracts instead of creating a parallel implementation schema.
- Source provenance contract: the implementation source file must have a module-level docstring with `Source reference`
  and `Implements` sections. The docstring must name the registry method, at least one approved method-card reference,
  implementation class, Trader runtime contract, implemented formula/algorithm/action rule, input ordering, warmup
  behavior, output ordering for series methods, and no-lookahead boundary. For generated quarantined implementations,
  the docstring must name the exact method-card IDs passed to the tool.
- Validation: method ID must exist in `math_registry`; approved method-card refs must match the method; source hash must
  match when supplied; provenance docstring checks must pass; imports and calls must pass the static safety allowlist;
  generated implementations must resolve from their artifact source path.
- Success data contains `method_implementation_manifest` with method ID, language, implementation kind, entrypoint,
  class name, source path, source hash, constructor kwargs, approved method-card refs, method contract,
  source provenance, `runtime_contract`, dependency allowlist, safety profile, and `status="registered"`.

`math_run_indicator_fixtures` contract:

- Request: either `implementation_id` for a persisted manifest or `implementation_manifest` inline; optional `fixtures`.
- The manifest must have `runtime_contract="trader.indicators.Indicator"`; signal manifests fail closed with
  `code="invalid_runtime_contract"`.
- Fixture inputs use ascending close values. The service builds latest-first `Bar` sequences, calls
  `Indicator.compute_series(bars)`, expands warmup nulls, compares expected values, and runs prefix checks for
  no-lookahead behavior.
- Before fixtures run, the service revalidates the manifest, approved method cards, source hash, entrypoint, and static
  safety checks.
- Success data contains an updated `method_implementation_manifest` with `status="validated"` and an
  `indicator_validation_report` with validation ID, implementation ID, method ID, entrypoint, source hash,
  fixture results, warnings, and blockers. Fixture mismatches return `ok=false` and leave the manifest blocked.

`math_run_signal_fixtures` contract:

- Request: either `implementation_id` for a persisted manifest or `implementation_manifest` inline; optional `fixtures`.
- The manifest must have `runtime_contract="trader.signals.Signal"`; indicator manifests fail closed with
  `code="invalid_runtime_contract"`.
- Fixture inputs use ascending close values. The service builds latest-first `Bar` sequences and calls
  `Signal.compute(bars) -> float`.
- Fixture payloads use `expected` for the scalar output and may use `expected_prefix` for no-lookahead/warmup checks.
  An `expected_prefix` value of `null` means the prefix should raise warmup `ValueError`; a numeric value must match the
  scalar output for that prefix.
- Before fixtures run, the service revalidates the manifest, approved method cards, source hash, entrypoint, static
  safety checks, runtime subclass, and provenance docstring.
- Success data contains an updated `method_implementation_manifest` with `status="validated"` and a
  `signal_implementation_validation_report` with validation ID, implementation ID, method ID, entrypoint, source hash,
  scalar fixture results, prefix results, warnings, and blockers. Fixture mismatches return `ok=false` and leave the
  manifest blocked.

`math_run_signal_diagnostics` contract:

- Request: `signal_observations`, `forward_return_labels`, `candidate_family_manifest`, `method_contracts`, optional
  `quantile_count`, and optional `data_quality_report`.
- `signal_observations` rows must include `candidate_id`, `signal_name`, `symbol`, `ts`, and finite numeric `value`.
  Optional `session`, `regime`, and `metadata` are explanatory context; raw indicator values are not the primary tested
  unit.
- `forward_return_labels` rows must include `symbol`, `ts`, positive integer `horizon`, and finite numeric
  `forward_return`. The service joins labels to observations by `symbol` and `ts`, then computes per-horizon results.
- `candidate_family_manifest` must include `candidate_family_id`, unique candidate IDs, and the tested grid. Candidate
  IDs referenced by observations or p-value rows must be declared before inference.
- Evidence: every horizon requires a `rank_ic` method contract with approved method-card evidence. If a candidate
  declares an implementation manifest or implementation ID, that manifest must be validated and must use
  `runtime_contract="trader.signals.Signal"`. Candidates without executable implementation evidence may run as
  observational diagnostics with warnings.
- Success data contains `signal_diagnostic_report` and an artifact reference. The report includes candidate count,
  tested grid, input counts, implementation refs, IC/rank IC, rank-IC p-values where sample size permits, hit rate,
  action-conditioned returns, coverage, turnover proxy, quantile buckets for continuous signals, monotonicity score,
  and symbol/session/regime breakdowns. Discrete `-1/0/+1` action signals skip quantile monotonicity and report an
  explanatory warning.
- Validation failures such as duplicate observation keys, missing labels for all observations, non-finite values,
  unknown candidates, missing rank-IC evidence, or invalid implementation manifests return `ok=false` with blockers
  embedded in the persisted report.

`math_run_multiple_testing_report` contract:

- Request: `candidate_family_manifest`, `metric_matrix`, `method_contract`, and optional `alpha`.
- `candidate_family_manifest` must include `candidate_family_id`, unique candidate IDs, candidate count implied by the
  declared IDs, and tested grid metadata.
- `metric_matrix` must contain exactly one p-value row per declared candidate. Rows must include `candidate_id` and
  finite `p_value` or `raw_p_value` in `[0, 1]`; optional `metric_name`, `metric_value`, and `horizon` are preserved in
  report rows.
- `method_contract.method_id` must be `benjamini_hochberg`, with approved method-card evidence. The first implemented
  multiple-testing method is Benjamini-Hochberg; Bonferroni, Holm, White Reality Check, Hansen SPA, Deflated Sharpe
  Ratio, and PBO remain follow-on methods.
- Success data contains `multiple_testing_report` and an artifact reference. The report includes raw p-values,
  adjusted p-values, rejection flags, accepted/rejected candidate IDs, correction method, alpha, candidate count,
  tested grid, warnings, and blockers.
- Validation failures such as missing candidate family metadata, duplicate candidate IDs, unknown metric candidates,
  duplicate metric rows, invalid p-values, missing candidate p-values, or missing method-card evidence return
  `ok=false` with blockers embedded in the persisted report.

`math_generate_python_method` contract:

- Request: `method_id`, non-empty `method_card_ids`, `method_contract`, and optional `fixtures`.
- MCP calls the configured provider-neutral LLM client and requires JSON with `class_name` and `source_code`.
- The generation prompt requires `source_code` to start with the same module-level provenance docstring enforced by
  `math_register_method_implementation`.
- Generated code is written only under `artifacts/research/method_implementations/quarantine/`; it is never written to
  `src/` or imported as a maintained package.
- Static safety checks reject filesystem access, network/process/SQL/broker imports, dynamic imports, `eval`, `exec`,
  `open`, global/nonlocal mutation, and dependencies outside the allowlist.
- Passing generated drafts immediately run through `math_register_method_implementation` and
  the fixture runner selected by `runtime_contract`: `math_run_indicator_fixtures` for Indicator methods and
  `math_run_signal_fixtures` for Signal methods. Success data reports the generated source path, registration result,
  fixture-validation result, and `status="validated"`; failures remain quarantined with `status="blocked"`.

`math_generate_cpp_kernel` contract:

- Request: either `implementation_id` for a persisted Python method implementation manifest or
  `implementation_manifest` inline; optional `template_id`.
- The Python manifest must have `status="validated"`, `runtime_contract="trader.indicators.Indicator"`, approved
  method-card refs, and an unchanged source hash. Signal manifests, unvalidated manifests, missing evidence, and
  unsupported methods fail closed.
- The first supported template is `sma_scalar_series_v1` for `method_id="sma"`. The tool renders only maintained
  templates under `trader_standard`; it does not accept arbitrary C++ source from callers or LLMs.
- Generated source is scanned for disallowed includes and unsafe call patterns, then written under the caller's
  artifact root with a `cxx_kernel_manifest`.
- Success data contains `cxx_kernel_manifest` with Python implementation provenance, method-card refs, method contract,
  template ID/hash, generated source path/hash, ABI metadata, warmup/NaN/alignment/dtype/no-lookahead policy, and safety
  policy. Unsupported or unsafe inputs return `ok=false` with blockers.

`math_compile_kernel` contract:

- Request: either `kernel_id` for a persisted C++ kernel manifest or `kernel_manifest` inline; optional `compiler` and
  `timeout_seconds`.
- Compilation verifies the generated source hash and safety scan before invoking a compiler. The compile command uses
  fixed safe flags, runs in an isolated artifact build directory, and captures stdout/stderr to a build log.
- Success data contains an updated `cxx_kernel_manifest` with compiler path/version, flags, command, build directory,
  binary path/hash/size, build log path, `status="compiled"`, and a compile-only benchmark summary.
- Missing compilers, tampered sources, disallowed source content, timeouts, or compiler failures return `ok=false` with
  an updated `status="compile_failed"` manifest and blockers. Contract-first C++ conformance/equivalence is deferred
  behind the method-package -> strategy -> backtest -> performance-report toolchain.

## LangGraph Use

Each LangGraph agent has its own identity, state schema, role policy, tool allowlist, and required output artifact.
Agents call MCP tools through an MCP client wrapper. They must not call platform internals directly when an MCP tool
exists.

Minimal allowlists:

| Agent | Allowed initial tools |
| --- | --- |
| Data Agent | `data_get_inventory`, `data_summarize_quality`, `data_ensure_loaded`, read-only health/config |
| Quant Research Supervisor Agent | Specialist artifact reads, supervisor handoff tools, `research_*` tools |
| Quantitative Methods Agent | `knowledge_*` retrieval/ingestion/citation tools, `math_list_method_contracts`, `math_validate_method_contract`, fixture, diagnostic, multiple-testing, method-packaging, and optional kernel tools |
| ML Agent | Planned 39A-39J `ml_*` lifecycle tools only; none are registered yet. |
| Hypothesis Agent | Ingredient artifact reads, `hypothesis_create_card` |
| Evaluation Agent | Data/backtest artifact reads, `evaluation_generate_performance_report`, later `evaluation_generate_report` |
| Adversarial Agent | Baseline artifact reads, `adversarial_run_robustness` |

LangGraph state may store artifact references, status, public messages, and structured decisions. It must not persist
hidden reasoning or raw LLM scratchpads as product records.
