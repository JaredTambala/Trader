"""Architecture tests for deterministic core calculations.

Subject: Separation of pure runtime, cycle, broker, market-data, and backtest modules from effects.
Level: Core package architecture contract.
Collaborators: Real core source files inspected as text; no runtime process or external service.
Guarantees: Deterministic modules remain free of clocks, logging, persistence, and adapter construction.
Non-goals: Numerical correctness, adapter behavior, and end-to-end runtime execution.
"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_runtime_pure_modules_do_not_use_runtime_side_effects() -> None:
    """Keep runtime payload calculations separate from worker and I/O shells."""
    pure_modules = [PROJECT_ROOT / 'src/trader/runtime/metrics_core.py', PROJECT_ROOT / 'src/trader/runtime/order_recovery.py']
    forbidden_snippets = ('import logging', 'datetime.now', 'time.sleep', 'threading', 'record_event(', '.cursor(', 'connection(', '.open(')
    offenders: list[str] = []
    for path in pure_modules:
        text = path.read_text(encoding='utf-8')
        for snippet in forbidden_snippets:
            if snippet in text:
                offenders.append(f'{path.relative_to(PROJECT_ROOT)} contains {snippet!r}')
    assert offenders == []


def test_runtime_status_payloads_do_not_use_runtime_side_effects() -> None:
    """Keep operator status payload shaping deterministic and side-effect free."""
    text = (PROJECT_ROOT / 'src/trader/runtime/status_payloads.py').read_text(encoding='utf-8')
    forbidden_snippets = ('import logging', 'datetime.now', 'record_event(', '.cursor(', 'connection(', '.open(')
    offenders = [snippet for snippet in forbidden_snippets if snippet in text]
    assert offenders == []


def test_cycle_pure_modules_do_not_use_runtime_side_effects() -> None:
    """Keep cycle planning and payload modules separate from recording shells."""
    pure_modules = [PROJECT_ROOT / 'src/trader/cycle/broker_state.py', PROJECT_ROOT / 'src/trader/cycle/lifecycle.py', PROJECT_ROOT / 'src/trader/cycle/market_data.py', PROJECT_ROOT / 'src/trader/cycle/metrics.py', PROJECT_ROOT / 'src/trader/cycle/order_state.py', PROJECT_ROOT / 'src/trader/cycle/orders.py', PROJECT_ROOT / 'src/trader/cycle/portfolio_updates.py', PROJECT_ROOT / 'src/trader/cycle/risk.py', PROJECT_ROOT / 'src/trader/cycle/stream.py']
    forbidden_snippets = ('import logging', 'datetime.now', 'record_event(', '.cursor(', 'connection(', '.open(')
    offenders: list[str] = []
    for path in pure_modules:
        text = path.read_text(encoding='utf-8')
        for snippet in forbidden_snippets:
            if snippet in text:
                offenders.append(f'{path.relative_to(PROJECT_ROOT)} contains {snippet!r}')
    assert offenders == []


def test_broker_pure_modules_do_not_use_runtime_side_effects() -> None:
    """Keep broker execution payload logic separate from broker adapters."""
    pure_modules = [PROJECT_ROOT / 'src/trader/broker/alpaca_domain.py', PROJECT_ROOT / 'src/trader/broker/internal_execution.py']
    forbidden_snippets = ('import logging', 'datetime.now', 'time.sleep', 'random.', 'uuid.', 'record_event(', '.cursor(', 'connection(', '.open(')
    offenders: list[str] = []
    for path in pure_modules:
        text = path.read_text(encoding='utf-8')
        for snippet in forbidden_snippets:
            if snippet in text:
                offenders.append(f'{path.relative_to(PROJECT_ROOT)} contains {snippet!r}')
    assert offenders == []


def test_market_data_pure_modules_do_not_use_runtime_side_effects() -> None:
    """Keep market-data query and quality calculations separate from I/O shells."""
    pure_modules = [PROJECT_ROOT / 'src/trader/market_data/alpaca_payloads.py', PROJECT_ROOT / 'src/trader/market_data/backfill_payloads.py', PROJECT_ROOT / 'src/trader/market_data/query_domain.py', PROJECT_ROOT / 'src/trader/market_data/query_sql.py', PROJECT_ROOT / 'src/trader/market_data/quality_config.py', PROJECT_ROOT / 'src/trader/market_data/quality_gaps.py', PROJECT_ROOT / 'src/trader/market_data/quality_reports.py', PROJECT_ROOT / 'src/trader/market_data/quality_summary.py']
    forbidden_snippets = ('import logging', 'datetime.now', 'record_event(', '.cursor(', 'connection(', '.open(', 'write_text(', 'build_event_store', 'fetch_bar_timestamps(')
    offenders: list[str] = []
    for path in pure_modules:
        text = path.read_text(encoding='utf-8')
        for snippet in forbidden_snippets:
            if snippet in text:
                offenders.append(f'{path.relative_to(PROJECT_ROOT)} contains {snippet!r}')
    assert offenders == []


def test_backtest_portfolio_core_does_not_use_runtime_side_effects() -> None:
    """Keep backtest portfolio calculations separate from persistence and data fetches."""
    text = (PROJECT_ROOT / 'src/trader/backtest/portfolio_core.py').read_text(encoding='utf-8')
    forbidden_snippets = ('import logging', 'datetime.now', 'record_event(', '.cursor(', 'connection(', '.open(', '_fetch_')
    offenders = [snippet for snippet in forbidden_snippets if snippet in text]
    assert offenders == []


def test_backtest_data_queries_do_not_use_runtime_side_effects() -> None:
    """Keep backtest market-data query shaping separate from event-store fetches."""
    text = (PROJECT_ROOT / 'src/trader/backtest/data_queries.py').read_text(encoding='utf-8')
    forbidden_snippets = ('import logging', 'datetime.now', 'record_event(', '.cursor(', 'connection(', '.open(', '_fetch_')
    offenders = [snippet for snippet in forbidden_snippets if snippet in text]
    assert offenders == []


def test_backtest_export_payloads_do_not_use_runtime_side_effects() -> None:
    """Keep backtest serialization and CSV row shaping separate from file writes."""
    text = (PROJECT_ROOT / 'src/trader/backtest/export_payloads.py').read_text(encoding='utf-8')
    forbidden_snippets = ('import logging', 'datetime.now', 'record_event(', '.cursor(', 'connection(', '.open(', 'write_text(')
    offenders = [snippet for snippet in forbidden_snippets if snippet in text]
    assert offenders == []


def test_backtest_persistence_payloads_do_not_use_runtime_side_effects() -> None:
    """Keep backtest persistence payload shaping separate from event-store writes."""
    text = (PROJECT_ROOT / 'src/trader/backtest/persistence_payloads.py').read_text(encoding='utf-8')
    forbidden_snippets = ('import logging', 'datetime.now', 'record_event(', '.cursor(', 'connection(', '.open(', '_fetch_')
    offenders = [snippet for snippet in forbidden_snippets if snippet in text]
    assert offenders == []


def test_backtest_result_builders_do_not_use_runtime_side_effects() -> None:
    """Keep backtest result construction separate from logging and persistence."""
    text = (PROJECT_ROOT / 'src/trader/backtest/result_builders.py').read_text(encoding='utf-8')
    forbidden_snippets = ('import logging', 'datetime.now', 'record_event(', '.cursor(', 'connection(', '.open(', '_fetch_')
    offenders = [snippet for snippet in forbidden_snippets if snippet in text]
    assert offenders == []


def test_backtest_runtime_planning_does_not_use_runtime_side_effects() -> None:
    """Keep backtest config and replay planning separate from adapters."""
    text = (PROJECT_ROOT / 'src/trader/backtest/runtime_planning.py').read_text(encoding='utf-8')
    forbidden_snippets = ('import logging', 'datetime.now', 'record_event(', '.cursor(', 'connection(', '.open(', 'InternalPaperBroker', '_cycle_log_suppression')
    offenders = [snippet for snippet in forbidden_snippets if snippet in text]
    assert offenders == []


def test_backtest_pure_modules_do_not_use_runtime_side_effects() -> None:
    """Keep backtest calculations, payloads, and planning free of side effects."""
    pure_modules = [PROJECT_ROOT / 'src/trader/backtest/benchmark.py', PROJECT_ROOT / 'src/trader/backtest/data_queries.py', PROJECT_ROOT / 'src/trader/backtest/export_payloads.py', PROJECT_ROOT / 'src/trader/backtest/performance.py', PROJECT_ROOT / 'src/trader/backtest/persistence_payloads.py', PROJECT_ROOT / 'src/trader/backtest/portfolio_core.py', PROJECT_ROOT / 'src/trader/backtest/replay.py', PROJECT_ROOT / 'src/trader/backtest/result_builders.py', PROJECT_ROOT / 'src/trader/backtest/runtime_planning.py', PROJECT_ROOT / 'src/trader/backtest/trade_accounting.py']
    forbidden_snippets = ('import logging', 'datetime.now', 'record_event(', '.cursor(', 'connection(', '.open(', '_fetch_', 'write_text(', 'InternalPaperBroker', '_cycle_log_suppression')
    offenders: list[str] = []
    for path in pure_modules:
        text = path.read_text(encoding='utf-8')
        for snippet in forbidden_snippets:
            if snippet in text:
                offenders.append(f'{path.relative_to(PROJECT_ROOT)} contains {snippet!r}')
    assert offenders == []
