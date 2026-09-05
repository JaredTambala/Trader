# MCP Tutorial

This tutorial begins with the public envelope offline, then shows how to inspect the real server. It does not invoke a
mutating tool.

## 1. Understand what crosses the wire

<!-- verified: doctest -->
```pycon
>>> from trader_mcp.protocol.contracts import SideEffect, success_envelope
>>> envelope = success_envelope(
...     command="mcp_health",
...     side_effect=SideEffect.READ_ONLY,
...     agent_owner="MCP Server",
...     data={"status": "ok"},
... )
>>> envelope.to_dict()["side_effect"]
'read_only'
>>> envelope.to_dict()["data"]
{'status': 'ok'}
```

The `agent_owner` describes the registered operation owner; it is not caller identity. Caller authorization is checked
by the role-scoped runtime before dispatch.

## 2. Configure a local read-only server

Copy the repository example environment, keep every mutation flag false, and point it at a deliberate artifact root.
The real parser test in `tests/trader_mcp/catalogue_policy/test_environment_and_registration.py` validates the
environment boundary.

<!-- verified: integration:mcp tests/trader_mcp/catalogue_policy/test_environment_and_registration.py -->
```bash
uv run python -m trader_mcp.runtime.server --env-path local.env
```

The process speaks MCP over stdio. Do not write logs or prompts to stdout; stdout is transport-owned.

## 3. Discover before calling

An MCP client initializes the session, lists tools, and inspects their schemas. Tool availability reflects environment
policy and configured adapters. The server's full catalogue is not automatically the current agent's catalogue.

## 4. Call and validate

Provide schema-valid JSON, inspect `isError` at the MCP layer, then validate the returned envelope. Check `ok`, errors,
warnings, artifacts, command, owner, side effect, and schema version. Re-read canonical artifact references before using
them for a later mutation or conclusion.

## 5. Handle unavailable capability

An absent registration, disabled capability flag, unavailable adapter, application failure, and transport failure are
different states. Preserve that distinction. Do not replace a failed real operation with an in-memory result.

## 6. Compose and extend the boundary

Clients should discover first, bind a request to the published schema, validate the response envelope, and carry only
canonical references into later calls. A new tool requires a deterministic research service, normalized request and
response models, ownership and side-effect metadata, a default-off gate for mutations, server registration tests, and
updates to the catalogue and contract page.

Continue with [Tool Contracts](contracts.md) and the [architecture](architecture.md), then the
[`trader_agents` tutorial](../../trader_agents/docs/tutorial.md) for model-selected tool use.
