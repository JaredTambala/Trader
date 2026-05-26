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
