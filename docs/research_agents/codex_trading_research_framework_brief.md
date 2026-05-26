# Trading Research Agent Framework: Codex Implementation Brief

## Purpose

Build a focused agentic research layer on top of the existing trading platform. The goal is not to create a generic agent framework or a detailed database of every LLM/tool interaction. The goal is to let the user state a trading hypothesis in natural language and have the system rapidly test, stress, falsify, and report on that hypothesis using deterministic platform tools.

The key product experience should be:

```text
User: Test whether a short-term mean-reversion strategy on liquid US equities works on 1-minute bars from January to March 2025. Use realistic slippage and fees. Tell me whether the idea survives robustness testing.

System:
1. Clarifies the hypothesis only when necessary.
2. Checks whether the required data exists.
3. Ingests missing data if permitted.
4. Creates or selects a strategy implementation.
5. Runs a reproducible backtest.
6. Runs a robustness battery.
7. Produces a structured research report with a verdict: rejected, inconclusive, promising, or paper-trade candidate.
```

## Executive recommendation

Treat this as a **research experiment workflow**, not as a general-purpose autonomous agent system.

The right abstraction is:

```text
Research Question
  -> Experiment Plan
  -> Data Availability Check
  -> Strategy Candidate
  -> Baseline Backtest
  -> Robustness Suite
  -> Failure Analysis
  -> Research Report
  -> Optional Human-Approved Paper-Trading Promotion
```

The current direction of recording detailed tool-call schemas and raw LLM interaction payloads in Postgres is likely overbuilt for the first useful version. Keep observability and tracing, but do not make agent internals the core product model. The platform should persist research artefacts that make experiments reproducible and reviewable.

## Design principle

The trading platform should remain deterministic. The LLM should orchestrate, plan, write constrained strategy code when necessary, and interpret results. It should not be allowed to freely operate the database or place trades.

```text
The LLM decides:
- what experiment should be run
- what hypothesis is being tested
- what strategy candidate should be proposed
- which robustness tests are relevant
- how to interpret the resulting evidence

The platform owns:
- data ingestion and data quality
- market data versioning
- strategy validation
- backtest execution
- fills, slippage, fees, and risk simulation
- metrics calculation
- result persistence
- deployment/promotion gates
```

## Non-goals for the first implementation

Do not build these first:

- A generic multi-agent chat system.
- A database table for every raw LLM message and tool-call payload.
- An agent that has direct SQL write access.
- Live-trading deployment from a natural-language prompt.
- Automatic alpha optimization that keeps searching until it finds something that appears to work.
- A complex MCP server before the internal platform tool interface has stabilized.
- A full LangGraph workflow unless the first vertical slice genuinely needs long-running checkpointed graph execution.

Do build these first:

- One reliable research experiment runner.
- A small set of high-level platform tools.
- A reproducible experiment record.
- A baseline backtest plus robustness suite.
- A structured report that is skeptical by default.

## Recommended stack

### First vertical slice

Use the existing Python/Postgres trading platform, and add:

- **Pydantic schemas** for experiment plans, tool inputs, tool outputs, report sections, and verdicts.
- **A normal Python `ResearchExperimentRunner` service** that coordinates the workflow.
- **OpenAI Agents SDK** for LLM orchestration, structured outputs, tool calling, handoffs where useful, guardrails, and tracing.
- **Existing platform services** for data, strategies, backtests, metrics, and risk.
- **Postgres only for durable research artefacts**, not for every agent scratchpad event.

### Later, only if needed

Add these when there is a clear reason:

- **LangGraph** if the workflow needs durable graph execution, checkpoints, human-in-the-loop pauses, or resumability across long-running sessions.
- **MCP** if platform tools should be reusable by Codex, ChatGPT, Claude, or other agent clients through a standard interface.
- **Codex-as-tool via MCP** only if the runtime research agent needs to delegate repository-scoped coding work to Codex. Do not make this a prerequisite for the first vertical slice.

## Codex-specific guidance

Codex should be used primarily to implement this system inside the repository. The runtime research agent does not need to be Codex itself.

Codex should:

1. Inspect the existing platform structure first.
2. Reuse existing backtest, strategy, data, risk, and Alpaca modules.
3. Avoid creating a parallel agent-only database model.
4. Build the smallest useful vertical slice.
5. Add tests around the runner, robustness calculations, and report generation.
6. Keep live trading out of scope unless explicitly requested later.

## Proposed repository structure

Adapt this to the existing codebase. Do not force this layout if the project already has clear conventions.

```text
research/
  __init__.py
  domain.py              # Experiment, plan, verdict, result schemas
  runner.py              # ResearchExperimentRunner orchestration
  planner.py             # Convert user prompt -> ExperimentPlan
  tools.py               # High-level platform tool wrappers
  robustness.py          # Robustness suite orchestration and metrics
  attribution.py         # PnL and return-source analysis
  reports.py             # Markdown/JSON report generation
  promotion.py           # Human-approved paper-trading gate, future phase

agents/
  __init__.py
  research_orchestrator.py
  strategy_author.py
  skeptic.py
  reporter.py

strategies/
  generated/
    .gitkeep             # Optional; generated candidate strategies live here

tests/
  research/
    test_experiment_runner.py
    test_robustness.py
    test_reports.py
    test_strategy_validation.py
```

## Central domain abstraction: Experiment

Introduce one core research concept: `Experiment`.

An experiment is the durable record of a trading hypothesis and the evidence gathered against it.

Minimum fields:

```text
experiment
- id
- created_at
- status
- research_question
- hypothesis
- universe
- timeframe
- start_at
- end_at
- data_requirements
- data_snapshot_id / data_version / data_coverage_summary
- strategy_candidate_id
- strategy_code_hash
- strategy_parameters
- baseline_backtest_id
- robustness_suite_id
- final_verdict
- final_confidence
- report_markdown
- trace_id / external_trace_reference, optional
```

Useful child records:

```text
strategy_candidate
- id
- experiment_id
- name
- strategy_type
- natural_language_spec
- code_path
- code_hash
- parameters
- validation_status
- validation_errors

backtest_run
- id
- experiment_id
- strategy_candidate_id
- config_json
- data_snapshot_id
- start_at
- end_at
- metrics_json
- trade_ledger_reference
- equity_curve_reference
- status

robustness_run
- id
- experiment_id
- baseline_backtest_id
- suite_config_json
- results_json
- verdict
- status

research_report
- id
- experiment_id
- markdown
- json_summary
- created_at
```

Avoid persisting raw agent conversation state unless there is a clear compliance or debugging need. If tracing is available from the agent framework, store only the trace identifier and the durable experiment artefacts.

## High-level platform tools

The agent should call a small set of high-level tools. Each tool should be implemented as a normal deterministic Python function or service method. These tools should wrap existing platform capabilities.

### Data tools

```text
get_data_inventory(symbols, timeframe, start_at, end_at) -> DataInventory
```

Returns coverage, gaps, data source, bar counts, and quality warnings.

```text
ensure_market_data(symbols, timeframe, start_at, end_at, source="alpaca") -> DataSnapshot
```

Ingests or verifies market data. Should never silently use incomplete data.

```text
summarize_data_quality(data_snapshot_id) -> DataQualityReport
```

Reports missing bars, duplicate bars, suspicious prices, timezone/calendar issues, corporate-action caveats, and symbol-level coverage.

### Strategy tools

```text
list_strategy_templates() -> list[StrategyTemplate]
```

Returns existing strategy templates and interfaces.

```text
create_strategy_candidate(experiment_id, strategy_spec) -> StrategyCandidate
```

Creates a candidate strategy from a structured spec. It may generate code, but the generated code must be validated before use.

```text
validate_strategy_candidate(strategy_candidate_id) -> StrategyValidationResult
```

Checks that the strategy implements the expected interface, has no forbidden imports, does not access live trading APIs, does not access future data, and can run on a small deterministic fixture.

### Backtest tools

```text
run_backtest(experiment_id, strategy_candidate_id, data_snapshot_id, backtest_config) -> BacktestRun
```

Runs the baseline backtest with explicit fees, slippage, fill assumptions, risk settings, and execution constraints.

```text
get_backtest_results(backtest_run_id) -> BacktestResult
```

Returns metrics, equity curve reference, trade ledger reference, exposure, turnover, drawdowns, and warnings.

### Robustness tools

```text
run_robustness_suite(experiment_id, baseline_backtest_id, robustness_config) -> RobustnessRun
```

Runs a configured set of stress tests and returns a structured result.

```text
analyze_return_attribution(backtest_run_id) -> ReturnAttribution
```

Explains where returns came from: symbols, time periods, trades, parameter choices, market regimes, long/short side, and outlier events.

### Report tools

```text
generate_research_report(experiment_id) -> ResearchReport
```

Creates the final Markdown and JSON report. The report should be skeptical and evidence-based.

## Agent roles

Start with a single orchestrator agent if possible. Add specialized agents only if they reduce confusion.

Potential roles:

```text
Research Orchestrator
- Owns the workflow.
- Converts user intent into an experiment plan.
- Calls the deterministic platform tools.
- Decides whether enough evidence exists for a verdict.

Strategy Author
- Writes or adapts strategy code from a constrained spec.
- Must obey the existing strategy interface.
- Must not bypass validation.

Skeptic / Robustness Analyst
- Tries to falsify the result.
- Looks for leakage, concentration, parameter fragility, slippage sensitivity, and regime dependence.

Reporter
- Produces a concise research report.
- Separates evidence from speculation.
```

These roles do not necessarily need separate services or database tables. They can be separate prompts, functions, or handoffs in the agent framework.

## Experiment workflow

The runner should implement this sequence:

```text
1. Receive natural-language research request.
2. Convert request to structured ExperimentPlan.
3. Create Experiment record.
4. Check data requirements.
5. Ingest or reject if required data is unavailable.
6. Create or select StrategyCandidate.
7. Validate StrategyCandidate.
8. Run baseline backtest.
9. Compute baseline metrics.
10. Run robustness suite.
11. Analyze return attribution and failure modes.
12. Generate final report.
13. Store verdict and report.
14. Return report to user.
```

The workflow should fail closed. If data is incomplete, strategy validation fails, or the backtest result is not reproducible, the experiment should produce a report explaining why the hypothesis could not be evaluated.

## Experiment plan schema

Use a structured schema similar to this. Adapt naming to project conventions.

```python
class ExperimentPlan(BaseModel):
    research_question: str
    hypothesis: str
    universe: list[str]
    timeframe: str
    start_at: datetime
    end_at: datetime
    strategy_intent: str
    strategy_family: Literal[
        "mean_reversion",
        "momentum",
        "breakout",
        "pairs",
        "stat_arb",
        "custom"
    ]
    required_data: list[DataRequirement]
    backtest_config: BacktestConfig
    robustness_config: RobustnessConfig
    success_criteria: SuccessCriteria | None = None
    notes: list[str] = []
```

The model should prefer explicit values. Do not let missing defaults create misleading experiments. If the user omits something important, use conservative defaults and state them in the report.

## Robustness suite

The core purpose of this system is falsification. The robustness suite should try to kill weak alpha quickly.

Minimum tests:

### 1. Slippage sensitivity

Run the same strategy with baseline, 2x, and 5x slippage. The report should show whether the edge disappears under realistic execution assumptions.

### 2. Fee sensitivity

Run baseline and elevated fee assumptions. This is especially important for high-turnover strategies.

### 3. Chronological split

Split the test window into at least two chronological periods. The strategy should not rely entirely on one subperiod.

### 4. Symbol-level concentration

Report PnL by symbol. Highlight if a small number of symbols explains most of the result.

### 5. Trade-level concentration

Report the share of PnL from the top 1, 5, and 10 trades. Highlight if one outlier trade explains the strategy.

### 6. Day/week/month concentration

Report whether a small number of days or weeks explains the majority of returns.

### 7. Parameter perturbation

Nudge key parameters around the proposed values. A strategy that only works at one sharp parameter value should be considered fragile.

### 8. Turnover and capacity sanity

Report trade count, turnover, average holding period, average notional, and whether the assumed execution is plausible.

### 9. Drawdown and tail risk

Report max drawdown, worst day, worst week, downside volatility, and recovery behavior.

### 10. Data leakage checks

Check for lookahead, improper bar-close usage, use of future data, accidental survivorship assumptions, and timestamp/calendar errors.

## Default verdict logic

The report should not simply ask, “Was the backtest profitable?” It should ask, “What evidence would make us reject this idea?”

Suggested verdicts:

```text
rejected
- Baseline fails, or robustness tests destroy the edge, or data/validation issues invalidate the test.

inconclusive
- Baseline is weak or data is insufficient, but there is not enough evidence to reject cleanly.

promising_but_fragile
- Baseline works, but robustness, concentration, turnover, or regime sensitivity creates serious concern.

paper_trade_candidate
- Baseline works, robustness is acceptable, no obvious leakage is detected, and operational assumptions are plausible.
```

For the first version, set a high bar for `paper_trade_candidate`. The system should mostly reject ideas.

## Research report template

Every completed experiment should produce a report with this structure:

```text
# Research Report: <experiment title>

## Verdict
- Verdict: rejected | inconclusive | promising_but_fragile | paper_trade_candidate
- Confidence: low | medium | high
- One-line reason

## Hypothesis Tested
- Research question
- Strategy idea
- Universe
- Timeframe
- Assumptions

## Data Used
- Symbols
- Bar timeframe
- Start/end
- Data source
- Coverage summary
- Known data-quality warnings

## Strategy Candidate
- Strategy name
- Strategy family
- Parameters
- Code path/hash
- Validation status

## Baseline Backtest
- Total return
- Annualized return, if applicable
- Volatility
- Sharpe/Sortino, if implemented
- Max drawdown
- Win rate
- Average win/loss
- Trade count
- Turnover
- Exposure
- Fees and slippage assumptions

## Return Attribution
- PnL by symbol
- PnL by period
- PnL by long/short side, if relevant
- Top winning and losing trades
- Concentration warnings

## Robustness Results
- Slippage sensitivity
- Fee sensitivity
- Chronological split
- Parameter perturbation
- Symbol leave-one-out, if applicable
- Regime or subperiod analysis, if implemented

## Failure Analysis
- What would make this strategy fail?
- Is the result explained by a small number of trades/symbols/days?
- Does the strategy survive realistic execution costs?
- Are there leakage or data-quality concerns?

## Decision
- Reject / revisit / run next experiment / paper-trade candidate
- Required follow-up before any deployment
```

## Persistence policy

Persist:

- Experiment plan.
- Data snapshot or data coverage reference.
- Strategy candidate metadata.
- Strategy code path and hash.
- Backtest configuration.
- Backtest metrics.
- Robustness suite configuration and results.
- Research report.
- Final verdict.
- Optional external trace identifier.

Do not initially persist:

- Every raw LLM message.
- Every internal agent routing decision.
- Every tool-call JSON blob.
- Chain-of-thought or hidden reasoning.
- Large intermediate payloads that can be regenerated from deterministic artefacts.

If debugging requires raw traces, rely on the agent framework's tracing first. Add custom persistence only when a concrete need appears.

## Safety and deployment boundaries

The research agent must not be able to place live orders.

Promotion to paper trading should require:

1. Human approval.
2. Existing risk manager configuration.
3. Explicit deployment config.
4. A report explaining why the strategy is being promoted.
5. A record of the exact strategy version and parameters.

Live deployment should remain out of scope for the first version.

## Implementation plan for Codex

### Phase 0: Repository reconnaissance

Codex should inspect the repository and identify:

- Existing strategy interface.
- Existing backtest runner.
- Existing risk manager abstractions.
- Existing market data storage and ingestion services.
- Existing result/metric models.
- Existing CLI, API, or service entry points.
- Existing tests and test commands.

Do not write new architecture until this inventory is complete.

### Phase 1: Minimal research domain model

Implement minimal schemas/classes for:

- `ExperimentPlan`
- `Experiment`
- `StrategyCandidate`
- `BacktestRun`
- `RobustnessRun`
- `ResearchReport`
- `ResearchVerdict`

Use existing ORM patterns if present. If there is no clear ORM pattern, start with Pydantic/domain objects and a thin persistence adapter.

### Phase 2: Platform tool wrappers

Create high-level wrappers around existing capabilities:

- `get_data_inventory`
- `ensure_market_data`
- `create_strategy_candidate`
- `validate_strategy_candidate`
- `run_backtest`
- `get_backtest_results`
- `run_robustness_suite`
- `analyze_return_attribution`
- `generate_research_report`

These should be deterministic functions. Do not expose direct SQL tools to the agent.

### Phase 3: Experiment runner

Implement `ResearchExperimentRunner.run(request: str) -> ResearchReport`.

The first version may use a simple rule-based or structured-output planner. It does not need multiple agents if a single orchestrator works.

### Phase 4: Robustness suite

Implement the minimum robustness battery:

- Slippage sensitivity.
- Fee sensitivity.
- Chronological split.
- Symbol-level PnL concentration.
- Trade-level PnL concentration.
- Parameter perturbation where parameters are available.
- Data-quality and leakage warnings.

### Phase 5: Report generation

Generate a Markdown report and a JSON summary. Store both if useful.

The report must include:

- Verdict.
- Hypothesis.
- Data used.
- Strategy candidate.
- Baseline metrics.
- Robustness results.
- Failure analysis.
- Decision and next steps.

### Phase 6: Agent integration

Only after the deterministic runner works, add LLM orchestration.

Use the LLM for:

- Turning natural language into `ExperimentPlan`.
- Drafting constrained strategy specs.
- Producing analysis text from structured metrics.
- Selecting relevant robustness checks.

Do not use the LLM for:

- Calculating metrics.
- Deciding fills.
- Mutating database state directly.
- Bypassing validation.
- Placing orders.

## Acceptance criteria

A first acceptable version should pass these checks:

```text
1. Given a natural-language experiment request, the system creates a structured ExperimentPlan.
2. The system verifies or rejects required market data.
3. The system can use an existing strategy or create a simple generated strategy candidate.
4. The strategy candidate is validated before backtesting.
5. The system runs a baseline backtest through the existing platform.
6. The system runs at least three robustness checks.
7. The system generates a Markdown research report.
8. The report gives a skeptical verdict and explains the evidence.
9. The experiment is reproducible from stored config, data reference, strategy hash, and backtest config.
10. The agent has no direct live-trading capability.
```

## Testing expectations

Codex should add or update tests for:

- Experiment plan parsing.
- Strategy validation failure cases.
- Backtest wrapper integration, using fixtures or mocks if necessary.
- Robustness calculations.
- Return concentration calculations.
- Report rendering.
- Reproducibility metadata.

Test examples:

```text
- A strategy with forbidden imports is rejected.
- A strategy with incomplete data produces an inconclusive/rejected report.
- Increasing slippage reduces reported performance in the robustness suite.
- Concentrated PnL is flagged when the top trade or symbol dominates returns.
- Running the same experiment twice with the same inputs produces the same strategy hash/config references.
```

## Suggested first Codex task prompt

Use this as the next instruction to Codex:

```text
You are working in my trading platform repository. I want you to implement the first vertical slice of a research experiment framework for falsifying trading strategy ideas.

Important constraints:
- Do not build a generic agent framework.
- Do not add database tables for every raw LLM/tool-call payload.
- Do not give the agent direct SQL write access.
- Do not add live trading or deployment functionality.
- Reuse the existing strategy, backtest, risk, market data, and persistence modules where possible.
- Build deterministic platform services first; LLM orchestration can be added after the runner works.

First, inspect the repository and summarize:
1. Existing strategy interface.
2. Existing backtest runner entry points.
3. Existing market data ingestion/storage interfaces.
4. Existing risk manager abstractions.
5. Existing persistence/ORM conventions.
6. Existing test commands.

Then implement a minimal ResearchExperimentRunner that can:
1. Accept a structured or natural-language experiment request.
2. Create an ExperimentPlan.
3. Check data availability.
4. Use an existing strategy or create a simple candidate through the existing strategy interface.
5. Run a baseline backtest.
6. Run a small robustness suite covering slippage sensitivity, fee sensitivity, chronological split, and PnL concentration.
7. Generate a Markdown report with a verdict.

Add tests for the runner, robustness calculations, and report generation. Run the relevant test suite before finishing. Keep the implementation small and idiomatic to this repository.
```

## Suggested AGENTS.md addendum

If the repository has an `AGENTS.md`, merge this into it. If not, create one at the repository root.

```markdown
# Trading Research Agent Instructions

This repository contains a Postgres-backed trading platform with Alpaca integration, strategy definitions, risk managers, market-data ingestion, event-driven processing, and backtesting.

When working on research-agent functionality:

- Prefer deterministic platform services over free-form agent behavior.
- Treat research as an experiment workflow: hypothesis -> data check -> strategy candidate -> backtest -> robustness -> report.
- Do not create database tables for every raw LLM message, internal agent step, or tool-call payload unless explicitly requested.
- Persist experiment plans, data references, strategy code hashes, backtest configs/results, robustness results, and reports.
- Do not give agents direct SQL write access.
- Do not let research agents place live orders.
- Do not promote a strategy to paper trading without an explicit human-approved promotion step.
- Reuse existing strategy, backtest, risk, market data, and persistence modules.
- Add tests for runner behavior, robustness calculations, strategy validation, and report generation.
- Run the repository's relevant tests before finishing.
```

## Sources consulted for technology recommendations

These are implementation references, not hard requirements:

- OpenAI Codex `AGENTS.md` guidance: https://developers.openai.com/codex/guides/agents-md
- OpenAI Codex best practices: https://developers.openai.com/codex/learn/best-practices
- OpenAI Agents SDK: https://openai.github.io/openai-agents-python/agents/
- OpenAI Agents SDK tracing: https://openai.github.io/openai-agents-python/tracing/
- OpenAI Agents SDK MCP support: https://openai.github.io/openai-agents-python/mcp/
- LangGraph overview: https://docs.langchain.com/oss/python/langgraph/overview
- LangGraph graph API: https://docs.langchain.com/oss/python/langgraph/graph-api
- LangGraph persistence: https://docs.langchain.com/oss/python/langgraph/persistence
- Model Context Protocol intro: https://modelcontextprotocol.io/docs/getting-started/intro
- MCP tools specification: https://modelcontextprotocol.io/specification/2025-11-25/server/tools
