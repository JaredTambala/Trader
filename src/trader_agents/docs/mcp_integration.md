# Agent-To-MCP Integration

The code-side boundary is the `trader_agents.mcp` package: `catalogue.py` describes admitted tools, `policy.py`
authorizes proposals, `runtime.py` binds trusted context and normalizes observations, and `client.py` owns transport.
These modules consume the lower `trader_mcp` catalogue/protocol contracts; `trader_mcp` never imports Agents.

`RoleScopedMcpRuntime` is the sole capability execution route. Before the model sees tools, it intersects the code-owned
catalogue with role policy, session approvals, phase, current lifecycle, and remaining budget. It also loads live MCP
tool descriptions and requires exact compatible schemas.

A model emits `ToolCallProposal`; it never holds a callable tool object. Runtime code binds trusted values the model
must not choose, including build-contract requirements, actor/requester attribution, and replay-safe operation IDs. The
policy returns an `AuthorizedToolCall`, the persistent stdio client dispatches it, and the returned envelope becomes a
bounded `ToolObservation`.

Tool observations retain command, owner, side effect, success, a bounded summary, canonical references, warnings, and
errors. Oversized or sensitive fields do not enter model context or checkpoints. Provider secrets remain in the MCP
server process.

Transport loss after a mutation is an ambiguous state, not proof of failure. The specialist must use a permitted
reconciliation read keyed by the runtime-bound operation ID. Accepted mutations are never replayed solely because a
LangGraph node restarted.
