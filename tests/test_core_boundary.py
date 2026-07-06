from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import trader
import trader.cycle.state as cycle_state
from trader.config import Config
from trader.cycle import run_cycle
from trader.event_store import NoOpEventStore
from trader.market_data import StaticMarketDataSource, StockBarEvent
from trader.portfolio import Portfolio, PortfolioSnapshot, Position
from trader.risk import RiskContext, RiskManager
from trader.strategies import Strategy
import trader_standard


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class RecordingEventStore(NoOpEventStore):
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def record_event(self, event_type: str, payload: dict[str, object]) -> None:
        self.events.append((event_type, dict(payload)))


class AcceptAllRiskManager(RiskManager):
    def validate(self, orders, context: RiskContext):
        return list(orders)


class BuyOnceStrategy(Strategy):
    @property
    def strategy_id(self) -> str:
        return "buy-once"

    def generate_orders(self, *, run_id, cycle_id, decision_ts, event_store, portfolio):
        return [{"symbol": "AAPL", "side": "buy", "qty": 1.0, "order_type": "market"}]


def _config() -> Config:
    return Config(
        mode="once",
        strategy_type="buy-once",
        strategy_id="buy-once",
        strategy_timeframe="1Min",
        sma_short_window=2,
        sma_long_window=3,
        db_path="",
        event_store="noop",
        market_data_source="noop",
        market_data_asset_class="stocks",
        market_data_stock_feed="iex",
        market_data_symbols=("AAPL",),
        market_data_max_age_seconds=60,
        alpaca_api_key="",
        alpaca_secret_key="",
        alpaca_data_base_url="https://data.alpaca.markets",
        alpaca_base_url="https://paper-api.alpaca.markets",
        pg_dsn="",
        pg_host="",
        pg_port=5432,
        pg_db="",
        pg_user="",
        pg_password="",
        buffered_event_store=False,
        buffer_flush_interval_ms=250,
        buffer_max_batch_size=500,
        buffer_max_queue_size=10000,
        buffer_block_on_full=True,
        log_signal_events=True,
        log_indicator_events=True,
        log_order_events=True,
        log_fill_events=True,
        log_position_snapshots=True,
        broker_type="noop",
    )


def test_trader_core_exports_contracts_not_standard_implementations() -> None:
    assert hasattr(trader, "Strategy")
    assert hasattr(trader, "RiskManager")
    assert hasattr(trader, "BacktestRunner")
    assert not hasattr(trader, "ToggleUnitStrategy")
    assert not hasattr(trader, "NoOpRiskManager")
    assert not hasattr(trader, "build_trend_following_strategy")

    assert hasattr(trader_standard, "ToggleUnitStrategy")
    assert hasattr(trader_standard, "NoOpRiskManager")
    assert hasattr(trader_standard, "build_trend_following_strategy")


def test_trader_root_portfolio_exports_remain_stable() -> None:
    """Keep root portfolio exports stable after internal module splits."""
    assert trader.Portfolio is Portfolio
    assert trader.PortfolioSnapshot is PortfolioSnapshot
    assert trader.Position is Position


def test_runtime_code_uses_explicit_portfolio_snapshot_persistence() -> None:
    """Keep portfolio snapshot writes at an explicit persistence boundary."""
    allowed = {
        PROJECT_ROOT / "src/trader/portfolio/snapshots.py",
    }
    offenders: list[str] = []
    for path in (PROJECT_ROOT / "src/trader").rglob("*.py"):
        if path in allowed:
            continue
        text = path.read_text(encoding="utf-8")
        if "snapshot.persist(event_store)" in text or "snapshot.persist(runtime.event_store)" in text:
            offenders.append(str(path.relative_to(PROJECT_ROOT)))

    assert offenders == []


def test_portfolio_pure_modules_do_not_use_runtime_side_effects() -> None:
    """Keep portfolio calculations free of clocks, logging, and I/O."""
    pure_modules = [
        PROJECT_ROOT / "src/trader/portfolio/models.py",
        PROJECT_ROOT / "src/trader/portfolio/order_inputs.py",
        PROJECT_ROOT / "src/trader/portfolio/order_math.py",
        PROJECT_ROOT / "src/trader/portfolio/reconstruction.py",
        PROJECT_ROOT / "src/trader/portfolio/transitions.py",
    ]
    forbidden_snippets = (
        "import logging",
        "datetime.now",
        "os.environ",
        "record_event(",
        ".cursor(",
        "connection(",
        ".open(",
    )

    offenders: list[str] = []
    for path in pure_modules:
        text = path.read_text(encoding="utf-8")
        for snippet in forbidden_snippets:
            if snippet in text:
                offenders.append(f"{path.relative_to(PROJECT_ROOT)} contains {snippet!r}")

    assert offenders == []


def test_runtime_metrics_core_does_not_use_runtime_side_effects() -> None:
    """Keep runtime metrics calculations separate from the worker shell."""
    text = (PROJECT_ROOT / "src/trader/runtime/metrics_core.py").read_text(encoding="utf-8")
    forbidden_snippets = (
        "import logging",
        "datetime.now",
        "time.sleep",
        "threading",
        "record_event(",
        ".cursor(",
        "connection(",
        ".open(",
    )

    offenders = [snippet for snippet in forbidden_snippets if snippet in text]

    assert offenders == []


def test_runtime_status_payloads_do_not_use_runtime_side_effects() -> None:
    """Keep operator status payload shaping deterministic and side-effect free."""
    text = (PROJECT_ROOT / "src/trader/runtime/status_payloads.py").read_text(encoding="utf-8")
    forbidden_snippets = (
        "import logging",
        "datetime.now",
        "record_event(",
        ".cursor(",
        "connection(",
        ".open(",
    )

    offenders = [snippet for snippet in forbidden_snippets if snippet in text]

    assert offenders == []


def test_cycle_pure_modules_do_not_use_runtime_side_effects() -> None:
    """Keep cycle planning and payload modules separate from recording shells."""
    pure_modules = [
        PROJECT_ROOT / "src/trader/cycle/broker_state.py",
        PROJECT_ROOT / "src/trader/cycle/lifecycle.py",
        PROJECT_ROOT / "src/trader/cycle/market_data.py",
        PROJECT_ROOT / "src/trader/cycle/metrics.py",
        PROJECT_ROOT / "src/trader/cycle/order_state.py",
        PROJECT_ROOT / "src/trader/cycle/orders.py",
        PROJECT_ROOT / "src/trader/cycle/portfolio_updates.py",
        PROJECT_ROOT / "src/trader/cycle/risk.py",
    ]
    forbidden_snippets = (
        "import logging",
        "datetime.now",
        "record_event(",
        ".cursor(",
        "connection(",
        ".open(",
    )

    offenders: list[str] = []
    for path in pure_modules:
        text = path.read_text(encoding="utf-8")
        for snippet in forbidden_snippets:
            if snippet in text:
                offenders.append(f"{path.relative_to(PROJECT_ROOT)} contains {snippet!r}")

    assert offenders == []


def test_market_data_pure_modules_do_not_use_runtime_side_effects() -> None:
    """Keep market-data query and quality calculations separate from I/O shells."""
    pure_modules = [
        PROJECT_ROOT / "src/trader/market_data/alpaca_payloads.py",
        PROJECT_ROOT / "src/trader/market_data/backfill_payloads.py",
        PROJECT_ROOT / "src/trader/market_data/query_domain.py",
        PROJECT_ROOT / "src/trader/market_data/query_sql.py",
        PROJECT_ROOT / "src/trader/market_data/quality_config.py",
        PROJECT_ROOT / "src/trader/market_data/quality_gaps.py",
        PROJECT_ROOT / "src/trader/market_data/quality_reports.py",
        PROJECT_ROOT / "src/trader/market_data/quality_summary.py",
    ]
    forbidden_snippets = (
        "import logging",
        "datetime.now",
        "record_event(",
        ".cursor(",
        "connection(",
        ".open(",
        "write_text(",
        "build_event_store",
        "fetch_bar_timestamps(",
    )

    offenders: list[str] = []
    for path in pure_modules:
        text = path.read_text(encoding="utf-8")
        for snippet in forbidden_snippets:
            if snippet in text:
                offenders.append(f"{path.relative_to(PROJECT_ROOT)} contains {snippet!r}")

    assert offenders == []


def test_backtest_portfolio_core_does_not_use_runtime_side_effects() -> None:
    """Keep backtest portfolio calculations separate from persistence and data fetches."""
    text = (PROJECT_ROOT / "src/trader/backtest/portfolio_core.py").read_text(encoding="utf-8")
    forbidden_snippets = (
        "import logging",
        "datetime.now",
        "record_event(",
        ".cursor(",
        "connection(",
        ".open(",
        "_fetch_",
    )

    offenders = [snippet for snippet in forbidden_snippets if snippet in text]

    assert offenders == []


def test_backtest_data_queries_do_not_use_runtime_side_effects() -> None:
    """Keep backtest market-data query shaping separate from event-store fetches."""
    text = (PROJECT_ROOT / "src/trader/backtest/data_queries.py").read_text(encoding="utf-8")
    forbidden_snippets = (
        "import logging",
        "datetime.now",
        "record_event(",
        ".cursor(",
        "connection(",
        ".open(",
        "_fetch_",
    )

    offenders = [snippet for snippet in forbidden_snippets if snippet in text]

    assert offenders == []


def test_backtest_export_payloads_do_not_use_runtime_side_effects() -> None:
    """Keep backtest serialization and CSV row shaping separate from file writes."""
    text = (PROJECT_ROOT / "src/trader/backtest/export_payloads.py").read_text(encoding="utf-8")
    forbidden_snippets = (
        "import logging",
        "datetime.now",
        "record_event(",
        ".cursor(",
        "connection(",
        ".open(",
        "write_text(",
    )

    offenders = [snippet for snippet in forbidden_snippets if snippet in text]

    assert offenders == []


def test_backtest_persistence_payloads_do_not_use_runtime_side_effects() -> None:
    """Keep backtest persistence payload shaping separate from event-store writes."""
    text = (PROJECT_ROOT / "src/trader/backtest/persistence_payloads.py").read_text(encoding="utf-8")
    forbidden_snippets = (
        "import logging",
        "datetime.now",
        "record_event(",
        ".cursor(",
        "connection(",
        ".open(",
        "_fetch_",
    )

    offenders = [snippet for snippet in forbidden_snippets if snippet in text]

    assert offenders == []


def test_backtest_result_builders_do_not_use_runtime_side_effects() -> None:
    """Keep backtest result construction separate from logging and persistence."""
    text = (PROJECT_ROOT / "src/trader/backtest/result_builders.py").read_text(encoding="utf-8")
    forbidden_snippets = (
        "import logging",
        "datetime.now",
        "record_event(",
        ".cursor(",
        "connection(",
        ".open(",
        "_fetch_",
    )

    offenders = [snippet for snippet in forbidden_snippets if snippet in text]

    assert offenders == []


def test_backtest_runtime_planning_does_not_use_runtime_side_effects() -> None:
    """Keep backtest config and replay planning separate from adapters."""
    text = (PROJECT_ROOT / "src/trader/backtest/runtime_planning.py").read_text(encoding="utf-8")
    forbidden_snippets = (
        "import logging",
        "datetime.now",
        "record_event(",
        ".cursor(",
        "connection(",
        ".open(",
        "InternalPaperBroker",
        "_cycle_log_suppression",
    )

    offenders = [snippet for snippet in forbidden_snippets if snippet in text]

    assert offenders == []


def test_backtest_pure_modules_do_not_use_runtime_side_effects() -> None:
    """Keep backtest calculations, payloads, and planning free of side effects."""
    pure_modules = [
        PROJECT_ROOT / "src/trader/backtest/benchmark.py",
        PROJECT_ROOT / "src/trader/backtest/data_queries.py",
        PROJECT_ROOT / "src/trader/backtest/export_payloads.py",
        PROJECT_ROOT / "src/trader/backtest/performance.py",
        PROJECT_ROOT / "src/trader/backtest/persistence_payloads.py",
        PROJECT_ROOT / "src/trader/backtest/portfolio_core.py",
        PROJECT_ROOT / "src/trader/backtest/replay.py",
        PROJECT_ROOT / "src/trader/backtest/result_builders.py",
        PROJECT_ROOT / "src/trader/backtest/runtime_planning.py",
        PROJECT_ROOT / "src/trader/backtest/trade_accounting.py",
    ]
    forbidden_snippets = (
        "import logging",
        "datetime.now",
        "record_event(",
        ".cursor(",
        "connection(",
        ".open(",
        "_fetch_",
        "write_text(",
        "InternalPaperBroker",
        "_cycle_log_suppression",
    )

    offenders: list[str] = []
    for path in pure_modules:
        text = path.read_text(encoding="utf-8")
        for snippet in forbidden_snippets:
            if snippet in text:
                offenders.append(f"{path.relative_to(PROJECT_ROOT)} contains {snippet!r}")

    assert offenders == []


def test_run_cycle_does_not_apply_hidden_open_buy_order_guard(monkeypatch) -> None:
    store = RecordingEventStore()
    decision_ts = datetime.now(timezone.utc)
    market_data = StaticMarketDataSource(
        [
            StockBarEvent(
                symbol="AAPL",
                timeframe="1Min",
                ts=decision_ts,
                ingested_at=decision_ts,
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=10.0,
                trade_count=None,
                vwap=None,
                source="test",
            )
        ]
    )
    existing_open_order = {
        "client_order_id": "existing_open_buy",
        "run_id": "run_existing",
        "cycle_id": "cycle_existing",
        "symbol": "AAPL",
        "side": "buy",
        "qty": 1.0,
        "order_type": "market",
        "status": "submitted",
        "broker_order_id": None,
        "created_at": decision_ts,
    }
    monkeypatch.setattr(
        cycle_state,
        "_load_latest_order_events",
        lambda event_store: [existing_open_order],
    )
    monkeypatch.setattr(cycle_state, "_load_halt_flag", lambda event_store: False)

    result = run_cycle(
        event_store=store,
        strategy=BuyOnceStrategy(),
        risk_manager=AcceptAllRiskManager(),
        market_data_source=market_data,
        config=_config(),
        decision_ts=decision_ts,
        ingest_market_data=False,
        portfolio=Portfolio.empty(cash_balance=1000.0),
    )

    assert result.status == "success"
    order_statuses = [
        payload["status"]
        for event_type, payload in store.events
        if event_type == "order_events"
    ]
    assert order_statuses == ["created", "validated", "submitted"]
