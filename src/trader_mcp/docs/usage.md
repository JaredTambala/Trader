# MCP Usage Reference

## Entrypoints

- `python -m trader_mcp.server --env-path PATH`: run the local stdio server.
- `trader_mcp.server.create_server(...)`: compose a server in trusted application/test code.
- `trader_mcp.environment.load_local_environment(path)`: parse and normalize server policy.
- `trader_mcp.contracts`: inspect or construct the stable envelope.

## Server lifecycle

The client owns the subprocess and MCP session. Initialize once, discover tools, make bounded calls, and close the
session cleanly. The agent runtime uses a persistent stdio client so one specialist turn does not spawn a server per
tool call.

The server logs bounded lifecycle events to `stderr`. `TRADER_MCP_LOG_LEVEL` accepts `INFO` (default) or `DEBUG`, and
`TRADER_MCP_LOG_FORMAT` accepts `human` (default) or `json`. `TRADER_MCP_SERVER_ROLE` labels concurrent subprocesses;
the agent runtime assigns it automatically. Never redirect MCP diagnostic output into protocol `stdout`.

## Adding a tool

1. Add deterministic behavior to the owning `trader_research` context.
2. Define the MCP name, public description, input schema, owner, side effect, and capability flag.
3. Register an adapter that normalizes inputs and wraps the service result without changing semantics.
4. Update [Tools](tools.md) and [Contracts](contracts.md).
5. Test direct service behavior, envelope mapping, registration policy, stdio transport, and role allowlists where the
   tool is exposed to an agent.

## Prohibited shortcuts

Do not expose raw SQL, arbitrary host command execution, filesystem escape, credentials, broker mutation, hidden model
reasoning, or unbounded provider operations. Do not return a database row as an undocumented schema. Do not let tool
descriptions promise capability that environment policy can never register.
