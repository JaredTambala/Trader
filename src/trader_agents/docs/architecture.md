# Multi-Agent Architecture

## What constitutes an agent

An agent here is not a deterministic workflow wearing an agent name. Each admitted identity has a versioned model
program, exact model profile, bounded public context, strict output schemas, a dynamically narrowed MCP catalogue,
authority rules, budgets, durable state, evidence-return contract, and termination conditions. The model chooses among
permitted actions; code constrains and records those choices.

The system deliberately does not persist or depend on hidden chain-of-thought. Its durable reasoning surface is the
public agenda, tool purposes, evidence summaries and references, issues, specialist returns, coordinator decisions, and
resource usage.

The primary graph implementation is `coordinator.py`; Data and Strategy own their corresponding specialist modules.

## Package composition

`runtime_from_environment` is the production composition root. It resolves and verifies:

- the immutable `ResearchSession` created through the MCP governance surface
- the admitted `ModelProfileRegistry` and `AgentProgramRegistry`
- the exact code-owned `ToolCatalogue`, checked against live MCP discovery
- a provider-neutral `LlmClient` and `StructuredModelRunner`
- one `RoleScopedMcpRuntime` per agent identity
- the Data and Strategy specialist graphs
- the Research Coordinator graph
- a dedicated Postgres LangGraph checkpointer
- an optional redacted MLflow trace sink
- one process-scoped semantic event emitter and configurable `stderr` console sink

These objects are injected into `AgenticResearchRuntime`, which exposes only start, resume, inspect, and cancel lifecycle
operations.

## Dependency direction

```text
operator / CLI
    -> AgenticResearchRuntime
       -> ResearchCoordinator LangGraph
          -> DataResearchAgent LangGraph
          -> StrategyEngineeringAgent LangGraph
       -> StructuredModelRunner -> LLM provider
       -> RoleScopedMcpRuntime -> stdio MCP client -> trader_mcp
       -> LangGraph Postgres checkpointer
       -> redacted trace sink
       -> redacted semantic event sink -> operator stderr

trader_mcp -> trader_research -> trader / trader_standard / provider adapters
```

There is no import path from an agent into `trader`, `trader_standard`, research service internals, event stores, coding
containers, or provider adapters. `trader_agents` imports only the public governance/session values it needs for the
entry contract. All capability calls cross MCP.

## Coordinator graph

The Research Coordinator is the only user-facing model. It delegates bounded tasks to specialists and reviews every
selected return before another shared-state transition.

The coordinator graph uses `AgentCheckpointState` and the following nodes:

```text
START
  -> ensure_session
  -> interpret_brief
       -> await_operator -> interpret_brief
       -> dispatch_ready_specialists
  -> review_evidence
  -> commit_decision
       -> dispatch_ready_specialists / await_operator / END
```

`ensure_session` verifies immutable session identity and obtains the canonical session. `interpret_brief` asks the
coordinator model for a strict `CoordinatorAgenda`, then deterministic policy validates scope, dependency graph, role
ownership, joins, and available budgets. `dispatch_ready_specialists` computes the ready set and may run independent
tasks concurrently. `review_evidence` receives all joined specialist returns, re-reads their exact canonical references,
and asks the coordinator model for a `CoordinatorDecision`. `commit_decision` checkpoints the validated decision before
recording its append-only canonical receipt, then applies only that accepted transition.

The Coordinator remains the single writer of shared graph state: agenda, branch, and terminal state. Specialists write only their isolated
thread state and domain-owned artifacts through MCP.

## Specialist graphs

Each current specialist is a compact loop over `SpecialistCheckpointState`:

```text
START -> model_tool_step -> model_tool_step ... -> END
```

At each step, the model emits either a typed tool proposal or a typed conclusion. Deterministic code validates the
proposal against role, delegation, phase, exact scope, side effect, approval, budget, tool schema, operation identity,
and lifecycle prerequisites. The normalized observation becomes the next bounded public context. Conclusions are
accepted only when required evidence and terminal invariants are satisfied.

The Data loop discovers/inspects a multi-asset scope, optionally performs admitted backfill, revalidates, and returns
dataset/quality/loading evidence. The Strategy loop searches and compares existing implementations before reuse,
adaptation, or isolated authoring; it packages, validates, and registers exact candidate versions and always destroys
the workspace.

## Parallelism and joins

The scheduler computes tasks whose declared dependencies are satisfied. Disjoint read or mutation scopes can execute
concurrently after a single coordinator transition. Mutation keys serialize work that could affect the same resource.
A hard join waits for all required specialist results before evidence review. A soft join may return control when a
useful completed result exists while retaining unfinished delegation identity for recovery; it never forgets an
in-flight mutation.

Coordinator decisions, approval interrupts, canonical decision receipt mutation, and evidence-dependent stages remain
serialized. Concurrency is an execution optimization, not permission to weaken artifact ownership or review every
selected return.

## Trust transitions

1. Operator input becomes an immutable canonical session with explicit scope, approvals, and budgets.
2. Model JSON is untrusted until strict Pydantic validation and deterministic semantic policy pass.
3. Tool arguments are rebound with trusted scope/operation identities where required.
4. Live MCP discovery is compared with the code-owned catalogue before exposure or execution.
5. MCP envelopes are normalized into bounded `ToolObservation`; raw output and credentials are excluded.
6. Specialist references are re-read from the canonical store by the coordinator.
7. A coordinator decision is checkpointed and recorded canonically before its transition is considered accepted.

## Observability contract

`AgentObservabilityEvent` is the versioned, sink-neutral description of public runtime activity. Event names are a
closed semantic vocabulary, and each name fixes its minimum visibility and authority classification. An adapter cannot
turn a DEBUG event into INFO or label diagnostic activity as a canonical product record. The authority value describes
the state projected by the event—diagnostic activity, recoverable checkpoint state, or an already accepted canonical
record. The event itself is never product truth.

Every event carries session, branch, role, agent-program, model-profile, tool-catalogue, and process identities. Delegation
and attempt identities occur as a pair; model and MCP stages require a call identity; checkpoint, phase, and committed
decision events require the accepted transition sequence. Event sequence is strictly increasing within one process.
Fresh processes may start their own sequence, so cross-process lineage uses stable correlation identities and canonical
transition sequence instead of inventing a global log order.

The vocabulary deliberately separates these trust stages:

1. a provider response was received;
2. its declared output schema was accepted or rejected;
3. the typed action passed or failed domain admission;
4. a tool proposal passed or failed deterministic policy authorization;
5. the authorized tool execution started and completed or failed;
6. a terminal coordinator outcome was accepted.

This distinction prevents a model response, a schema-valid action, and an authorized side effect from appearing to be
the same fact in logs or traces.

Event fields do not come from generic object dumps. Named projectors expose bounded public summaries for agendas,
specialist turns and returns, MCP proposals and observations, policy outcomes, budgets, checkpoints, coordinator
decisions, and terminal results. Arbitrary tool arguments and observations contribute only allowlisted scalar facts,
identities, counts, and deterministic digests. Recursive validation rejects non-JSON values, oversized values, and
unsafe fields including raw prompts or completions, hidden reasoning, credentials, source text, retrieved chunks, and
raw MCP payloads. Sinks revalidate and detach events at their boundary, and the legacy trace API now uses the same
recursive field validator.

The production composition shares one emitter across the runtime, Coordinator, specialists, structured-model runners,
and role-scoped MCP runtimes. This gives every event a monotonically increasing process-local sequence. The console
sink writes either a concise human line or the exact event JSON to `stderr`; INFO filters DEBUG events but never hides
warnings or errors. No-op and recording sinks remain available for isolated embedding and contract tests. Legacy
MLflow spans continue alongside the semantic stream until approved durable event persistence is implemented.

The three child MCP processes also log their own bounded lifecycle events to inherited `stderr`. Each line carries the
specialist role and a distinct MCP process identity, while MCP protocol JSON-RPC remains isolated on child `stdout`.

## Failure and termination

Provider errors, schema exhaustion, unauthorized calls, scope drift, missing evidence, ambiguous mutation state, budget
exhaustion, repeated low-information transitions, checkpoint identity mismatch, and contaminated evaluation stop or
interrupt the system explicitly. A model cannot convert these failures into success by explanation.

Terminal outcomes include a grounded conclusion, explicit blocked/failed/cancelled result, or a bounded operator
interrupt. A fresh process can resume from public checkpoint state without replaying an accepted mutation.

PostgreSQL checkpoints contain bounded operational state only. Canonical research artifacts and append-only decision
receipts remain in the separate research store.
