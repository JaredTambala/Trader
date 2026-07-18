# Research MCP Operations

This document covers local operation for the research MCP server and related verification commands.

## Maintenance Posture

Knowledge-base creation, retrieval, bounded methodology extraction, and Data Agent tools remain supported operational
surfaces. Current work is not expanding semantic extraction beyond the 33AB baseline. Operational changes in these
areas should be limited to data integrity, citation correctness, security, dependency maintenance, and regression fixes
unless the tracker explicitly reactivates composite methodology work.

The implementation-to-evidence and provider-neutral parameter-optimisation tools are now registered. ML model lifecycle
and broader robustness work remain planned. Use `mcp_get_config` for exact runtime gates and provider health.

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
| `TRADER_MCP_ALLOW_BROKER_MUTATION` | `false` | Must remain false for research MCP tools. |
| `TRADER_MCP_ALLOW_RAW_SQL` | `false` | Must remain false for research MCP tools. |

Provision the Optuna role/schema outside MCP with least privilege, set that role as the URL username, and grant it only
the dedicated schema. Trader's normal application role should not use that schema. `mcp_get_config` reports only whether
the profile is configured; `research_get_optimizer_runtime` reports package/config availability without connecting or
creating a study. Built-in grid/random remain available when the URL or Optuna package is absent.

### MLflow Runtime Boundary

The current MLflow adapter supports only explicit non-authoritative projection of canonical backtest-optimisation
evidence. Tasks 39A-39J will add authoritative ML training telemetry/model-registry behavior. The operational contract
is:

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

Quantitative Methods knowledge tools expect a configured knowledge store for production use. Postgres-backed knowledge
storage is the normal runtime path; tests may inject isolated in-memory stores.

Full-document ingestion stages embedding generation before replacing active evidence. A successful Postgres run
publishes replacement evidence units, vectors, the embedding manifest, and the ingestion report in one transaction. If
embedding or publication fails, the prior active generation remains available; investigate the blocked run before
retrying with `force=true`. Providers that expose ordered batch embedding are called in bounded 16-text batches; each
response must match the requested count and indexes before publication. Single-text providers retain the same atomic
path through a deterministic fallback.

`knowledge_assemble_methodology_evidence` and `knowledge_create_rich_method_card_draft` require both the knowledge store
and the research artifact store. Evidence assembly loads a methodology candidate, applies the family evidence profile,
and writes a role-labeled `methodology_evidence_packet` research artifact. Rich draft creation loads a passed
methodology-candidate validation report from structured research artifacts, revalidates source/chunk evidence in the
knowledge store, and writes the rich method-card draft back through the knowledge-store method-card path.

## Rich Methodology Operating Checklist

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

## Controlled Verification Procedure

Tasks 57I-57S in the [active tracker](../../plans/mcp_trading_research_tools_plan.md) are the release-qualification procedure
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

The controlled harness accepts four explicit connection profiles. It never derives test credentials from `.env`
operator names:

| Profile | Variables | Authority |
|---|---|---|
| Provisioning admin | `PG_ADMIN_HOST`, `PG_ADMIN_PORT`, `PG_ADMIN_DB`, `PG_ADMIN_USER`, `PG_ADMIN_PASSWORD` | Creates only the named verification roles/database and the `vector` extension. |
| Operator fingerprint | `PG_OPERATOR_HOST`, `PG_OPERATOR_PORT`, `PG_OPERATOR_DB`, `PG_OPERATOR_USER`, `PG_OPERATOR_PASSWORD` | Opens an explicit read-only, repeatable-read transaction; never writes verification evidence here. |
| Trader verification | `PG_TEST_HOST`, `PG_TEST_PORT`, `PG_TEST_DB`, `PG_TEST_USER`, `PG_TEST_PASSWORD` | Owns the disposable `*_test` database and product test schemas. |
| Optuna verification | `PG_OPTUNA_TEST_HOST`, `PG_OPTUNA_TEST_PORT`, `PG_OPTUNA_TEST_DB`, `PG_OPTUNA_TEST_USER`, `PG_OPTUNA_TEST_PASSWORD` | Targets the same test database and owns only `TRADER_OPTUNA_SCHEMA`. |

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

With a clean worktree whose product paths are byte-identical to `verification-57i-freeze-v2`, execute:

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

Do not copy verification rows into the operator database. The final acceptance record must distinguish passed,
failed, not run, and optional profile not qualified. Optional-provider failure leaves that provider gated off and does
not invalidate a passing built-in core unless canonical Trader state was affected.

## Typical Local Checks

Use focused checks after changing docs, MCP registrations, agent identities, or artifact contracts:

```bash
uv run pytest tests/test_agent_identities.py tests/test_mcp_server.py tests/test_research_domain.py -q
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
