# Agent Runtime Usage Reference

## Public Python lifecycle

`runtime_from_environment()` builds the exact configured system. `AgenticResearchRuntime` provides asynchronous
`start(session)`, `resume(session, response)`, `inspect(session)`, and `cancel(session, cancellation)` methods. The
session is an immutable `trader_research.governance.ResearchSession`, normally loaded through its canonical MCP
reference rather than constructed ad hoc.

Application callers should import stable public types and lifecycle functions from `trader_agents`. Contributors who
need an internal extension seam should use its canonical responsibility path—for example,
`trader_agents.model_runtime.client.LlmClient` or `trader_agents.mcp.client.McpToolClient`. Flat implementation-module
imports are intentionally unsupported; source moves do not leave aliases behind.

## CLI

<!-- verified: offline-shell tests/cross_package/documentation/test_package_documentation.py::test_declared_shell_examples -->
```bash
trader-agent --log-level INFO --log-format human --help
```

The CLI is lifecycle control, not a free-form chat shell. It emits public JSON-safe results or interrupts and never
prints hidden model reasoning. Final result JSON is written to `stdout`; runtime and child MCP events are written to
`stderr`. Preserve the same session, operator, model-profile, program, tool-catalogue, and checkpoint identities on
recovery.

`--log-level INFO` is the default narrative. `--log-level DEBUG` adds model receipt/schema, policy admission,
scheduling, budgets, and checkpoint saves. Select `--log-format human` for direct reading or `--log-format json` for
one validated event per line. CLI values take precedence over `TRADER_AGENTS_LOG_LEVEL` and
`TRADER_AGENTS_LOG_FORMAT`; the runtime passes the resolved values to each MCP subprocess.

Keep machine results and diagnostic events separate during a real run:

```text
uv run trader-agent --log-level DEBUG --log-format json run \
  --session /absolute/path/to/session.json \
  > result.json 2> agent-events.jsonl
```

Use `pytest -s` for uncaptured live logs or `--capture=tee-sys` when contract-test output should be both displayed and
retained by pytest.

## Public observability contract

Use the event builder rather than assigning level or authority at a call site. The semantic event name fixes those
values, while the caller supplies the runtime clock, process-local sequence, and exact correlation identities.

<!-- verified: doctest -->
```pycon
>>> from datetime import UTC, datetime
>>> from trader_agents import (
...     AgentEventCorrelation,
...     AgentEventName,
...     build_agent_observability_event,
... )
>>> correlation = AgentEventCorrelation(
...     session_id="session-1",
...     branch_id="branch-1",
...     role="research_coordinator",
...     program_id="research-coordinator-v1",
...     model_profile_id="ollama-lfm25-8b-json-v1",
...     tool_catalog_id="first-agentic-slice-v1",
...     process_instance_id="worker-1",
... )
>>> event = build_agent_observability_event(
...     name=AgentEventName.SESSION_STARTED,
...     timestamp=datetime(2026, 9, 3, 12, tzinfo=UTC),
...     sequence=1,
...     correlation=correlation,
...     fields={"operation": "start"},
... )
>>> (event.name.value, event.level.value, event.authority.value)
('agent.session.started', 'info', 'diagnostic')
>>> event.to_dict()["timestamp"]
'2026-09-03T12:00:00Z'
```

For agent and MCP values, build `fields` with the matching `project_*` function rather than `model_dump()`. The
projectors accept `ProjectionDetail.INFO` or `ProjectionDetail.DEBUG`; both apply the same recursive redaction and size
limits. `NoOpObservabilityEventSink` and `RecordingObservabilityEventSink` are available for isolated composition and
tests. `ConsoleObservabilityEventSink` is the production console adapter. A shared `AgentEventEmitter` supplies the
process identity, event clock, and ordered sequence; callers supply semantic correlation and projector output.

## Required services

- Ollama serving the exact admitted `lfm2.5:8b` digest
- local stdio `trader_mcp` configured for the required capability flags
- canonical research Postgres with the required role separation
- separate LangGraph checkpoint Postgres/role
- digest-pinned Docker image for Strategy work when coding is permitted
- optional MLflow tracking sink for redacted lifecycle traces

See the root [environment guide](../../../docs/environment.md) and [research operations](../../../docs/workflows/research_operations.md).

## Safe embedding

Tests may inject a `StaticJsonLlmClient`, fake MCP client, in-memory checkpointer, and recording trace sink. Those are
explicit test compositions and never substitute for required production dependencies. Use them to prove contracts and
graph behavior, not provider behavior or controlled qualification.
