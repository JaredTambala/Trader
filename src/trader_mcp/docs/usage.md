# MCP Usage Reference

## Entrypoints

- `python -m trader_mcp.runtime.server --env-path PATH`: run the local stdio server.
- `trader_mcp.runtime.server.create_server(...)`: compose a server in trusted application/test code.
- `trader_mcp.catalogue.policy.load_local_environment(path)`: parse and normalize server policy.
- `trader_mcp.protocol.contracts`: inspect or construct the stable envelope.

`create_server` accepts provider-neutral overrides for controlled tests and embedding. When an override is absent,
`trader_mcp.runtime.composition` selects the concrete implementation and returns it through a typed runtime-dependency
bundle. Capability modules must accept the injected port, registry, policy, or factory; they must not import a concrete
provider to manufacture their own fallback.

The public path is intentionally layered:

| Need | Use | Why |
| --- | --- | --- |
| deterministic research behavior | `trader_research` facade | owns validation, artifacts, and domain semantics |
| tool discovery and policy | `trader_mcp.catalogue` | describes ownership, schemas, gates, and side effects |
| an MCP call | registered adapter under `trader_mcp.tools` | normalizes JSON and preserves the service result |
| local process composition | `trader_mcp.runtime` | selects stores, providers, and stdio lifecycle |

## Server lifecycle

The client owns the subprocess and MCP session. Initialize once, discover tools, make bounded calls, and close the
session cleanly. The agent runtime uses a persistent stdio client so one specialist turn does not spawn a server per
tool call.

The server logs bounded lifecycle events to `stderr`. `TRADER_MCP_LOG_LEVEL` accepts `INFO` (default) or `DEBUG`, and
`TRADER_MCP_LOG_FORMAT` accepts `human` (default) or `json`. `TRADER_MCP_SERVER_ROLE` labels concurrent subprocesses;
the agent runtime assigns it automatically. Never redirect MCP diagnostic output into protocol `stdout`.

At call time, inspect both layers of failure: an MCP `isError` can report transport or adapter failure, while an
envelope with `ok=false` reports a structured application failure. A successful envelope can still contain warnings or
partial evidence that must be handled by the caller.

| Situation | Meaning | Caller action |
| --- | --- | --- |
| tool is absent | registration gate or dependency is unavailable | inspect config and stop; do not invent a fallback |
| `isError=true` | MCP or adapter call failed | preserve the transport error and reconnect or inspect policy |
| `isError=false`, `ok=false` | service rejected or could not complete the request | inspect structured errors and change the request or reconcile |
| `ok=true` with warnings | operation completed with declared caveats | carry warnings with the artifact refs and review them |
| lost mutation response | terminal state is unknown | read by stable identity before retrying |

## Adding a tool

1. Add deterministic behavior to the owning `trader_research` context.
2. Define the MCP name, public description, input schema, owner, side effect, and capability flag.
3. Register an adapter that normalizes inputs and wraps the service result without changing semantics.
4. Update [Tools](tools.md) and [Contracts](contracts.md).
5. Test direct service behavior, envelope mapping, registration policy, stdio transport, and role allowlists where the
   tool is exposed to an agent.

Keep catalogue, contracts, and package documentation synchronized. A description that promises a capability the policy
cannot register is a documentation bug as well as a usability bug.

## Prohibited shortcuts

Do not expose raw SQL, arbitrary host command execution, filesystem escape, credentials, broker mutation, hidden model
reasoning, or unbounded provider operations. Do not return a database row as an undocumented schema. Do not let tool
descriptions promise capability that environment policy can never register. Do not import `trader_agents`, construct
an LLM client, or place a model call inside a tool adapter. Model-directed authoring belongs to an agent using bounded
Coding Workspace and independent admission tools.
