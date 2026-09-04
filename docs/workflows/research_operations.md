# Research And Agent Operations

This document covers local operation for the research MCP server and related verification commands.

## Maintenance Posture

Knowledge-base creation, retrieval, bounded methodology extraction, and Data Agent tools remain supported operational
surfaces. Current work is not expanding semantic extraction beyond the implemented bounded-methodology baseline. Operational changes in these
areas should be limited to data integrity, citation correctness, security, dependency maintenance, and regression fixes
unless the
[Trader Development Roadmap](https://app.notion.com/p/d1453b7a4da6468babead2a5cda7ef84) explicitly reactivates
composite methodology work.

The implementation-to-evidence, provider-neutral parameter-optimisation, and ML deployment/runtime tools are now
registered. ML feature/training/evaluation/registry/monitoring and broader robustness work remain planned. Use
`mcp_get_config` for exact runtime gates and provider health.

## Start The Server

The MCP server uses stdio:

<!-- verified: integration:postgres/local-model/provider tests/test_postgres_verification_runtime.py tests/test_postgres_agentic_acceptance.py tests/test_postgres_optimization_acceptance.py -->
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
| `TRADER_AGENTS_MODEL_PROFILE_ID` | `ollama-lfm25-8b-json-v1` | Exact active evaluation profile. It pins Ollama `lfm2.5:8b` digest `9cf756159fc2f3b9128c6a3f544ec90c5e9b8afdbb4179a57b8aea9de589cfb2`, an 8,192-token context window, and a 2,048-token output ceiling. Its first complete Coordinator gate failed, so it is not accepted for qualification. |
| `TRADER_AGENTS_MCP_COMMAND` | current Python executable | Command used to start each isolated MCP stdio server. |
| `TRADER_AGENTS_MCP_ARGS` | `-m trader_mcp.server` | Arguments for each MCP stdio server. |
| `TRADER_AGENTS_MCP_CWD` | current directory | Working directory for MCP server processes. |
| `TRADER_AGENTS_MCP_TIMEOUT_SECONDS` | `180` | Per-call MCP transport timeout. |
| `TRADER_AGENTS_LOG_LEVEL` | `INFO` | `INFO` operator narrative or `DEBUG` diagnostic event detail on agent `stderr`. |
| `TRADER_AGENTS_LOG_FORMAT` | `human` | Human-readable lines or exact `json` event lines on agent `stderr`. |
| `TRADER_AGENTS_MLFLOW_TRACKING_URI` | empty | Optional MLflow tracking URI for redacted agent traces; no trace sink is used when empty. |
| `TRADER_AGENTS_MLFLOW_EXPERIMENT` | `trader-agentic-research` | MLflow experiment for agent trace correlation. |
| `TRADER_MLFLOW_INFERENCE_PROFILE` | `mlflow_local_pyfunc` | Names the configured immutable local-pyfunc adapter profile. |
| `TRADER_MCP_ALLOW_BROKER_MUTATION` | `false` | Must remain false for research MCP tools. |
| `TRADER_MCP_ALLOW_RAW_SQL` | `false` | Must remain false for research MCP tools. |

Provision the Optuna role/schema outside MCP with least privilege, set that role as the URL username, and grant it only
the dedicated schema. Trader's normal application role should not use that schema. `mcp_get_config` reports only whether
the profile is configured; `research_get_optimizer_runtime` reports package/config availability without connecting or
creating a study. Built-in grid/random remain available when the URL or Optuna package is absent.

## Model-Backed Research Runtime User Guide (Unqualified)

The `trader-agent` command operates the implemented Coordinator–Data–Strategy slice. It is available for development
and qualification; it is not yet a controlled production capability.

### What The Command Does

One invocation opens three independent MCP stdio clients and one PostgreSQL LangGraph checkpointer. The Research
Coordinator model creates or resumes the shared agenda and selects only responsibilities required by the brief. Data
Research and Strategy Engineering receive separate, bounded contexts only when selected and can run concurrently only
when their declared dependencies and mutation keys permit it. Each selected specialist proposes one tool call at a
time; code validates the proposal against the immutable session before MCP sees it. Structured returns rejoin the
Coordinator, which re-reads exact canonical evidence before recording a public decision receipt and choosing the next
action. An unselected specialist's client remains idle.

The slice ends when every responsibility in the accepted agenda is ready, or with a blocker, an operator question, or
an explicit cancellation. A complete combined brief still requires Data readiness plus an admitted strategy or risk
implementation; a Data-only or Strategy-only brief can conclude without inventing work for the other role. The slice
does not backtest the implementation, optimize it, perform robustness or walk-forward analysis, recommend paper
trading, or touch a broker.

### Prerequisites And Configuration

Before starting a session:

1. Install the locked project environment with `uv sync` and run PostgreSQL for both canonical research evidence and
   replaceable LangGraph checkpoints.
2. Configure `TRADER_MCP_TRADER_CONFIG_PATH` for the canonical research store and set
   `TRADER_AGENTS_CHECKPOINT_DSN` to a dedicated checkpoint role/database or schema. Do not rely on the research-store
   DSN as a checkpoint fallback.
3. Serve the model named by the active evaluation profile. The current profile requires Ollama `lfm2.5:8b` with
   the exact content digest embedded in `trader_agents.profiles`; a matching name backed by different bytes fails
   before its first model decision.
4. Keep `TRADER_MCP_ALLOW_BROKER_MUTATION=false` and `TRADER_MCP_ALLOW_RAW_SQL=false`. Enable Data loading only when
   the session also contains a matching pre-approved acquisition envelope.
5. For adaptation or authorship, configure the Coding Workspace as described below. Exact reuse does not require the
   sandbox.
6. Set `TRADER_AGENTS_MLFLOW_TRACKING_URI` and, optionally, `TRADER_AGENTS_MLFLOW_EXPERIMENT` when queryable redacted
   agent traces are required. Leaving the URI empty selects the no-op trace sink.

Run `uv run trader-agent manifest` after any dependency, program, model-profile, or tool-catalogue change. The returned
identities are inputs to the session, not informative labels that the runtime may silently replace.

### Create An Immutable Session

First inspect the exact credential-free runtime identities:

<!-- verified: integration:postgres/local-model/provider tests/test_postgres_verification_runtime.py tests/test_postgres_agentic_acceptance.py tests/test_postgres_optimization_acceptance.py -->
```bash
uv run trader-agent manifest
```

Create a JSON serialization of one immutable `ResearchSession` using the exact model-profile, all three agent-program,
and tool-catalogue identities from that manifest. The session is the authority boundary and must include:

- a stable session and operator identity, natural-language objective, and observable success definition;
- a complete multi-item Data scope with roles, symbols, fields, timeframe, bounds, provider envelope, warmup, and
  quality requirements;
- either one exact existing implementation ref or a complete operator-approved build specification;
- explicit Data-loading and Coding Workspace approvals;
- the Python quality-guide reference and exact repository revision used for authorship; and
- finite call, token, time, mutation, revision, and concurrency budgets.

The model may reason inside these bounds but cannot infer missing material strategy semantics or expand authority.
`tests/fixtures/agentic_slice_session_inputs.json` is a comprehensive non-production example of the normalized input
shape and edge cases. It is a qualification fixture, not a ready-to-run production session. Validate a completed
session without opening Postgres, a model, or MCP subprocesses:

<!-- verified: integration:postgres/local-model/provider tests/test_postgres_verification_runtime.py tests/test_postgres_agentic_acceptance.py tests/test_postgres_optimization_acceptance.py -->
```bash
uv run trader-agent validate-session --session /absolute/path/to/session.json
```

Budget reservations are deliberately upper bounds, not predictions. The session must have enough remaining capacity
for the worst valid specialist path it authorizes, including one structured-output repair and, when approved, one
evidence-led candidate repair. Every physical provider call and every MCP dispatch consumes accounting even when the
process exits before its next checkpoint.

### Start And Recover A Session

For execution, configure the canonical research store/MCP environment, dedicated checkpoint persistence, and the
admitted model. Apply the idempotent LangGraph checkpoint schema explicitly when provisioning a fresh checkpoint
namespace:

<!-- verified: integration:postgres/local-model/provider tests/test_postgres_verification_runtime.py tests/test_postgres_agentic_acceptance.py tests/test_postgres_optimization_acceptance.py -->
```bash
export TRADER_AGENTS_CHECKPOINT_DSN='postgresql://checkpoint_role:...@localhost:5432/trader_checkpoints'
uv run trader-agent run --session /absolute/path/to/session.json --setup-checkpoint-schema
```

`run` starts three persistent stdio MCP sessions so Coordinator, Data, and Strategy transport state is isolated. It
either prints a grounded `AgenticSliceResult` or an `OperatorInterrupt`. A later invocation with the exact same session
identity recovers the existing checkpoint instead of creating a second research lineage. Inspect only the redacted
public projection with:

The final result is written to `stdout`. Semantic agent events and role/process-labelled MCP lifecycle events are
written to `stderr`, leaving child MCP JSON-RPC isolated on its protocol `stdout`. For an operator-readable terminal,
use the default INFO/human settings. For a retained contract-test or qualification trace, put the two streams in
separate files:

```text
uv run trader-agent --log-level DEBUG --log-format json run \
  --session /absolute/path/to/session.json \
  > result.json 2> agent-events.jsonl
```

The event log is redacted diagnostic evidence, not a canonical research record. Use `pytest -s` to display live logs
during a focused test or `--capture=tee-sys` to display them while retaining pytest capture.

<!-- verified: integration:postgres/local-model/provider tests/test_postgres_verification_runtime.py tests/test_postgres_agentic_acceptance.py tests/test_postgres_optimization_acceptance.py -->
```bash
uv run trader-agent inspect --session /absolute/path/to/session.json
```

Resume an interrupt using the same session and exact operator identity:

<!-- verified: integration:postgres/local-model/provider tests/test_postgres_verification_runtime.py tests/test_postgres_agentic_acceptance.py tests/test_postgres_optimization_acceptance.py -->
```bash
uv run trader-agent resume \
  --session /absolute/path/to/session.json \
  --approved true \
  --answer 'Bounded public operator response' \
  --operator-id operator-name
```

Cancel a checkpointed non-terminal session using the owning operator identity and a bounded public reason:

<!-- verified: integration:postgres/local-model/provider tests/test_postgres_verification_runtime.py tests/test_postgres_agentic_acceptance.py tests/test_postgres_optimization_acceptance.py -->
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

Never edit a session file and reuse its `session_id`. The stored session digest, checkpoint identity, canonical
receipts, and mutation journals make that drift fail closed. Create a new session or explicit research branch for a
materially different objective, scope, build contract, program, model, tool catalogue, or budget.

### Configure The Coding Workspace

Build the sandbox from the repository revision that the session pins, publish it to a registry that the local Docker
daemon can resolve, and use the immutable repository digest rather than a tag:

<!-- verified: integration:postgres/local-model/provider tests/test_postgres_verification_runtime.py tests/test_postgres_agentic_acceptance.py tests/test_postgres_optimization_acceptance.py -->
```bash
docker build -f containers/agent-sandbox/Dockerfile -t trader-agent-sandbox:candidate .
docker tag trader-agent-sandbox:candidate localhost:5000/trader/agent-sandbox:candidate
docker push localhost:5000/trader/agent-sandbox:candidate
docker image inspect --format '{{index .RepoDigests 0}}' \
  localhost:5000/trader/agent-sandbox:candidate
```

Then configure a dedicated workspace root outside the repository:

<!-- verified: integration:postgres/local-model/provider tests/test_postgres_verification_runtime.py tests/test_postgres_agentic_acceptance.py tests/test_postgres_optimization_acceptance.py -->
```bash
export TRADER_MCP_ALLOW_CODING_WORKSPACE=true
export TRADER_MCP_CODING_WORKSPACE_ROOT=/absolute/dedicated/trader-agent-workspaces
export TRADER_MCP_CODING_REPOSITORY_ROOT=/absolute/read-only/Trader
export TRADER_MCP_CODING_REPOSITORY_REVISION="$(git rev-parse HEAD)"
export TRADER_MCP_CODING_CONTAINER_IMAGE='registry/repository@sha256:<64-hex-digest>'
```

The runner mounts the repository read-only and candidate files separately, disables network and IPC, drops
capabilities, prevents privilege escalation, runs as a non-root user, bounds CPU/memory/processes/file descriptors,
and limits time and output. It owns and verifies cleanup of the exact container after success, failure, timeout, or
output cutoff. Missing Docker, an invalid digest, or failed cleanup is an error; there is no host-execution fallback.
The deterministic admission service remains a separate gate after any sandbox check passes.

### Read Results, Evidence, And Traces

An `AgenticSliceResult` reports the terminal status, public summary, optional Data and Strategy specialist returns, the
exact Coordinator decision, its canonical receipt ref, aggregate budget use, and permitted next actions. A specialist
return is absent when that responsibility was not selected. Treat the included refs—not the prose summary—as the audit
trail:

- Data refs resolve to the exact manifest and quality evidence for the complete or explicitly partial scope.
- Strategy refs resolve to the exact implementation version and its own matching admission report.
- Candidate-attempt, package, and admission lineage distinguish reuse, adaptation, authorship, and repair.
- A `blocked`, `failed`, or `cancelled` result is terminal evidence, not permission to retry under changed inputs with
  the same session identity.
- An `OperatorInterrupt` contains a bounded question and resume schema; it does not itself grant the requested
  authority.

With agent MLflow tracing enabled, each start, resume, cancel, or inspect operation creates a lifecycle root joined to
redacted model, MCP call/result, validation, checkpoint/decision, workspace, and admission spans. Roots are flushed
before the invocation closes so a later process can query them. Traces retain public correlation identities,
operation classes, evidence types/refs, counters, and bounded error codes. They intentionally omit prompts, model
messages, hidden reasoning, source code, credentials, raw scope payloads, and full tool responses. MLflow is
observability only; canonical Trader evidence and decision receipts remain authoritative.

### Failure And Recovery Rules

- Re-run `run` with the byte-identical session after a process failure. LangGraph resumes the latest bounded checkpoint;
  canonical operation journals reconcile accepted side effects that occurred after it.
- A terminal Data load, candidate write, package registration, or admission is replayed by stable runtime operation
  identity rather than dispatched again. Ambiguous prepared Data mutations fail with an explicit reconciliation error.
- A Coordinator decision is checkpointed before its receipt write. Recovery retries that exact decision and does not
  ask the model to invent another one.
- Physical provider calls and their terminal result/validation spans are counted even when their process dies before
  saving normal checkpoint usage.
- Equivalent repeated work, exhausted budgets, identity drift, unauthorized scope, or an unresolvable lost mutation
  stops or interrupts; the runtime does not silently widen scope or loop indefinitely.

### Qualification Status

The runtime, phase entry points, fresh-process recovery matrix, Docker sandbox checks, no-selection 36-run campaign,
and four bounded-scale profiles are implemented. This guide describes the current development capability, not a
controlled release. Controlled status requires all mandatory phases to persist matching evidence against one clean
freeze, followed by independent verification and a canonical acceptance record. The roadmap and product-state page
remain authoritative for that verdict.

### MLflow Runtime Boundary

The current MLflow integration supports explicit non-authoritative optimisation projection and a separate lazy local
pyfunc inference adapter. The adapter is registered only when `MLFLOW_TRACKING_URI` is configured; the MCP server still
starts when MLflow/pandas are absent. `ml_create_deployment_manifest` is DB-only. `ml_validate_deployment` and
model-backed backtests require `TRADER_MCP_ALLOW_ML_RUNTIME=true`, load only a pinned model URI, and never write to
MLflow. Authoritative training, registry, and monitoring behavior remains planned. The operational contract is:

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

<!-- verified: integration:postgres/local-model/provider tests/test_postgres_verification_runtime.py tests/test_postgres_agentic_acceptance.py tests/test_postgres_optimization_acceptance.py -->
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

The canonical implementation/specification cutover has no data migration or compatibility reader. A database containing candidate-era research
tables or artifacts is unsupported and must be recreated or reset as a clean database before use. Schema initialization
then creates only canonical implementation, specification, backtest, optimisation, tracking, Evaluation, and
Adversarial projections. Do not translate old rows, synthesize new refs from candidate IDs, or selectively preserve
candidate-era research data.

## Historical qualification records

Tag-specific deterministic qualification phases and commands are retained in the
[pre-package-ownership operations record](../history/research_agents/research_operations_before_package_ownership.md).
They are historical evidence, not instructions for qualifying the current model-backed runtime.
