# Research MCP Operations

This document covers local operation for the research MCP server and related verification commands.

## Maintenance Posture

Knowledge-base creation, retrieval, bounded methodology extraction, and Data Agent tools remain supported operational
surfaces. Current work is not expanding semantic extraction beyond the 33AB baseline. Operational changes in these
areas should be limited to data integrity, citation correctness, security, dependency maintenance, and regression fixes
unless the tracker explicitly reactivates composite methodology work.

The implementation-to-evidence, provider-neutral parameter-optimisation, and ML deployment/runtime tools are now
registered. ML feature/training/evaluation/registry/monitoring and broader robustness work remain planned. Use
`mcp_get_config` for exact runtime gates and provider health.

## Start The Server

The MCP server uses stdio:

```bash
uv run python -m trader_mcp.server
```

For an MCP client, configure:

```text
command: uv
args: ["run", "python", "-m", "trader_mcp.server"]
cwd: /home/jared/Trader
```

The server should start and list tools without a valid database, broker credential, trader runtime YAML, or LLM
configuration. Runtime failures belong inside the affected tool envelope.

## Environment Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `TRADER_MCP_TRANSPORT` | `stdio` | MCP transport. Only stdio is supported. |
| `TRADER_MCP_ARTIFACT_ROOT` | `artifacts/research` | Legacy/export root; not canonical for new execution artifacts. |
| `TRADER_MCP_TRADER_CONFIG_PATH` | empty | Optional trader YAML for execution-plane dependencies and the Postgres research artifact store. |
| `TRADER_MCP_TOOL_ENV_PATH` | `.env` | Optional dotenv file loaded lazily for trader YAML expansion. |
| `TRADER_MCP_ALLOW_DATA_LOADING` | `false` | Enables explicit sample/backfill mutation. |
| `TRADER_MCP_ALLOW_BACKTESTS` | `false` | Enables canonical backtest-specification execution. |
| `TRADER_MCP_ALLOW_OPTIMIZATION` | `false` | Additionally enables generic parameter-optimisation execution. |
| `TRADER_MCP_ALLOW_EXTERNAL_RESEARCH_WRITES` | `false` | Master gate for approved external research-service writes. |
| `TRADER_MCP_ALLOW_OPTUNA_WRITES` | `false` | Enables configured Optuna sampler-state writes when the master gate is also true. |
| `TRADER_OPTUNA_STORAGE_URL` | empty | Dedicated Optuna PostgreSQL URL; its username must match the configured role. |
| `TRADER_OPTUNA_SCHEMA` | `trader_optuna` | Dedicated non-`public` Optuna schema. |
| `TRADER_OPTUNA_ROLE` | `trader_optuna_writer` | Dedicated Optuna writer role. |
| `TRADER_OPTUNA_STUDY_PREFIX` | `trader` | Namespace for adapter-owned study names. |
| `TRADER_MCP_ALLOW_EXPERIMENT_TRACKING_WRITES` | `false` | Enables configured analytical tracking projections with the master gate. |
| `MLFLOW_TRACKING_URI` | empty | Configured optional MLflow sink/training tracking authority; never request-supplied. |
| `TRADER_MLFLOW_OPTIMIZATION_EXPERIMENT` | `trader-backtest-optimization` | Disposable analytical projection namespace. |
| `TRADER_MCP_ALLOW_ML_RUNTIME` | `false` | Enables deployment parity model loading and model-backed backtest inference. |
| `TRADER_MCP_ALLOW_CODING_WORKSPACE` | `false` | Enables isolated Strategy Engineering workspace creation, candidate writes, checks, packaging, and cleanup. |
| `TRADER_MCP_CODING_WORKSPACE_ROOT` | empty | Dedicated writable root for ephemeral candidate workspaces. Must not be the repository root. |
| `TRADER_MCP_CODING_REPOSITORY_ROOT` | empty | Read-only Trader repository snapshot exposed to the coding service. |
| `TRADER_MCP_CODING_REPOSITORY_REVISION` | empty | Exact pinned repository revision used by every workspace. |
| `TRADER_MCP_CODING_CONTAINER_IMAGE` | empty | Exact admitted image used for isolated checks, required as `repository@sha256:<64 hex>`; tags and shortened digests fail closed. |
| `TRADER_AGENTS_CHECKPOINT_DSN` | empty | Dedicated PostgreSQL DSN for replaceable LangGraph operational checkpoints. |
| `TRADER_AGENTS_MODEL_PROFILE_ID` | `ollama-qwen35-9b-json-v1` | Exact admitted model profile. The first slice currently registers only its development Ollama profile. |
| `TRADER_AGENTS_MCP_COMMAND` | current Python executable | Command used to start each isolated MCP stdio server. |
| `TRADER_AGENTS_MCP_ARGS` | `-m trader_mcp.server` | Arguments for each MCP stdio server. |
| `TRADER_AGENTS_MCP_CWD` | current directory | Working directory for MCP server processes. |
| `TRADER_AGENTS_MCP_TIMEOUT_SECONDS` | `180` | Per-call MCP transport timeout. |
| `TRADER_AGENTS_MLFLOW_TRACKING_URI` | empty | Optional MLflow tracking URI for redacted agent traces; no trace sink is used when empty. |
| `TRADER_AGENTS_MLFLOW_EXPERIMENT` | `trader-agentic-research` | MLflow experiment for agent trace correlation. |
| `TRADER_MLFLOW_INFERENCE_PROFILE` | `mlflow_local_pyfunc` | Names the configured immutable local-pyfunc adapter profile. |
| `TRADER_MCP_ALLOW_BROKER_MUTATION` | `false` | Must remain false for research MCP tools. |
| `TRADER_MCP_ALLOW_RAW_SQL` | `false` | Must remain false for research MCP tools. |

Provision the Optuna role/schema outside MCP with least privilege, set that role as the URL username, and grant it only
the dedicated schema. Trader's normal application role should not use that schema. `mcp_get_config` reports only whether
the profile is configured; `research_get_optimizer_runtime` reports package/config availability without connecting or
creating a study. Built-in grid/random remain available when the URL or Optuna package is absent.

## Agentic Runtime Operations (Unqualified)

The `trader-agent` command operates the implemented Coordinator–Data–Strategy slice. It is available for development
and qualification; it is not yet a controlled production capability.

First inspect the exact credential-free runtime identities:

```bash
uv run trader-agent manifest
```

Create a JSON serialization of one immutable `ResearchSession` using the exact model-profile, agent-program, and
tool-catalogue identities from that manifest. The session must also contain a complete composite Data scope, Strategy
build-contract inputs, approvals, budgets, operator identity, and success definition. Validate it without opening
Postgres, a model, or MCP subprocesses:

```bash
uv run trader-agent validate-session --session /absolute/path/to/session.json
```

For execution, configure the canonical research store/MCP environment, a dedicated checkpoint database, and the
admitted Ollama model. The first run may apply the idempotent LangGraph checkpoint schema explicitly:

```bash
export TRADER_AGENTS_CHECKPOINT_DSN='postgresql://checkpoint_role:...@localhost:5432/trader_checkpoints'
uv run trader-agent run --session /absolute/path/to/session.json --setup-checkpoint-schema
```

`run` starts three persistent stdio MCP sessions so Coordinator, Data, and Strategy transport state is isolated. It
either prints a grounded `AgenticSliceResult` or an `OperatorInterrupt`. A later invocation with the exact same session
identity recovers the existing checkpoint instead of creating a second research lineage. Inspect only the redacted
public projection with:

```bash
uv run trader-agent inspect --session /absolute/path/to/session.json
```

Resume an interrupt using the same session and exact operator identity:

```bash
uv run trader-agent resume \
  --session /absolute/path/to/session.json \
  --approved true \
  --answer 'Bounded public operator response' \
  --operator-id operator-name
```

Cancel a checkpointed non-terminal session using the owning operator identity and a bounded public reason:

```bash
uv run trader-agent cancel \
  --session /absolute/path/to/session.json \
  --reason 'Operator stopped this investigation.' \
  --operator-id operator-name
```

Cancellation writes an append-only canonical `cancelled` decision receipt and a terminal checkpoint result. Repeating
the same command returns that terminal result. In one runtime process, cancellation first stops the active session
task; across processes it takes effect from the latest completed checkpoint, so mutation-specific operation journals
remain the authority for reconciling work interrupted between checkpoints. It cannot cancel a different operator's
session or replace an already terminal conclusion.

Use `--setup-checkpoint-schema` on `resume`, `cancel`, or `inspect` only when an operator is deliberately provisioning a fresh
checkpoint database. Do not use the research artifact-store DSN as an implicit fallback. Checkpoints can be expired
after terminal evidence is confirmed because they are operational state, not research authority.

Exact reuse can operate with read-only implementation-catalogue and admission evidence. New authorship additionally
requires the default-off Coding Workspace gate and every pinned workspace variable above. Data loading likewise
requires its separate gate plus approval inside the immutable session. The Coordinator cannot widen either envelope.

### MLflow Runtime Boundary

The current MLflow integration supports explicit non-authoritative optimisation projection and a separate lazy local
pyfunc inference adapter. The adapter is registered only when `MLFLOW_TRACKING_URI` is configured; the MCP server still
starts when MLflow/pandas are absent. `ml_create_deployment_manifest` is DB-only. `ml_validate_deployment` and
model-backed backtests require `TRADER_MCP_ALLOW_ML_RUNTIME=true`, load only a pinned model URI, and never write to
MLflow. Tasks 39A-G/J add authoritative training/registry/monitoring behavior. The operational contract is:

- one configured tracking URI and registry URI, with callers unable to override them per tool request
- authentication through environment/secret references that are never persisted in artifacts or tool envelopes
- a database-backed MLflow backend store and configured artifact store suitable for Model Registry use
- tracking-server identity and client/server version checks exposed through read-only health/config tools
- namespaced experiment and registered-model policies so runs cannot be reconciled from an unrelated authority
- independent default-off gates for MLflow writes, model fitting, and model-alias mutation
- resource, timeout, dependency, and artifact-size bounds for training and evaluation execution
- no live deployment mutation through MCP; deployment tools create and validate backtest/paper manifests only

Future training/registry controls add `TRADER_MCP_ALLOW_MLFLOW_WRITES`, `TRADER_MCP_ALLOW_ML_TRAINING`, and
`TRADER_MCP_ALLOW_MODEL_ALIAS_MUTATION`; these remain roadmap contracts. Generic projection already uses the master
external-write and experiment-tracking-write gates.

The MLflow artifact store remains the model-binary authority. Trader Postgres stores reconciled MLflow IDs/URIs,
digests, signatures, source/data/environment hashes, and validation/promotion/deployment lineage. It does not duplicate
model binaries into generic research artifact payloads.

Deployment and validation rows are visible in `research_ml_deployments` and
`research_ml_deployment_validations`; canonical payloads remain in `research_artifacts`. Runtime raw-output evidence is
written to `prediction_events`, mapped strategy inputs to `signal_events`, and prediction lineage to
`order_events.decision_evidence`. The local adapter qualification command is:

```bash
uv run --extra ml pytest tests/test_mlflow_inference_adapter.py -q
```

Quantitative Methods knowledge tools expect a configured knowledge store for production use. Postgres-backed knowledge
storage is the normal runtime path; tests may inject isolated in-memory stores.

Full-document ingestion stages embedding generation before replacing active evidence. A successful Postgres run
publishes replacement evidence units, vectors, the embedding manifest, and the ingestion report in one transaction. If
embedding or publication fails, the prior active generation remains available; investigate the blocked run before
retrying with `force=true`. Providers that expose ordered batch embedding are called in bounded 16-text batches; each
response must match the requested count and indexes before publication. Single-text providers retain the same atomic
path through a deterministic fallback.

`knowledge_assemble_methodology_evidence` and `knowledge_create_method_card_draft` require both the knowledge store
and the research artifact store. Evidence assembly loads a methodology candidate, applies the family evidence profile,
and writes a role-labeled `methodology_evidence_packet` research artifact. Draft creation loads a passed
methodology-candidate validation report from structured research artifacts, revalidates source/chunk evidence in the
knowledge store, and writes the complete method-card draft back through the knowledge-store method-card path. The
free-form summary draft contract and the second rich-card tool no longer exist.

## Methodology Operating Checklist

For source-to-method work, verify these conditions before expecting strategy evidence:

- Registering a source is only a reference step. Run full-document ingestion and check ingestion status before using
  retrieval or source-scoped methodology discovery.
- Use source IDs for exhaustive discovery over a known book or paper, and use retrieval queries for semantic search
  across the indexed knowledge base.
- Dereference evidence chunks when reviewing a candidate. Chunk IDs, locators, text hashes, and exact claim-span
  offsets/hashes are the audit trail; do not treat retrieval excerpts as the canonical source record or assign one
  method exclusive ownership of a chunk.
- Assemble role-labeled evidence before expecting rich extraction quality. The packet records found and missing family
  roles and explains whether the source supports descriptive, implementation, signal, strategy, or risk readiness.
- Treat null rich fields as expected when the source does not support them. Do not fill missing parameters, thresholds,
  or assumptions from memory.
- A blocked methodology validation report should be fixed at the source/evidence level: ingest the correct source,
  discover a wider candidate span, or accept that the method is not sufficiently evidenced.
- Publish rich drafts only after reviewer approval. Draft cards are review artifacts and should not be used as approved
  method evidence.
- When an external producer derives strategy/risk code from a rich card, retain the card ref as optional provenance and
  submit the resulting source through normal implementation registration/validation. Cards are not execution inputs.

MCP research artifact persistence is DB-first. Implementation, specification, canonical backtest, optimisation,
tracking-report, Evaluation, and Adversarial tools require `ResearchArtifactStore` and return
`research://postgres/{artifact_type}/{artifact_id}` refs. They fail closed without it and never create canonical
filesystem artifacts. Typed projection tables expose stable IDs/status/lineage in pgAdmin while `research_artifacts`
JSONB remains canonical. Optuna uses its separately provisioned schema/role only for sampler state; Trader does not query
it for evidence. MLflow projections are disposable and never dual-write canonical state.

The 56D/57C/57K-R cutover has no data migration or compatibility reader. A database containing candidate-era research
tables or artifacts is unsupported and must be recreated or reset as a clean database before use. Schema initialization
then creates only canonical implementation, specification, backtest, optimisation, tracking, Evaluation, and
Adversarial projections. Do not translate old rows, synthesize new refs from candidate IDs, or selectively preserve
candidate-era research data.

## Frozen Deterministic Verification Procedure

This section documents the accepted deterministic orchestration freeze. The control-plane code and named tests below
exist at `verification-orchestration-v1-freeze`, not on the clean agentic-build branch. Its acceptance evidence must not
be cited as qualification for the model-backed runtime.

The 57I-57S baseline summarized in [product_state.md](product_state.md) is the release-qualification procedure
for the implementation/specification/backtest/optimisation cutover. Run them in order. Use one frozen Git
revision. Record the exact revision, dependency lock hash, credential-free environment/profile digests, commands,
results, evidence refs, and database fingerprints. A code, schema, fixture, lockfile, or policy change invalidates its
phase and every downstream phase that consumed it.

Use separate acceptance profiles:

- **Core:** static, type, contract, non-Postgres, realistic fixture, built-in grid/random, and security tests. Mandatory.
- **Trader Postgres:** canonical MCP graph, projection reconciliation, restart/resume, isolation, and bounded scale.
  Mandatory.
- **Optuna:** dedicated-schema integration, reconciliation, provider loss, and resume. Required before enabling
  `optuna_tpe`, but not for built-in-engine acceptance.
- **Tracking sink:** idempotent derived projection and external deletion/unavailability behavior. Qualify each sink
  independently before enabling its writes.

Before a Postgres phase, capture stable counts/fingerprints for the operator runtime, research, and knowledge tables.
Run verification only against an explicit `PG_TEST_DB` ending `_test` or `_testing`, then compare the operator
fingerprints again. A missing suffix, legacy-variable fallback, unexpected operator change, unexplained dirty file,
undeclared skip, or provider write outside its isolated namespace is a stop condition, not a warning.
Any fallback to `PG_DB` is specifically forbidden.

### Isolated Postgres Runtime

The controlled harness accepts four connection profiles for the historical optimisation campaign and a fifth,
checkpoint-only profile for orchestration qualification. It never derives test credentials from `.env` operator
names:

| Profile | Variables | Authority |
|---|---|---|
| Provisioning admin | `PG_ADMIN_HOST`, `PG_ADMIN_PORT`, `PG_ADMIN_DB`, `PG_ADMIN_USER`, `PG_ADMIN_PASSWORD` | Creates only the named verification roles/database and the `vector` extension. |
| Operator fingerprint | `PG_OPERATOR_HOST`, `PG_OPERATOR_PORT`, `PG_OPERATOR_DB`, `PG_OPERATOR_USER`, `PG_OPERATOR_PASSWORD` | Opens an explicit read-only, repeatable-read transaction; never writes verification evidence here. |
| Trader verification | `PG_TEST_HOST`, `PG_TEST_PORT`, `PG_TEST_DB`, `PG_TEST_USER`, `PG_TEST_PASSWORD` | Owns the disposable `*_test` database and product test schemas. |
| Optuna verification | `PG_OPTUNA_TEST_HOST`, `PG_OPTUNA_TEST_PORT`, `PG_OPTUNA_TEST_DB`, `PG_OPTUNA_TEST_USER`, `PG_OPTUNA_TEST_PASSWORD` | Targets the same test database and owns only `TRADER_OPTUNA_SCHEMA`. |
| Orchestration checkpoints | `PG_CHECKPOINT_TEST_HOST`, `PG_CHECKPOINT_TEST_PORT`, `PG_CHECKPOINT_TEST_DB`, `PG_CHECKPOINT_TEST_USER`, `PG_CHECKPOINT_TEST_PASSWORD` | Required only by `controlled_orchestration_v1`; targets the test database and owns only `TRADER_CHECKPOINT_SCHEMA`. It cannot mutate canonical runtime or research tables. |

Set `PG_TEST_LOCALE` to a locale installed by the Postgres server. Provisioning creates the database from `template0`
with UTF-8 encoding and pins both `LC_COLLATE` and `LC_CTYPE` to that value. Set `TZ=UTC`, `PYTHONHASHSEED=0`, and
`TRADER_VERIFICATION_MODE=true`. Use a distinct non-superuser for each test writer and a disposable
`TRADER_OPTUNA_STUDY_PREFIX` and `TRADER_MLFLOW_OPTIMIZATION_EXPERIMENT` tied to the frozen revision.

Keep every mutation gate false while provisioning 57J:

```bash
export TRADER_MCP_ALLOW_BROKER_MUTATION=false
export TRADER_MCP_ALLOW_RAW_SQL=false
export TRADER_MCP_ALLOW_DATA_LOADING=false
export TRADER_MCP_ALLOW_BACKTESTS=false
export TRADER_MCP_ALLOW_OPTIMIZATION=false
export TRADER_MCP_ALLOW_EXTERNAL_RESEARCH_WRITES=false
export TRADER_MCP_ALLOW_OPTUNA_WRITES=false
export TRADER_MCP_ALLOW_EXPERIMENT_TRACKING_WRITES=false
```

With a clean worktree whose product paths are byte-identical to `verification-57i-freeze-v6`, execute:

```bash
uv run python -m tests.support.postgres_verification provision --reset
uv run python -m tests.support.postgres_verification begin --phase 57J
uv run pytest tests/test_postgres_verification_runtime.py -m postgres -q
uv run python -m tests.support.postgres_verification end --phase 57J --outcome passed
```

`provision --reset` terminates sessions and drops only the validated `PG_TEST_DB`; it cannot accept the operator
database name or an unsafe suffix. The fixture guard verifies the live database, role, UTC setting, pinned locale, and
`verification_control.runtime_marker` before constructing a store and again immediately before each `TRUNCATE`.
`begin` stores a credential-free runtime manifest, the executed harness revision, and the operator `before` fingerprint
in `verification_control.operator_fingerprints`.
`end` requires an explicit `--outcome passed|blocked`; blocked outcomes require one or more `--blocker` values. The
phase row records `isolation_status`, `qualification_status`, blockers, the executed harness revision, and the verdict
revision independently. An operator fingerprint or harness mismatch always blocks both isolation and qualification,
even when the caller supplied `--outcome passed`. The control schema is disposable and is recreated by
`provision --reset`; it has no migration path from the first verification schema. Product rows, source text, vectors,
artifact payloads, passwords, and external provider state are not copied into verification evidence.

The mandatory acceptance graph is not the existing in-memory empty-strategy smoke test. It must use
`PostgresResearchArtifactStore`, call public MCP tools throughout, and produce real multi-asset orders, exposure, costs,
risk approvals and rejections, parameter-sensitive trial results, disjoint selection/holdout hashes, immutable
selection, untouched-holdout Evaluation, Supervisor-executed variants, and an independent Adversarial report. Every
durable ref must use `research://postgres/...`; canonical JSONB and typed pgAdmin projections must reconcile; no
canonical filesystem path may be present.

### 57L Postgres-Only Fixture Qualification

57L qualifies the canonical execution core before the public MCP graph is attempted. It deliberately calls direct
research services with `PostgresEventStore` and `PostgresResearchArtifactStore`; it does not use DuckDB, an in-memory
artifact store, Optuna, MLflow, or filesystem artifact authority. This phase proves product behavior below the MCP
transport boundary. 57M separately proves MCP registration, gates, envelopes, Evaluation, and Adversarial composition.

The versioned fixture in `tests/support/realistic_optimization_fixture.py` contains three symbols, 48 hourly selection
bars per symbol, and 32 hourly holdout bars per symbol. A 25-hour gap makes the regions chronologically disjoint and
larger than the maximum five-bar lookback. Fixed timestamps, prices, fee/slippage assumptions, seed, source-code
digests, bar-content digests, Data Agent manifest/quality digests, and grid order make drift observable. The manifest
retains `source_filter=null` because canonical backtest specifications reject source-filtered manifests; the exact
fixture source remains covered by the canonical bar-content digest and isolated database precondition.

The Postgres qualification must prove all of the following in one test:

1. Data Agent inventory and quality evidence exactly match the locked selection and holdout snapshots.
2. Handwritten strategy, risk-manager, and objective implementations register and pass validation from persisted refs.
3. Canonical strategy, ordered risk-stack, and selection backtest specifications pass validation and produce a real
   portfolio run with buys and sells, at least two traded symbols, nonzero fees/slippage/exposure, and both risk
   approvals and quantity-limit rejections.
4. Built-in grid search executes lookbacks 2, 3, 4, and 5 as four canonical child backtests with distinct trade counts,
   returns, and objective values, then persists one deterministic selected trial and its child refs.
5. No holdout backtest exists before selection. The selected behavior is rebound to the disjoint holdout manifest only
   after selection, and the resulting run retains `selection_origin_ref` without changing the selected optimisation.
6. Canonical JSONB and representative typed projections reconcile for the optimisation run, every trial, and the
   holdout backtest. The selection and holdout bar-content digests are unchanged after execution.

Run it inside the controlled phase boundary with all Postgres verification variables set explicitly:

```bash
uv run python -m tests.support.postgres_verification begin --phase 57L
uv run pytest tests/test_postgres_realistic_optimization_fixture.py -m postgres -q -W error
uv run python -m tests.support.postgres_verification end --phase 57L --outcome passed
```

The test fixtures destructively clean runtime and research rows in the verification database before and after the test.
The durable controlled-execution verdict remains in `verification_control.phase_runs`; no rows are copied into the
operator database.

### 57M Stdio MCP Evidence Graph

57M runs `tests/test_postgres_optimization_evidence_graph.py` through an actual MCP `ClientSession` over stdio. The
child server uses only `PostgresEventStore` and `PostgresResearchArtifactStore` connected to the guarded verification
database. Direct services are not substitutes for graph calls. Test setup may seed the locked 57L bars, and test
assertions may read Postgres for reconciliation, but all product artifacts are created through public MCP tools.

The phase requires exactly `TRADER_MCP_ALLOW_BACKTESTS=true` and `TRADER_MCP_ALLOW_OPTIMIZATION=true`. Broker mutation,
raw SQL, data loading, external research writes, Optuna writes, and experiment-tracking writes remain false. The phase
manifest records and rechecks this exact policy profile at `end`; configuration drift blocks qualification.

The graph obtains selection and holdout inventory/quality evidence from Data Agent MCP tools, registers and validates
the handwritten strategy, risk manager, and closed objective, creates immutable specifications, runs the selection
backtest and four-trial built-in grid, executes the selected holdout specification, obtains a passed Evaluation report,
and asks Adversarial to plan `seed_sensitivity` plus `multiple_testing`. The current Supervisor-allowlisted Experiment
service executes the declared seed variant; Robustness judges the supplied canonical evidence. Optuna and MLflow are not
used.

Ordinary Postgres tests still clean their rows. Controlled 57M and 57N commands may set their matching
`TRADER_VERIFICATION_RETAIN_PHASE`; any other phase value fails closed. This leaves the resulting bars and research
artifacts in `trader_verification_test` after pytest exits so they can be inspected in pgAdmin. The retained phase is
part of the credential-free runtime manifest and must match both `begin` and `end`. A later destructive phase may
explicitly replace these disposable verification rows; they are never copied to the operator database.

The governance authority redesign is a hard schema cutover. Startup fails with
`legacy research_artifacts schema detected` when the canonical table still has `agent_owner`; there is no compatibility
reader or data migration. For a disposable development or
verification database, explicitly clear all research projections and drop only the legacy canonical table before
starting the new code:

```sql
DO $$
DECLARE
    target RECORD;
BEGIN
    FOR target IN
        SELECT schemaname, tablename
        FROM pg_tables
        WHERE schemaname = 'public'
          AND tablename LIKE 'research_%'
    LOOP
        EXECUTE format(
            'TRUNCATE TABLE %I.%I CASCADE',
            target.schemaname,
            target.tablename
        );
    END LOOP;
END
$$;

DROP TABLE IF EXISTS public.research_artifacts;
```

The next `PostgresResearchArtifactStore` startup recreates `research_artifacts` with the current authority columns. Do
not run this destructive reset against a database whose research evidence must be retained.

### Declaration Contract Operational Impact

The declaration-contract delivery was contract-only. It added canonical authority declarations for
`research_objective`, `experiment_protocol`, `workflow_plan`, `approval_request` and `workflow_outcome`, but no
persistence or execution. The current service layer additionally persists immutable
`experiment_protocol_proposal` evidence before approval; workflow persistence services and the executor supply the
remaining explicit boundaries described below.

The contracts can be imported and round-tripped as JSON for design and test work. Existing direct MCP procedures may
still persist null `requested_by`/`actor` values. A workflow plan or step result supplied as arbitrary JSON is not
evidence merely because it satisfies the dataclass schema.

### Workflow Checkpoint Operations

The checkpoint layer adds replaceable Postgres-backed LangGraph operational state, not a canonical research artifact
writer. Set a dedicated connection string explicitly:

```bash
export TRADER_AGENTS_CHECKPOINT_DSN='postgresql://checkpoint_role:...@localhost:5432/trader'
```

Run `open_postgres_checkpointer(setup=True)` once under an operator-controlled setup path to apply the maintained
checkpointer's idempotent schema. Normal runtime opens it without `setup=True`. The configuration summary reports only
whether Postgres persistence is configured; it never exposes the DSN or credentials. There is no fallback to
`TRADER_RESEARCH_ARTIFACT_STORE_DSN`, filesystem artifacts or in-memory state.

LangGraph owns its checkpoint migrations, checkpoints, blobs and pending-write tables. These tables record node
position, bounded retry/result summaries and canonical refs so a workflow thread can resume after a process or
connection interruption. They are not included in Trader research projections, do not establish a research claim and
may be expired or deleted according to an operational retention policy after terminal workflow evidence is confirmed.
Do not grant the checkpoint role broker/runtime mutation privileges.

The resume shell does not register MCP tools, execute capabilities or create `workflow_outcome` artifacts. A successful
resume test proves checkpoint continuity and idempotency only.

### Resumable Research Composition

Use `run_research_composition` when the caller has an approved objective and explicit specialist tasks but wants one
bounded entrypoint to connect specialist evidence to the fixed workflow. The request identity, objective and tasks are
immutable for the life of the composition thread. Callers must build Data and Experiment Design tasks with their
responsibility-owned builders rather than passing symbols, dates, costs or runtime choices as loose graph state.

The default route catalog contains Data and Experiment Design. A Design task must reference Data evidence that already
exists when the immutable composition request is built; composition does not rewrite later tasks from earlier outputs.
It resolves each accepted handoff in the same canonical store used by MCP. The Design route calls
`research_create_experiment_protocol_proposal`, validates its proposed-only envelope and reloads the canonical
proposal. Missing local-mutation permission returns a typed prerequisite. Exact resume does not repeat the proposal
mutation.

After the proposal handoff is accepted, composition returns `awaiting_approval`. An operator inspects the proposal and
passes one explicit terminal `Approval` decision per material assumption to
`apply_experiment_protocol_approvals`. Resume with that approved protocol succeeds only when protocol ID, objective,
design digest and canonical inputs still match the proposal. A changed request, task, proposal, protocol, route or
canonical payload requires a new composition and otherwise fails closed. The proposal remains unchanged when
`research_register_experiment_workflow` later saves the approved protocol in its separate artifact row.

The caller supplies one `McpToolClient`, canonical artifact-store view and checkpointer across the parent composition
and child specialist/workflow execution. Thread IDs are derived separately, so one layer cannot overwrite another's
cursor. `max_transitions` bounds parent decisions; `max_workflow_tool_calls` deliberately pauses child workflow
execution. Exact terminal replay returns the saved bounded state without another specialist action, workflow
registration, plan step or outcome write. There is no generic MCP composition command.

### Deterministic Workflow Execution

Before compiling a protocol, create canonical Data records for every baseline/selection/holdout region with
`data_create_research_snapshot`. The tool requires one exact scope plus `requested_by` and `actor`; it fails closed when
the research artifact store is unavailable. Use the returned `research://postgres/dataset_manifest/...` and
`research://postgres/data_quality_report/...` refs in `ProtocolDataset`.

The operator must assemble five explicit dependencies before execution:

1. an approved `ResearchObjective` and matching approved `ExperimentProtocol`;
2. a `ResearchArtifactStore` that can resolve every supplied and produced canonical ref;
3. an MCP server/client using that same canonical artifact-store authority;
4. a LangGraph checkpointer, normally opened through the separately configured
   `TRADER_AGENTS_CHECKPOINT_DSN`; and
5. a stable workflow ID used for checkpoint thread identity and executor provenance.

`TRADER_RESEARCH_ARTIFACT_STORE_DSN` and `TRADER_AGENTS_CHECKPOINT_DSN` may identify different schemas, databases or
roles. They serve different contracts: the former is canonical product evidence, while the latter is replaceable
operational state. The executor's artifact-store instance must nevertheless see the same canonical records as the MCP
tools; a private in-memory store on one side and Postgres on the other is not a valid composition.

The coordinator, fixed compiler and executor are invoked through the Python library, not a generic MCP workflow
command. The coordinator reads canonical inputs and returns either a typed prerequisite/approval/blocker or a compiled
workflow selected from the code-owned catalog:

```python
coordination = coordinate_research(
    objective=approved_objective,
    protocol=approved_protocol,
    artifact_store=artifact_store,
)
if coordination.compiled_workflow is not None:
    execution = await execute_compiled_research_workflow(
        compiled=coordination.compiled_workflow,
        workflow_id=workflow_id,
        tool_client=mcp_client,
        checkpointer=checkpointer,
        artifact_store=artifact_store,
    )
else:
    handle_coordination_decision(coordination.decision)
```

`coordinate_research` performs no writes or MCP calls. Its executable decision pins objective ID, protocol ID,
registered template ID/version and deterministic plan ID. If a decision crosses a process boundary, call
`compile_coordination_decision` with the same canonical inputs before execution; it rejects unknown templates, changed
objective/protocol identity and plan drift. Do not deserialize model output directly into executor arguments.

The executor first calls `research_register_experiment_workflow`, then drives the compiled steps through MCP and finally
calls `research_record_workflow_outcome`. Enable `TRADER_MCP_ALLOW_BACKTESTS=true` for any executable template and
`TRADER_MCP_ALLOW_OPTIMIZATION=true` when the protocol contains optimisation. Existing Optuna and external-tracking
gates remain independent. A disabled gate yields a terminal blocked outcome; it does not skip the node or continue into
holdout/review.

Every compiled input and produced artifact is reloaded and payload-hashed. Changing a pinned record after compilation
blocks before the dependent tool executes. Transport retries stop after three attempts. To pause deliberately, pass
`max_tool_calls`; `WorkflowExecutionInterrupted.public_state` reports the bounded state and the same workflow ID,
compiled plan and checkpointer resume at the next unaccepted step.

`max_tool_calls` counts compiled plan-step calls during that invocation; workflow registration and terminal outcome
recording are outside that limit. Before writing, each invocation resolves the deterministic registration IDs. Existing
matching objective/protocol/plan records are fully revalidated and reused, so a resumed invocation does not repeat
`research_register_experiment_workflow`. The same rule reuses an existing matching terminal outcome. A deliberate pause
raises `WorkflowExecutionInterrupted` and writes no terminal outcome. Once the checkpoint is terminal, the executor
constructs and records the outcome if it is absent, then returns `WorkflowExecution`.

| Condition | Observable behavior |
| --- | --- |
| Objective or protocol is absent or awaits approval | The coordinator returns a typed prerequisite or approval request and no compiled workflow. |
| Objective/protocol identities differ, no unique registered template matches, or approved scope is unsupported | The coordinator returns a structured blocker and nothing is persisted. |
| A canonical implementation/Data ref does not resolve | The coordinator requests that exact domain-owned artifact and returns no compiled workflow. |
| A pinned prerequisite has invalid authority or content | The coordinator blocks the selection; direct compiler use raises before a plan is returned. |
| Workflow registration is rejected | Execution raises `WorkflowExecutionError` before the plan-step loop. |
| A pinned input drifts before its dependent call | The step becomes terminally blocked; later steps do not run and a blocked outcome is recorded. |
| A tool returns a policy blocker such as `backtests_not_allowed` | The tool is not bypassed; later optimisation/review steps do not run and a blocked outcome is recorded. |
| A transient transport call fails | The same step is attempted at most three times, then the workflow blocks. |
| `max_tool_calls` is reached | Execution raises `WorkflowExecutionInterrupted`; the checkpoint is preserved and no outcome is recorded. |
| Outcome persistence fails after terminal checkpoint state | Execution raises `WorkflowExecutionError`; rerunning with the same identity retries terminal outcome recording without replaying accepted steps. |

The generic `research_artifacts` table remains canonical. The following typed projections are for inspection:

```sql
SELECT * FROM public.research_objectives ORDER BY objective_id;
SELECT * FROM public.research_experiment_protocol_proposals ORDER BY proposal_id;
SELECT * FROM public.research_experiment_protocols ORDER BY protocol_id;
SELECT * FROM public.research_workflow_plans ORDER BY plan_id;
SELECT * FROM public.research_workflow_outcomes ORDER BY outcome_id;

SELECT artifact_type, artifact_id, domain_owner, producer_tool,
       requested_by, actor, status
FROM public.research_artifacts
WHERE requested_by = :workflow_id
ORDER BY created_at, artifact_type, artifact_id;
```

The typed rows expose workflow navigation; their JSONB payloads and the matching `research_artifacts` records remain the
canonical values. Checkpoint tables remain replaceable operational state. Current deterministic workflow qualification
is in-process MCP integration plus lower-level Postgres projection checks; fresh-process Postgres execution and operator
isolation remain part of the controlled orchestration qualification work in the active roadmap.

Run the controlled graph with the complete explicit verification environment:

```bash
export TRADER_VERIFICATION_RETAIN_PHASE=57M
export TRADER_MCP_ALLOW_BACKTESTS=true
export TRADER_MCP_ALLOW_OPTIMIZATION=true
uv run python -m tests.support.postgres_verification begin --phase 57M
uv run pytest tests/test_postgres_optimization_evidence_graph.py -m postgres -q -W error -s
uv run python -m tests.support.postgres_verification end --phase 57M --outcome passed
```

Inspect the retained canonical and typed evidence without relying on filesystem paths:

```sql
SELECT artifact_type, artifact_id, status, domain_owner, producer_tool,
       requested_by, actor
FROM public.research_artifacts
ORDER BY artifact_type, artifact_id;

SELECT optimization_run_id, optimization_plan_id, status, selected_trial_id
FROM public.research_parameter_optimization_runs
ORDER BY optimization_run_id;

SELECT optimization_run_id, sequence, status, objective_value, parameters,
       child_backtest_run_id
FROM public.research_parameter_optimization_trials
ORDER BY optimization_run_id, sequence;

SELECT run_id, dataset_id, status, selection_origin_ref
FROM public.research_backtest_runs
ORDER BY run_id;

SELECT report_id, optimization_run_id, holdout_backtest_run_id, status
FROM public.research_parameter_optimization_evaluations;

SELECT report_id, audit_plan_id, baseline_optimization_run_id, status
FROM public.research_parameter_optimization_robustness_reports;
```

### 57N Determinism, Integrity, And Holdout Leakage

57N repeats the complete 57M graph twice from guarded empty public runtime/research tables and also runs built-in random
search from the same provider-neutral plan. It compares stable refs and normalized canonical payload hashes for all
artifacts. Only wall-clock `backtest_run.bundle.result.finished_at` and `duration_seconds` are excluded; every research
input, event-derived result, observation, score, trial order, tie-break, selection, and report lineage remains hashed.

Between the clean repeats, the test mutates source hashes, validation state, strategy parameters, dataset and quality
snapshots, fixed costs, plan seed, engine configuration digest, trial objective/order, selected refs, and holdout
selection lineage directly in the disposable database. Each public MCP consumer must fail closed, and every successful
attack rejection is recorded in `verification_control.integrity_checks`. Original payloads are restored after each
case.

The test-only `AuditedPostgresEventStore` records bounded reads of `stock_bar_events` and `crypto_bar_events` in
`verification_control.data_access_log`, grouped under `plan_setup`, `selection_optimization`, and
`holdout_evaluation`. After optimisation completes, `verification_control.selection_seals` records a database-clock
seal over the selected run digest. Assertions require every trial child and objective observation to use the selection
region, no holdout backtest before the seal, a selection-stage maximum timestamp before holdout start, and all
holdout-evaluation audit rows after the seal. Plan setup may read both regions to create and hash the sealed manifests;
that is not model fitting or objective evaluation.

Run the controlled phase with exactly the backtest and optimisation gates enabled:

```bash
export TRADER_VERIFICATION_RETAIN_PHASE=57N
export TRADER_MCP_ALLOW_BACKTESTS=true
export TRADER_MCP_ALLOW_OPTIMIZATION=true
uv run python -m tests.support.postgres_verification begin --phase 57N
uv run pytest tests/test_postgres_optimization_determinism_integrity.py -m postgres -q -W error -s
uv run python -m tests.support.postgres_verification end --phase 57N --outcome passed
```

Inspect the retained qualification evidence in pgAdmin:

```sql
SELECT execution_label, graph_digest, artifact_count, root_refs
FROM verification_control.determinism_snapshots
WHERE phase = '57N'
ORDER BY execution_label;

SELECT check_name, target_artifact_type, consumer_tool, error_code, passed
FROM verification_control.integrity_checks
WHERE phase = '57N'
ORDER BY check_name;

SELECT stage, sum(read_count) AS reads,
       min(minimum_parameter_ts) AS minimum_parameter_ts,
       max(maximum_parameter_ts) AS maximum_parameter_ts
FROM verification_control.data_access_log
WHERE phase = '57N'
GROUP BY stage
ORDER BY stage;

SELECT optimization_run_id, run_digest, sealed_at
FROM verification_control.selection_seals
WHERE phase = '57N';
```

Do not copy verification rows into the operator database. The final acceptance record must distinguish passed,
failed, not run, and optional profile not qualified. Optional-provider failure leaves that provider gated off and does
not invalidate a passing built-in core unless canonical Trader state was affected.

### 57O Restart, Resume, Fault, And Deadline Qualification

57O proves that canonical Postgres state, rather than process memory, is sufficient to resume built-in optimisation.
The controlled test compares an uninterrupted run with fresh-process recovery after a partial run and injects failures
before/after trial and final-run persistence boundaries. A completed child backtest whose trial write was interrupted is
resolved by its deterministic run ID, its complete payload and lineage are revalidated, and the persisted row is reused
without updating it or replaying the event store. It also proves bounded retries, terminal blocked-run reads, stable
sequence/provider trial IDs, and Postgres child-process deadlines. A declared deadline is enforced by terminating the
isolated child; an executor without that capability blocks before executing.

Run with only backtests and optimisation enabled:

```bash
unset TRADER_VERIFICATION_RETAIN_PHASE
export TRADER_MCP_ALLOW_BACKTESTS=true
export TRADER_MCP_ALLOW_OPTIMIZATION=true
export TRADER_MCP_ALLOW_EXTERNAL_RESEARCH_WRITES=false
export TRADER_MCP_ALLOW_OPTUNA_WRITES=false
export TRADER_MCP_ALLOW_EXPERIMENT_TRACKING_WRITES=false
uv run python -m tests.support.postgres_verification begin --phase 57O
uv run pytest tests/test_postgres_optimization_recovery.py -m postgres -q -W error
uv run python -m tests.support.postgres_verification end --phase 57O --outcome passed
```

### 57P Provider Independence Qualification

57P starts a fresh stdio MCP process whose import hook makes both `optuna` and `mlflow` unavailable. It runs and resumes
built-in grid, runs seeded random, recreates the server for each call, and reloads both ledgers from canonical Postgres.
Only the two built-in profiles may appear in optimizer runtime metadata. This qualifies the mandatory no-provider
product; it does not qualify an Optuna or tracking-sink adapter.

```bash
export TRADER_MCP_ALLOW_BACKTESTS=true
export TRADER_MCP_ALLOW_OPTIMIZATION=true
export TRADER_MCP_ALLOW_EXTERNAL_RESEARCH_WRITES=false
export TRADER_MCP_ALLOW_OPTUNA_WRITES=false
export TRADER_MCP_ALLOW_EXPERIMENT_TRACKING_WRITES=false
uv run python -m tests.support.postgres_verification begin --phase 57P
uv run pytest tests/test_postgres_optimization_provider_independence.py -m postgres -q -W error
uv run python -m tests.support.postgres_verification end --phase 57P --outcome passed
```

Until separate live-provider profiles pass, record `optuna_tpe` and MLflow tracking as `not_qualified` and keep their
write gates false. Package presence or unit adapter tests are not provider qualification.

### 57Q Policy, Security, And Resource Boundaries

57Q runs with every mutation gate false at the phase boundary; individual MCP tests construct explicit isolated gate
matrices internally. The test set challenges closed objective observations, finite scores, import and builtin escape
surfaces, broad/restricted Trader imports, dependency-based permission expansion, database/broker mutation attempts,
undeclared tunables, holdout/dataset/cost boundaries, retry/trial/deadline limits, bounded failure payloads, MCP gate
independence, and Python package direction.

```bash
export TRADER_MCP_ALLOW_BACKTESTS=false
export TRADER_MCP_ALLOW_OPTIMIZATION=false
export TRADER_MCP_ALLOW_EXTERNAL_RESEARCH_WRITES=false
export TRADER_MCP_ALLOW_OPTUNA_WRITES=false
export TRADER_MCP_ALLOW_EXPERIMENT_TRACKING_WRITES=false
uv run python -m tests.support.postgres_verification begin --phase 57Q
uv run pytest tests/test_parameter_optimization.py tests/test_mcp_optimization_tools.py \
  tests/test_implementation_templates.py tests/test_package_boundaries.py -q -W error
uv run python -m tests.support.postgres_verification end --phase 57Q --outcome passed
```

Implementation admission remains a bounded validation policy plus deterministic fixture execution. It is not an OS
sandbox for hostile arbitrary Python; that limitation must remain in the 57S residual-risk record.

### 57R Projection, Operator, And Bounded-Scale Qualification

57R executes 64 real grid trials, 100 real seeded-random trials, and one three-symbol backtest with 1,000 bars per
symbol. It records wall times, result-query times, database size, artifact count, and the principal trial-ledger query
plan in `verification_control.bounded_scale_results`; it requires the run/sequence index and reconciles every artifact
in the scale graph with its typed projection. The scale measurements are local bounded evidence, not universal service
level objectives. The phase then reruns the public MCP evidence graph so the final retained product rows include
Evaluation and Adversarial evidence while the scale control rows remain inspectable.

```bash
export TRADER_VERIFICATION_RETAIN_PHASE=57R
export TRADER_MCP_ALLOW_BACKTESTS=true
export TRADER_MCP_ALLOW_OPTIMIZATION=true
export TRADER_MCP_ALLOW_EXTERNAL_RESEARCH_WRITES=false
export TRADER_MCP_ALLOW_OPTUNA_WRITES=false
export TRADER_MCP_ALLOW_EXPERIMENT_TRACKING_WRITES=false
uv run python -m tests.support.postgres_verification begin --phase 57R
uv run pytest tests/test_postgres_optimization_bounded_scale.py \
  tests/test_postgres_optimization_evidence_graph.py -m postgres -q -W error -s
uv run python -m tests.support.postgres_verification end --phase 57R --outcome passed
```

Inspect the bounded measurements with:

```sql
SELECT profile, status, symbols, bars_per_symbol, trial_count, wall_seconds,
       result_query_seconds, database_bytes, artifact_count, query_plan, payload
FROM verification_control.bounded_scale_results
WHERE phase = '57R'
ORDER BY profile;
```

### 57S Acceptance Record

57S reads, but does not recreate, the retained product evidence. It requires passed/isolated 57J-57R rows on one freeze,
empty blockers, matching before/after operator fingerprints, all three 57R bounded profiles, and retained optimisation,
Evaluation, and Adversarial refs. It writes one verification-only `acceptance_records` row. Built-in grid/random are
qualified; Optuna and MLflow tracking remain explicitly not qualified and disabled in the default acceptance profile.

```bash
unset TRADER_VERIFICATION_RETAIN_PHASE
export TRADER_MCP_ALLOW_BACKTESTS=false
export TRADER_MCP_ALLOW_OPTIMIZATION=false
export TRADER_MCP_ALLOW_EXTERNAL_RESEARCH_WRITES=false
export TRADER_MCP_ALLOW_OPTUNA_WRITES=false
export TRADER_MCP_ALLOW_EXPERIMENT_TRACKING_WRITES=false
uv run python -m tests.support.postgres_verification begin --phase 57S
uv run pytest tests/test_postgres_optimization_acceptance.py -m postgres -q -W error
uv run python -m tests.support.postgres_verification end --phase 57S --outcome passed
```

```sql
SELECT freeze_revision, status, mandatory_phases, provider_profiles, environment,
       evidence_inventory, commands, residual_risks, recorded_at
FROM verification_control.acceptance_records;
```

### Controlled Orchestration Qualification

`controlled_orchestration_v1` qualifies the implemented Data Agent, Experiment Design, operator approval,
Research Coordinator and fixed supplied-implementation workflow as one bounded responsibility graph. It adds no
general planner and does not qualify unavailable specialist routes. The `ORCHESTRATION_*` values below are evidence
record keys in `verification_control`, not names for architecture components.

Start only after the current product implementation is committed. Tag that clean product revision as
`verification-orchestration-v1-freeze`; the harness rejects a missing tag, a dirty worktree, product-byte drift, a
changed harness revision during a phase, an unexpected mutation gate or an operator fingerprint change. Configure the
admin, operator, product-test and optional-provider profiles described above, plus a distinct checkpoint profile that
targets the same `PG_TEST_DB`:

```bash
export TRADER_VERIFICATION_PROFILE=controlled_orchestration_v1
export TRADER_VERIFICATION_MODE=true
export TRADER_CHECKPOINT_SCHEMA=orchestration_checkpoint
export PG_CHECKPOINT_TEST_HOST="$PG_TEST_HOST"
export PG_CHECKPOINT_TEST_PORT="$PG_TEST_PORT"
export PG_CHECKPOINT_TEST_DB="$PG_TEST_DB"
export PG_CHECKPOINT_TEST_USER=trader_orchestration_checkpoint_test
export PG_CHECKPOINT_TEST_PASSWORD='...'
export TZ=UTC
export PYTHONHASHSEED=0
```

The checkpoint password is used only to build saver connections. Runtime manifests contain its host, port, database,
role and schema, never its password or a DSN. Provision once with every mutation gate false:

```bash
export TRADER_MCP_ALLOW_BROKER_MUTATION=false
export TRADER_MCP_ALLOW_RAW_SQL=false
export TRADER_MCP_ALLOW_DATA_LOADING=false
export TRADER_MCP_ALLOW_BACKTESTS=false
export TRADER_MCP_ALLOW_OPTIMIZATION=false
export TRADER_MCP_ALLOW_EXTERNAL_RESEARCH_WRITES=false
export TRADER_MCP_ALLOW_OPTUNA_WRITES=false
export TRADER_MCP_ALLOW_EXPERIMENT_TRACKING_WRITES=false
uv run python -m tests.support.postgres_verification provision --reset
```

Run the mandatory phases in this order. `begin` and `end` enforce the exact gate set shown; do not carry a retained
phase variable into a different phase.

```bash
uv run python -m tests.support.postgres_verification begin --phase ORCHESTRATION_RUNTIME
uv run pytest tests/test_postgres_orchestration_runtime.py -m postgres -q -W error
uv run python -m tests.support.postgres_verification end --phase ORCHESTRATION_RUNTIME --outcome passed

uv run python -m tests.support.postgres_verification begin --phase ORCHESTRATION_CORE
uv run ruff check src tests
python -m compileall -q src tests/support
uv run mypy
uv run pytest -m 'not postgres' -q -W error
uv run python -m tests.support.postgres_verification end --phase ORCHESTRATION_CORE --outcome passed

export TRADER_MCP_ALLOW_BACKTESTS=true
export TRADER_MCP_ALLOW_OPTIMIZATION=true
export TRADER_VERIFICATION_RETAIN_PHASE=ORCHESTRATION_E2E
uv run python -m tests.support.postgres_verification begin --phase ORCHESTRATION_E2E
uv run pytest tests/test_postgres_orchestration_evidence_graph.py -m postgres -q -W error -s
uv run python -m tests.support.postgres_verification end --phase ORCHESTRATION_E2E --outcome passed

export TRADER_MCP_ALLOW_OPTIMIZATION=false
export TRADER_VERIFICATION_RETAIN_PHASE=ORCHESTRATION_RECOVERY
uv run python -m tests.support.postgres_verification begin --phase ORCHESTRATION_RECOVERY
uv run pytest tests/test_postgres_orchestration_recovery.py -m postgres -q -W error -s
uv run python -m tests.support.postgres_verification end --phase ORCHESTRATION_RECOVERY --outcome passed

export TRADER_MCP_ALLOW_BACKTESTS=false
unset TRADER_VERIFICATION_RETAIN_PHASE
uv run python -m tests.support.postgres_verification begin --phase ORCHESTRATION_POLICY
uv run pytest tests/test_orchestration_policy_security.py tests/test_research_composition.py tests/test_experiment_design_specialist.py tests/test_package_boundaries.py -q -W error
uv run python -m tests.support.postgres_verification end --phase ORCHESTRATION_POLICY --outcome passed

export TRADER_MCP_ALLOW_BACKTESTS=true
export TRADER_VERIFICATION_RETAIN_PHASE=ORCHESTRATION_SCALE
uv run python -m tests.support.postgres_verification begin --phase ORCHESTRATION_SCALE
uv run pytest tests/test_postgres_orchestration_bounded_scale.py -m postgres -q -W error -s
uv run python -m tests.support.postgres_verification end --phase ORCHESTRATION_SCALE --outcome passed

export TRADER_MCP_ALLOW_BACKTESTS=false
unset TRADER_VERIFICATION_RETAIN_PHASE
uv run python -m tests.support.postgres_verification begin --phase ORCHESTRATION_ACCEPTANCE
uv run pytest tests/test_postgres_orchestration_acceptance.py -m postgres -q -W error -s
uv run python -m tests.support.postgres_verification end --phase ORCHESTRATION_ACCEPTANCE --outcome passed
```

The end-to-end, recovery and scale phases deliberately retain their disposable evidence. Later phases do not truncate
that evidence, so acceptance can read one freeze-wide graph. Setup inserts exact fixture bars only when absent and
otherwise checks their count and content digest. Each resume stage launches a new Python driver, opens the checkpoint
role anew and starts a fresh stdio MCP server. The response-loss fault retains only a command, argument digest, bounded
result identity and retry disposition; it never stores arguments, envelopes, source, credentials, approval rationale
or artifact payloads.

Inspect the credential-free verdict and evidence without expanding canonical payloads:

```sql
SELECT phase, isolation_status, qualification_status, blockers,
       manifest->>'qualification_profile' AS profile,
       operator_before_digest = operator_after_digest AS operator_unchanged
FROM verification_control.phase_runs
WHERE phase LIKE 'ORCHESTRATION_%'
ORDER BY started_at;

SELECT phase, composition_id, sequence, command, argument_digest,
       retry_disposition, result_identity
FROM verification_control.orchestration_call_ledger
ORDER BY phase, composition_id, sequence;

SELECT profile, task_count, transition_count, tool_call_count,
       checkpoint_bytes, artifact_count, database_bytes, wall_seconds
FROM verification_control.orchestration_scale_results
ORDER BY profile;

SELECT qualification_profile, freeze_revision, status, qualified_surface,
       exclusions, residual_risks
FROM verification_control.orchestration_acceptance_records;
```

If any phase blocks, end it with `--outcome blocked --blocker '...'`, stop the campaign and preserve the evidence. A
product or fixture defect is fixed before creating a new freeze tag; it is never waived in the acceptance record.

## Typical Local Checks

Use focused checks after changing docs, MCP registrations, agent identities, or artifact contracts:

```bash
uv run pytest tests/test_agent_runtime_foundation.py tests/test_mcp_server.py tests/test_research_domain.py -q
uv run pytest tests/test_parameter_optimization.py tests/test_mcp_optimization_tools.py -q
uv run pytest tests/test_research_agent_docs.py -q
uv run pytest tests/test_package_boundaries.py -q
uv run ruff check tests
python -m compileall -q src/trader_research src/trader_mcp src/trader_agents
```

For a broader MCP registration check:

```bash
uv run pytest tests/test_mcp_tools.py tests/test_mcp_data_workflow.py tests/test_mcp_quant_methods_tools.py tests/test_mcp_optimization_tools.py -q
```

Postgres integration tests destructively reset their fixture tables and therefore require the provisioned runtime
marker plus all five `PG_TEST_*` values. The test harness ignores legacy `PG_HOST`, `PG_PORT`, `PG_USER`, and
`PG_PASSWORD` variables. Run each Postgres phase between the fingerprinting `begin` and `end` commands above.

## Operational Safety

- Inspect `mcp_get_config` before running local-mutating tools.
- Keep `TRADER_MCP_ALLOW_BACKTESTS=false` unless intentionally running local backtests.
- Keep optimisation and both external-write gates false unless intentionally running the corresponding procedure.
- Keep `TRADER_MCP_ALLOW_DATA_LOADING=false` unless intentionally loading sample or backfilled data.
- Do not expose raw SQL or broker-mutating operations through research MCP.
- Treat structured research artifact rows as research evidence, not as live trading controls. New canonical execution
  artifacts have no filesystem fallback.
