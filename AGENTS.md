# Agent Instructions

This file is the repo-level operating guide for AI coding agents working in Trader. It is an instruction router and
checklist, not a replacement for the project documentation.

## System Purpose

Trader is a Postgres-first trading platform for market-data ingestion, strategy/risk execution, backtesting, research
experiments, AI/tool-facing signal discovery, and Alpaca paper-trading operations. Research-agent work is deliberately
outside the live trading hot path: agents produce deterministic, inspectable artifacts and must not place live orders.

Use the existing documentation as the source of truth:

- Product and setup overview: [README.md](README.md)
- Documentation index: [docs/README.md](docs/README.md)
- Core runtime architecture: [docs/core/system_architecture.md](docs/core/system_architecture.md)
- Core platform docs: [docs/core/README.md](docs/core/README.md)
- Research-agent docs: [docs/research_agents/README.md](docs/research_agents/README.md)
- Agent identities and artifact ownership: [docs/research_agents/agent_operating_model.md](docs/research_agents/agent_operating_model.md)
- MCP/tool envelope contracts: [docs/research_agents/tool_contracts.md](docs/research_agents/tool_contracts.md)
- Active research-agent tracker: [plans/mcp_trading_research_tools_plan.md](plans/mcp_trading_research_tools_plan.md)
- Python contributor standard: [docs/python_code_quality.md](docs/python_code_quality.md)

## Package Architecture

- `trader`: core platform only. Market data, event store, brokers, runtime orchestration, strategy/risk interfaces,
  backtesting, metrics, and operator primitives live here. It must not depend on research, MCP, or agent packages.
- `trader_standard`: maintained first-party implementations of platform interfaces, including indicators, signals,
  strategies, and risk managers. It should not own experiment orchestration, MCP schemas, or agent tooling.
- `trader_research`: deterministic research services, research domain models, tool envelopes, data-quality wrappers,
  strategy validation, recommendations, knowledge/method artifacts, diagnostics, and reports.
- `trader_mcp`: MCP server and adapters over `trader_research` services. Keep transport concerns here.
- `trader_agents`: LangGraph identities, state schemas, policy routers, tool allowlists, and graph wiring over MCP
  tools. Agent code should call MCP tools, not platform internals, when a tool exists.

## Agent Definitions

Follow [agent_operating_model.md](docs/research_agents/agent_operating_model.md) for the authoritative boundaries.

- Data Agent: owns symbol discovery, dataset manifests, data inventory, quality reports, and explicit bounded loading
  evidence.
- Quantitative Methods Agent: owns knowledge sources, method cards, method contracts, implementation validation,
  signal diagnostics, multiple-testing reports, and optional kernel/parity artifacts.
- Quant Research Supervisor Agent: coordinates research workflow, consumes specialist artifacts, creates experiment
  plans and recommendations, and preserves specialist ownership.
- ML Agent: owns feature, model, prediction, and drift artifacts.
- Hypothesis Agent: owns hypothesis cards from available ingredients.
- Evaluation Agent: owns skeptical critique and evaluation reports.
- Adversarial Agent: owns robustness and stress-test reports.

No research agent may control live trading, broker mutation, halt clearing, order reconciliation, direct SQL writes, or
raw hidden scratchpad persistence.

## Mandatory SDLC Loop

For every task, do this in order:

1. Read the relevant tracker entry first. For research-agent/MCP work, start with
   [plans/mcp_trading_research_tools_plan.md](plans/mcp_trading_research_tools_plan.md).
2. Identify current status, acceptance criteria, evidence, and active docs before editing.
3. Inspect the change surface with repo searches and nearby code reads. Prefer `rg` and targeted file reads.
4. Plan narrowly around the package boundary and existing patterns.
5. Implement the smallest coherent change. Do not create compatibility layers unless the tracker or user explicitly
   requires them.
6. Test the direct behavior first, then broaden tests when touching shared contracts, MCP registration, agent identity,
   persistence, or package boundaries.
7. Update active documentation and the tracker in the same change when behavior, APIs, artifacts, or status change.
8. Review `git status --short` before staging. Stage only intended files.
9. Commit only when the user asks for a commit, or when an agreed workflow explicitly requires one.

## Python Code Quality

Apply [docs/python_code_quality.md](docs/python_code_quality.md) to all Python changes.

- Normalize request payloads, config, rows, and external responses at boundaries before passing data deeper.
- Use typed value objects or stable plain-data shapes instead of passing partially-normalized dictionaries through core
  logic.
- Keep orchestration functions readable: validate early, name intermediate domain concepts, and move focused behavior
  into small helpers.
- Keep deterministic core logic separate from adapters, persistence, clocks, network calls, brokers, and LLM clients.
- Make failures actionable with clear blockers, warnings, or explicit exceptions carrying useful context.
- Use Google-style docstrings for new or changed public modules, classes, and functions.
- Add comments only for non-obvious invariants, external contracts, or deliberate tradeoffs.
- Scale tests to risk: focused tests for narrow changes; broader suites for shared contracts, package boundaries, MCP,
  persistence, or runtime behavior.

## Documentation And Tracker Rules

- Feature work is not complete until active docs and the active tracker reflect the implementation.
- For research-agent and MCP work, update [plans/mcp_trading_research_tools_plan.md](plans/mcp_trading_research_tools_plan.md)
  whenever status, scope, evidence, or follow-on work changes.
- Update [docs/research_agents/tool_contracts.md](docs/research_agents/tool_contracts.md) when tool inputs, outputs,
  envelopes, side effects, or artifact contracts change.
- Update [docs/research_agents/agent_operating_model.md](docs/research_agents/agent_operating_model.md) when agent
  ownership, boundaries, or allowlists change.
- Update core docs under [docs/core/](docs/core/) when runtime, storage, strategy/risk, market-data, backtest, or
  operator behavior changes.
- Do not create new documents when an existing canonical document can be updated.

## Verification Policy

Use the narrowest checks that prove the change, then broaden when shared surfaces are touched.

- Docs-only root instruction changes: run link/text checks such as
  `rg -n "mcp_trading_research_tools_plan|python_code_quality|agent_operating_model|tool_contracts" AGENTS.md`.
- Python changes: run targeted tests for the changed behavior and `uv run ruff check` on touched Python paths.
- Shared contracts, MCP registration, agent identity, persistence, or package-boundary changes: run the relevant targeted
  suites and consider `uv run pytest -m 'not postgres' -q`.
- Postgres-backed changes: run the relevant `pytest.mark.postgres` tests when local Postgres is available.
- Before final response, report the exact checks run and any checks intentionally skipped.

## Do Not

- Do not implement before checking the tracker and nearby docs.
- Do not commit feature work without docs and tracker updates, unless the final response explicitly explains why no docs
  or tracker change was needed.
- Do not create legacy compatibility imports, shims, or aliases unless explicitly planned.
- Do not bypass MCP/tool boundaries from agent code when a tool exists.
- Do not give agents direct SQL write access, broker mutation, live trading controls, or raw scratchpad persistence.
- Do not persist every LLM message, hidden reasoning trace, or tool-call payload as product state.
- Do not stage or commit unrelated untracked files.
- Do not rewrite or revert user changes unless explicitly requested.

## Before Final Response

Confirm and report:

- The tracker was checked and updated, or why it was not applicable.
- Active docs were updated, or why no docs change was needed.
- Tests/checks were run with exact commands and results.
- `git status --short` was reviewed.
- Remaining untracked or modified files are identified.
