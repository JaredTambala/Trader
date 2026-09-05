# Agent Runtime Tutorial

This tutorial first inspects the admitted runtime definition without starting services. The final step explains the
guarded integration path and its current qualification status.

## 1. Inspect admitted roles

<!-- verified: doctest -->
```pycon
>>> from trader_agents import AgentRole
>>> [role.value for role in AgentRole]
['research_coordinator', 'data_research', 'strategy_engineering']
```

Those are independently programmed model identities. Data and Strategy do not receive the coordinator's full context
or each other's private turn history.

## 2. Inspect the pinned model profile

<!-- verified: doctest -->
```pycon
>>> from trader_agents import development_model_profiles
>>> profiles = development_model_profiles()
>>> manifest = profiles.public_manifest()
>>> manifest["profiles"][0]["provider"]
'ollama'
>>> manifest["profiles"][0]["model"]
'lfm2.5:8b'
>>> manifest["profiles"][0]["thinking"]
False
```

The profile includes an exact model digest, context and output ceilings, temperature, deadline, and provider endpoint.
Session creation pins the profile identity; runtime startup verifies the served Ollama model digest before touching a
checkpoint.

## 3. Inspect a strict model output

The model may propose a tool call, but cannot execute it directly.

<!-- verified: doctest -->
```pycon
>>> from trader_agents import ToolCallProposal
>>> proposal = ToolCallProposal(
...     call_id="inspect-1",
...     tool_name="data_get_inventory",
...     arguments={"symbol": "AAPL", "asset_class": "stocks", "timeframe": "1Hour"},
...     purpose="Determine whether the requested history is already present.",
...     expected_evidence=["dataset coverage"],
... )
>>> proposal.tool_name
'data_get_inventory'
>>> proposal.model_config["extra"]
'forbid'
```

The role policy still checks that this exact tool and scope are allowed, that its transport schema matches discovery,
and that budgets remain before dispatch.

## 4. Understand a real session

An operator creates an immutable research session through MCP. It includes the natural-language brief, structured Data
and Strategy contracts where applicable, authority/approval envelope, budgets, and exact program/model/tool identities.
The coordinator may select only Data, only Strategy, both, or interrupt on material ambiguity. No code prescribes a
fixed phase sequence beyond the safety and evidence invariants described in [Architecture](architecture.md).

## 5. Start, inspect, resume, or cancel

The CLI is an integration surface requiring local Ollama, the stdio MCP server configuration, checkpoint Postgres, and
canonical research Postgres. MLflow tracing is optional when explicitly configured.

<!-- verified: offline-shell tests/cross_package/documentation/test_package_documentation.py::test_declared_shell_examples -->
```bash
trader-agent --log-level INFO --log-format human --help
```

Use the subcommands documented by `--help` to start an exact session reference, inspect its public state, resume an
operator interrupt, or cancel as the owning operator. A new process may perform those lifecycle operations against the
same checkpoints.

## 6. Read a run as it happens

INFO mode narrates session start/recovery, model completion, accepted specialist actions, MCP execution, delegation
joins, evidence review, committed decisions, and the terminal outcome. Every line includes session, branch, role,
program, model profile, catalogue, and process identities. Delegated work additionally includes delegation and attempt
identities, so concurrent Data and Strategy lines remain attributable.

For a terminal and a log that can be queried afterward, use JSON mode and split the streams:

```text
uv run trader-agent --log-level DEBUG --log-format json run \
  --session /absolute/path/to/session.json \
  > result.json 2> agent-events.jsonl
```

The result is the public lifecycle outcome. The event file is diagnostic evidence, not a canonical research artifact.
It never contains raw prompts, model completions, hidden reasoning, source text, credentials, or full MCP payloads.
Warnings and failures remain visible in either threshold.

## 7. Interpret the result honestly

The current implementation passes scripted contract, policy, persistence, security, recovery, isolation, and focused
graph tests. The admitted LFM profile did not pass the material-ambiguity coordinator choice gate, so controlled
behavioral qualification has not run to acceptance. Use the runtime for bounded development/evaluation, not as a
qualified autonomous research service. See [Qualification](qualification.md).

## 8. Extend only through a complete agent boundary

Adding a specialist requires a model program, strict turn/result schemas, authority and tool policy, isolated state,
evidence-return and coordinator-review behavior, termination rules, recovery, traces, and behavioral tests. Start with
[Specialists](specialists.md), then read [Contracts](contracts.md), [MCP Integration](mcp_integration.md), and
[Checkpointing And Recovery](checkpointing_and_recovery.md). Do not create an agent merely to rename a deterministic
execution function.
