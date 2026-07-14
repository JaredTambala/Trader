# Research MCP Operations

This document covers local operation for the research MCP server and related verification commands.

## Maintenance Posture

Knowledge-base creation, retrieval, bounded methodology extraction, and Data Agent tools remain supported operational
surfaces. Current work is not expanding semantic extraction beyond the 33AB baseline. Operational changes in these
areas should be limited to data integrity, citation correctness, security, dependency maintenance, and regression fixes
unless the tracker explicitly reactivates composite methodology work.

The active development direction is implementation-to-evidence: intake and validation for handwritten or AI-produced
strategy/risk code, reproducible backtest specifications, ML model versioning, and robustness/adversarial evaluation.
Those planned tools are not registered yet; use `mcp_get_config` and [mcp_tools.md](mcp_tools.md) rather than inferring
availability from the roadmap.

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
| `TRADER_MCP_ARTIFACT_ROOT` | `artifacts/research` | Fallback/export root for local filesystem artifacts. |
| `TRADER_MCP_TRADER_CONFIG_PATH` | empty | Optional trader YAML for execution-plane dependencies and the Postgres research artifact store. |
| `TRADER_MCP_TOOL_ENV_PATH` | `.env` | Optional dotenv file loaded lazily for trader YAML expansion. |
| `TRADER_MCP_ALLOW_DATA_LOADING` | `false` | Enables explicit sample/backfill mutation. |
| `TRADER_MCP_ALLOW_BACKTESTS` | `false` | Enables `research_run_backtest` and `research_run_portfolio_backtest` execution. |
| `TRADER_MCP_ALLOW_BROKER_MUTATION` | `false` | Must remain false for research MCP tools. |
| `TRADER_MCP_ALLOW_RAW_SQL` | `false` | Must remain false for research MCP tools. |

### Planned MLflow Runtime

MLflow integration is not implemented yet. Tasks 39A-39J will define the final names and adapters, but the operational
contract must include:

- one configured tracking URI and registry URI, with callers unable to override them per tool request
- authentication through environment/secret references that are never persisted in artifacts or tool envelopes
- a database-backed MLflow backend store and configured artifact store suitable for Model Registry use
- tracking-server identity and client/server version checks exposed through read-only health/config tools
- namespaced experiment and registered-model policies so runs cannot be reconciled from an unrelated authority
- independent default-off gates for MLflow writes, model fitting, and model-alias mutation
- resource, timeout, dependency, and artifact-size bounds for training and evaluation execution
- no live deployment mutation through MCP; deployment tools create and validate backtest/paper manifests only

Planned environment controls should follow the existing MCP policy pattern, for example configured MLflow tracking and
registry locations plus `TRADER_MCP_ALLOW_MLFLOW_WRITES`, `TRADER_MCP_ALLOW_ML_TRAINING`, and
`TRADER_MCP_ALLOW_MODEL_ALIAS_MUTATION`. These names are roadmap contracts until task 39A implements and tests them.

The MLflow artifact store remains the model-binary authority. Trader Postgres stores reconciled MLflow IDs/URIs,
digests, signatures, source/data/environment hashes, and validation/promotion/deployment lineage. It does not duplicate
model binaries into generic research artifact payloads.

Quantitative Methods knowledge tools expect a configured knowledge store for production use. Postgres-backed knowledge
storage is the normal runtime path; tests may inject compatibility stores.

Full-document ingestion stages embedding generation before replacing active evidence. A successful Postgres run
publishes replacement evidence units, vectors, the embedding manifest, and the ingestion report in one transaction. If
embedding or publication fails, the prior active generation remains available; investigate the blocked run before
retrying with `force=true`.

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
- For strategy/risk generation, prefer explicit rich-card IDs or refs over inline payloads in operator workflows so the
  DB lineage remains visible in pgAdmin and downstream artifact refs.

MCP research artifact persistence is DB-first. When `TRADER_MCP_TRADER_CONFIG_PATH` points at a Postgres-backed Trader
config, mutating methodology, method, strategy, risk-manager, portfolio-backtest, and evaluation tools store canonical artifacts in
the structured research artifact tables and return `research://postgres/{artifact_type}/{artifact_id}` refs. If no
research artifact store is configured, those mutating MCP paths fail closed instead of silently creating canonical
filesystem artifacts. The filesystem `artifact_root` remains available for legacy direct-service exports and backtest
result files that have not yet moved into the research artifact store.

## Typical Local Checks

Use focused checks after changing docs, MCP registrations, agent identities, or artifact contracts:

```bash
uv run pytest tests/test_agent_identities.py tests/test_mcp_server.py tests/test_research_domain.py -q
uv run pytest tests/test_research_agent_docs.py -q
uv run pytest tests/test_package_boundaries.py -q
uv run ruff check tests
python -m compileall -q src/trader_research src/trader_mcp src/trader_agents
```

For a broader MCP registration check:

```bash
uv run pytest tests/test_mcp_tools.py tests/test_mcp_data_workflow.py tests/test_mcp_quant_methods_tools.py tests/test_mcp_strategy_tools.py tests/test_mcp_backtest_tools.py tests/test_mcp_evaluation_tools.py -q
```

## Operational Safety

- Inspect `mcp_get_config` before running local-mutating tools.
- Keep `TRADER_MCP_ALLOW_BACKTESTS=false` unless intentionally running local backtests.
- Keep `TRADER_MCP_ALLOW_DATA_LOADING=false` unless intentionally loading sample or backfilled data.
- Do not expose raw SQL or broker-mutating operations through research MCP.
- Treat structured research artifact rows and any fallback files under `artifacts/research/` as research evidence, not as
  live trading controls.
