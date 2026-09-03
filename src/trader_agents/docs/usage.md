# Agent Runtime Usage Reference

## Public Python lifecycle

`runtime_from_environment()` builds the exact configured system. `AgenticResearchRuntime` provides asynchronous
`start(session)`, `resume(session, response)`, `inspect(session)`, and `cancel(session, cancellation)` methods. The
session is an immutable `trader_research.governance.ResearchSession`, normally loaded through its canonical MCP
reference rather than constructed ad hoc.

## CLI

<!-- verified: offline-shell tests/test_package_documentation.py::test_declared_shell_examples -->
```bash
trader-agent --help
```

The CLI is lifecycle control, not a free-form chat shell. It emits public JSON-safe results or interrupts and never
prints hidden model reasoning. Preserve the same session, operator, model-profile, program, tool-catalogue, and
checkpoint identities on recovery.

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
