# MCP Tutorial

This tutorial begins with the public envelope offline, then shows how to inspect the real server. It does not invoke a
mutating tool. The server is a transport boundary around deterministic research services, so the client should learn
the catalogue and validate evidence at every call.

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

The envelope separates four things that are easy to confuse: `ok` describes the service outcome, `agent_owner` names
the owning capability, `side_effect` describes what the operation may change, and `artifacts` names durable evidence.
None of these fields says that a scientific conclusion is correct.

## 2. Configure a local read-only server

Copy the repository example environment, keep every mutation flag false, and point it at a deliberate artifact root.
The real parser test in `tests/trader_mcp/catalogue_policy/test_environment_and_registration.py` validates the
environment boundary.

<!-- verified: integration:mcp tests/trader_mcp/catalogue_policy/test_environment_and_registration.py -->
```bash
uv run python -m trader_mcp.runtime.server --env-path local.env
```

The process speaks MCP over stdio. Do not write logs or prompts to stdout; stdout is transport-owned.

The process has two channels with different owners:

```text
stdout -> JSON-RPC / MCP protocol only
stderr -> bounded INFO or DEBUG lifecycle records
```

Set `TRADER_MCP_SERVER_ROLE` when inspecting concurrent processes so the diagnostic stream identifies which role made
each call. The role label does not replace the agent's allowlist or session policy.

## 3. Discover before calling

An MCP client initializes the session, lists tools, and inspects their schemas. Tool availability reflects environment
policy and configured adapters. The server's full catalogue is not automatically the current agent's catalogue.

Discovery is a capability check, not an authorization shortcut. A disabled flag removes a tool from registration; a
registered tool still has to pass role, scope, approval, budget, and state checks in the caller and service.

## 4. Call and validate

Provide schema-valid JSON, inspect `isError` at the MCP layer, then validate the returned envelope. Check `ok`, errors,
warnings, artifacts, command, owner, side effect, and schema version. Re-read canonical artifact references before using
them for a later mutation or conclusion.

For a lost response, use the operation or artifact identity and a read capability to reconcile before retrying. A
transport error is not evidence that a mutating service failed.

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
