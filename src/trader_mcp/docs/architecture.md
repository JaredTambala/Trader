# MCP Architecture

## Position in the system

```text
model-backed role -> role-scoped MCP client -> stdio FastMCP server
                    -> transport validation and policy
                    -> trader_research public service
                    -> canonical store / bounded provider adapter / trader core
```

The stdio process is a separate trust boundary. Agent code sends only tool name plus JSON-safe arguments and receives a
public tool envelope. It cannot import an event store, provider adapter, or research service to bypass this boundary.

## Composition

`create_server` receives a resolved `McpEnvironment` and optional providers for tests or controlled embedding. The
composition root builds Postgres, knowledge, data, optimisation, tracking, inference, coding, and validation adapters,
then registers only capabilities admitted by policy. Optional provider imports and secrets remain inside the server.

## Envelope

Every research result is wrapped as `ToolEnvelope` with `ok`, command, agent owner, side-effect classification, schema
version, generated timestamp, data, artifact references, warnings, and structured errors. The adapter does not reinterpret
the application result. Model-facing clients must treat `ok=false`, unknown fields, and schema mismatch explicitly.

## Side effects

Operations are classified as read-only, local mutating, external research mutating, broker read, or broker mutating.
The active research server registers no live broker mutation surface. Environment flags gate optional mutation, but a
flag alone does not grant an agent access: the agent package independently narrows the discovered catalogue by role,
session authority, budgets, and current state.

## Recovery

Read-only calls can be retried within deadlines. Mutating services own stable operation identities and canonical
prepared/terminal evidence. If transport ends after dispatch, the agent reconciles through a read capability; it does
not assume failure and does not automatically repeat the mutation.
