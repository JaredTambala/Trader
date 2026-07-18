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

Only tools listed as registered in [mcp_tools.md](mcp_tools.md) and returned by `mcp_get_config` are callable. The
implementation/specification cutover is complete: strategy/risk candidates, candidate stacks, loose baseline/portfolio
backtest requests, filesystem run identities, and `evaluation_generate_performance_report` are not registered. Current
execution begins with content-addressed implementation versions and immutable specifications. Provider-neutral
parameter optimisation, explicit tracking projection, sealed-holdout Evaluation, and independent Adversarial audit are
registered. ML feature/training/model lifecycle tools and broader robustness remain planned.

Canonical loaders recompute content-addressed IDs and validation lineage at use time. Optimisation startup rechecks the
pinned base specification, implementation hashes, dataset/quality snapshots, objective source, and provider profile;
payload or configuration drift blocks before a trial executes.

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

Canonical MCP research artifact refs use `research://postgres/{artifact_type}/{artifact_id}`. New implementation,
specification, backtest, optimisation, Evaluation, and Adversarial services require the structured store and have no
filesystem authority or fallback.

## Side Effects

| Class | Meaning | Allowed examples |
| --- | --- | --- |
| `read_only` | Reads config, event-store data, local artifacts, or broker/operator snapshots without writing. | Inventory, data quality summary, result lookup. |
| `local_mutating` | Writes local artifacts or bounded research records; never submits broker orders. | Dataset manifest, quality report, sample load, backtest artifact, robustness report. |
| `external_research_mutating` | Mutates an approved external research service without broker or live-runtime mutation. | Explicit tracking projection now; later ML training/registry writes. |
| `broker_read` | Reads broker state through operator-owned surfaces. | Future read-only operator context tools. |
| `broker_mutating` | Mutates broker state. | Not allowed for research-agent MCP tools. |

External writes require a generic default-off gate plus a purpose-specific gate. Training execution and alias
promotion will require additional independent gates even though both use the external research mutation class.

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
| `ml_get_runtime`, `ml_health`, `ml_list_training_experiments` | ML Agent | planned configured MLflow training runtime/health metadata |
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
| `research_list_risk_manager_templates` | Quant Research Supervisor Agent | risk-manager template catalog |
| `research_register_strategy_implementation`, `research_validate_strategy_implementation` | Quant Research Supervisor Agent | strategy implementation version and validation report |
| `research_register_risk_manager_implementation`, `research_validate_risk_manager_implementation` | Quant Research Supervisor Agent | risk implementation version and validation report |
| `research_register_optimization_objective`, `research_validate_optimization_objective` | Quantitative Methods Agent | objective implementation version and validation report |
| `research_create_strategy_specification`, `research_validate_strategy_specification` | Quant Research Supervisor Agent | immutable strategy spec and validation |
| `research_create_risk_stack_specification`, `research_validate_risk_stack_specification` | Quant Research Supervisor Agent | immutable ordered risk spec and validation |
| `research_create_backtest_specification`, `research_validate_backtest_specification` | Quant Research Supervisor Agent | Data Agent-scoped canonical backtest spec and validation |
| `research_run_backtest_specification`, `research_get_backtest_results`, `research_compare_backtest_results` | Quant Research Supervisor Agent | canonical DB run and comparison refs |
| `research_get_optimizer_runtime`, `research_create_parameter_optimization_plan`, `research_run_parameter_optimization`, `research_get_parameter_optimization_results` | Quant Research Supervisor Agent | engine health and canonical plan/run/trial ledger |
| `research_run_parameter_optimization_variants` | Quant Research Supervisor Agent | Adversarial-requested immutable child runs |
| `research_project_experiment_tracking` | Quant Research Supervisor Agent | non-authoritative tracking projection report |
| `research_create_walk_forward_plan`, `research_run_walk_forward_optimization`, `research_get_walk_forward_results` | Quant Research Supervisor Agent | deferred walk-forward plan/run/result artifacts |
| `evaluation_generate_parameter_optimization_report` | Evaluation Agent | sealed untouched-holdout Evaluation report |
| `evaluation_generate_walk_forward_report` | Evaluation Agent | deferred stitched out-of-sample walk-forward Evaluation report |
| `evaluation_generate_report` | Evaluation Agent | later skeptical critique report |
| `adversarial_create_parameter_optimization_audit_plan`, `adversarial_generate_parameter_optimization_audit` | Adversarial Agent | immutable attack plan and robustness report |
| `adversarial_run_robustness` | Adversarial Agent | planned broader `robustness_report.json` |
| `adversarial_audit_walk_forward` | Adversarial Agent | deferred walk-forward robustness report |
| `research_analyze_return_attribution` | Quant Research Supervisor Agent | attribution report |
| `research_generate_recommendation` | Quant Research Supervisor Agent | recommendation report |

## Canonical Implementation, Specification, And Optimisation Contracts

Implementation registration accepts `name`, `version`, complete `source_code`, `factory_name`, optional `class_name`, a
bounded parameter schema, dependency declarations, authoring origin, capabilities, resource/runtime requirements,
optional generic provenance refs, and metadata. IDs are content-addressed over normalized identity and source hash.
Validation accepts exactly one implementation ID, URI, or inline payload and writes an
`implementation_validation_report` after import/call safety checks, kind-specific interface construction, parameter
validation, and a deterministic fixture. Strategy/risk implementations are Supervisor-owned; optimisation objectives
are Quantitative Methods-owned. Method cards and packages are not eligibility requirements.

`research_create_strategy_specification` consumes one passed strategy implementation validation and explicit
parameters, sizing, portfolio mode, runtime context, assumptions, tunable-field declarations, and optional provenance.
Symbols, dates, timeframe, source, and live/broker/raw-SQL permissions are forbidden. The validation tool resolves the
exact source hash again. Risk-stack creation similarly consumes an ordered non-empty array of passed risk implementation
validations with explicit parameters and tunable fields, then revalidates order and every source hash.

`research_create_backtest_specification` consumes a passed strategy-spec validation, optional passed risk-stack
validation, exactly one complete Data Agent manifest, matching complete quality report, costs/assumptions, initial
cash/positions, benchmark, deterministic seed, run/logging limits, and optional immutable parent/selection/variant
lineage. It embeds and hashes the normalized Data/quality payloads. The validator re-resolves all upstream validations
and fails on hash or scope drift. Loose scope and filesystem refs are not accepted.

`research_run_backtest_specification` accepts only a passed backtest-spec validation ref and requires
`TRADER_MCP_ALLOW_BACKTESTS=true`. It chooses no-risk or ordered-risk execution from the specification and writes one
canonical `backtest_run` containing summary metrics, complete result, curves, trades, positions, symbol metrics,
exposure, risk decisions/breaches/measures, warnings, blockers, and full implementation/specification/dataset lineage.
`research_get_backtest_results` accepts exactly one run ID or DB URI. Comparison accepts 2-50 canonical run refs plus a
numeric ranking metric/order. No new execution service reads or returns a durable filesystem path.

An optimisation plan consumes a passed selection-region backtest-spec validation, a sealed chronological holdout Data
Agent manifest and matching quality report, one passed `optimization_objective` validation, direction, typed finite
search dimensions, constraints, seed, trial budget, and bounded sequential resource limits. Every dimension path must be
explicitly declared tunable by the owning strategy/risk spec. Costs, datasets, implementations, provider settings,
holdout/fold boundaries, and undeclared fields are rejected.

The objective receives only this closed object:

```json
{
  "schema_version": "1.0",
  "status": "passed",
  "metrics": {},
  "counts": {},
  "costs": {},
  "exposure": {},
  "risk": {},
  "quality": {},
  "constraints": {},
  "lineage": {}
}
```

Unknown top-level fields, non-scalar metrics/costs, invalid counts, unsupported runtime imports/calls, and unavailable
objective metrics block. An engine receives only search dimensions, seed, prior canonical trial outcomes, direction,
and budget. A run pins engine profile/version/configuration digest/capabilities, seed, and executor kind. It never changes
engine in place. Each canonical trial stores the suggestion, retry attempts, exceptions, child specs/runs, closed
observation, constraints, objective result, diagnostics, warnings, and blockers. Selection is deterministic and remains
exploratory.

`builtin_grid` and `builtin_random` are always available without Optuna or MLflow. `optuna_tpe` is lazy and requires its
dedicated configured non-public schema/role plus both external-write and Optuna-write gates. Provider loss blocks or
leaves a run partial; `research_get_parameter_optimization_results` reads canonical Trader evidence without the provider.

`research_project_experiment_tracking` accepts only a supported canonical run ref and configured profile. It derives
all metrics/tags, calls the sink at most once per canonical digest/profile, and writes an idempotent
`experiment_tracking_projection_report` with `authoritative=false`. It accepts no arbitrary metrics, tags, URI, or
credentials. The generic external-write and experiment-tracking-write gates are both required.

Evaluation accepts an optimisation run and a matching sealed-holdout `backtest_run`. It verifies completed selection,
holdout dataset hash, selected strategy specification, selection lineage, and required risk telemetry before writing its
own report. Adversarial plan creation freezes a baseline digest and declared attacks. The Supervisor executes immutable
requested optimisation variants; cost/window stresses use immutable child backtest specs. Adversarial judgment consumes
those refs, cannot rewrite the baseline/selection, and blocks missing required evidence or observed instability.

## Method Package Artifacts

`math_package_method_artifact` packages a validated Python implementation for optional implementation producers. It is
local-mutating and writes `method_package_manifest.json`; it does not register an executable strategy.

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

## Maintained Implementation Template Catalog

`research_list_strategy_templates` and `research_list_risk_manager_templates` are read-only discovery tools over the maintained implementation catalog in `trader_research.implementations`. Each row exposes a stable template ID, implementation kind, runtime contract, real `trader_standard` entrypoint, typed parameter metadata, required runtime context, and concise behavior metadata. Strategy rows also declare portfolio mode.

Catalog rows are informational producer metadata. They are not implementation versions, executable specifications, validation evidence, or permission to run code. They do not contain method-card requirements, candidate validation requirements, source generators, dataset scope, filesystem paths, or mutable provider identity. To execute a maintained implementation, a producer submits its source through the same content-addressed implementation registration and validation contract used by handwritten and externally produced code.

The candidate-era Python packages, domain models, filesystem bundle readers, and performance-report service have been deleted. Their MCP names and artifact types are unsupported. No compatibility alias, filesystem fallback, migration reader, or automatic translation from candidate IDs exists.

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
- Approved rich cards may be retained as optional provenance by an external implementation producer. The resulting
  source receives no special eligibility: it must pass the same content-addressed implementation registration,
  validation, and specification contracts as handwritten or maintained source. Numeric behavior is never inferred from
  prose at execution time.
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
| Evaluation Agent | Canonical backtest reads, `evaluation_generate_parameter_optimization_report`, later broader reports |
| Adversarial Agent | Canonical plan/run reads and registered parameter-optimisation audit tools |

LangGraph state may store artifact references, status, public messages, and structured decisions. It must not persist
hidden reasoning or raw LLM scratchpads as product records.
