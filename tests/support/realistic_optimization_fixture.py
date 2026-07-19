"""Deterministic multi-asset evidence fixture for task 57L qualification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Mapping, Sequence

from trader.config import Config
from trader.event_store import EventStore
from trader.market_data.queries import BarQuery, fetch_bars
from trader_research.data import (
    DataInventoryRequest,
    DataQualityRequest,
    data_summarize_quality,
    get_data_inventory,
)


SYMBOLS = ("ALPHA", "BETA", "GAMMA")
ASSET_CLASS = "stocks"
TIMEFRAME = "1Hour"
SOURCE = "verification_57l_v1"
SEED = 5701
INITIAL_CASH = 100_000.0
SEARCH_LOOKBACKS = (2, 3, 4, 5)
SELECTION_CONTENT_SHA256 = "e883fa92e7eea43292bcb2f78e1d5ec48b7bf7aec5fe19dee2169646d150d0b0"
HOLDOUT_CONTENT_SHA256 = "96a896db53cfcbfc76b8bc9115d46b2d6bcf8fcc538905410c81ceb1f88debbf"
STRATEGY_SOURCE_SHA256 = "b40e32bb54d5c8b28f88ccdebd208e8fbc30240299400d8d1e1470833f45ad83"
RISK_SOURCE_SHA256 = "3713e6405efd1ecf10c7136475172a1aea7c862b0d80a80473c893d1d1cd2aee"
OBJECTIVE_SOURCE_SHA256 = "a6b826690cf58353c6c6d1ba49bd612737c7ffcbe631b6ea0526324f14a81012"
SELECTION_DATASET_ID = "dataset_e02d3f18f9ee9abc"
SELECTION_MANIFEST_SHA256 = "524849bd41e3752cc3661d366289ba68a50252b924ec10d941de2a1e1a5f095f"
SELECTION_QUALITY_SHA256 = "5c7dac4ac4e04fa3602db90390ab21cf1e6ca4722b0e012824e08da363bd20e9"
HOLDOUT_DATASET_ID = "dataset_c2866c31b1730cc2"
HOLDOUT_MANIFEST_SHA256 = "6f8d43d90c2ea98de618386ac01f583421c76755afd40ebcccb3ef0648ffa64a"
HOLDOUT_QUALITY_SHA256 = "60749fd4f5dac5df8388de5e2b72ab1e5111a7d1651cd2c98d80ccbd705f3c3f"
BASE_STRATEGY_PARAMETERS = {
    "lookback_bars": 3,
    "entry_threshold_bps": 15.0,
    "exit_threshold_bps": 5.0,
    "base_order_qty": 1.0,
}
RISK_PARAMETERS = {"max_entry_qty": 2.0}
BACKTEST_ASSUMPTIONS = {
    "fill_model": "full_fill",
    "latency_ms": 0.0,
    "fees": {"fixed_per_order": 0.25, "bps": 1.0, "minimum_fee": 0.25},
    "slippage": {"bps": 2.0},
    "data": {"allow_latest_prior_bar": False, "allow_price_carry_forward": False},
}

STRATEGY_PARAMETER_SCHEMA = {
    "type": "object",
    "properties": {
        "lookback_bars": {"type": "integer", "minimum": 2, "maximum": 5},
        "entry_threshold_bps": {"type": "number", "minimum": 0.0, "maximum": 100.0},
        "exit_threshold_bps": {"type": "number", "minimum": 0.0, "maximum": 100.0},
        "base_order_qty": {"type": "number", "minimum": 0.1, "maximum": 10.0},
    },
    "required": [
        "lookback_bars",
        "entry_threshold_bps",
        "exit_threshold_bps",
        "base_order_qty",
    ],
}

RISK_PARAMETER_SCHEMA = {
    "type": "object",
    "properties": {
        "max_entry_qty": {"type": "number", "minimum": 0.1, "maximum": 100.0},
    },
    "required": ["max_entry_qty"],
}

STRATEGY_SOURCE = '''
from trader.portfolio import Position
from trader.strategies import Strategy
from trader_standard.bar_signals import fetch_recent_bars, table_for_asset_class


class TrailingReturnTransitionStrategy(Strategy):
    def __init__(
        self,
        *,
        symbols,
        asset_class,
        timeframe,
        lookback_bars=3,
        entry_threshold_bps=15.0,
        exit_threshold_bps=5.0,
        base_order_qty=1.0,
    ):
        self._symbols = tuple(sorted(str(symbol).strip().upper() for symbol in symbols))
        self._asset_class = str(asset_class)
        self._timeframe = str(timeframe)
        self._lookback_bars = int(lookback_bars)
        self._entry_threshold_bps = float(entry_threshold_bps)
        self._exit_threshold_bps = float(exit_threshold_bps)
        self._qty_by_symbol = {
            symbol: float(base_order_qty) * (index + 1)
            for index, symbol in enumerate(self._symbols)
        }

    @property
    def strategy_id(self):
        return "verification-trailing-return-transition-v1"

    def generate_orders(self, *, run_id, cycle_id, decision_ts, event_store, portfolio):
        orders = []
        for symbol in self._symbols:
            orders.extend(
                self.generate_orders_for_symbol(
                    symbol,
                    run_id=run_id,
                    cycle_id=cycle_id,
                    decision_ts=decision_ts,
                    event_store=event_store,
                    portfolio=portfolio,
                )
            )
        return tuple(orders)

    def generate_orders_for_symbol(
        self,
        symbol,
        *,
        run_id,
        cycle_id,
        decision_ts,
        event_store,
        portfolio,
    ):
        del run_id, cycle_id
        requested = str(symbol).strip().upper()
        if requested not in self._qty_by_symbol:
            return ()
        bars = fetch_recent_bars(
            event_store,
            table=table_for_asset_class(self._asset_class),
            symbol=requested,
            timeframe=self._timeframe,
            limit=self._lookback_bars + 1,
            as_of_ts=decision_ts,
        )
        if len(bars) < self._lookback_bars + 1 or not self._is_contiguous(bars):
            return ()
        oldest = float(bars[-1].close)
        if oldest <= 0.0:
            return ()
        trailing_return_bps = ((float(bars[0].close) / oldest) - 1.0) * 10000.0
        position = portfolio.positions.get(
            requested,
            Position(symbol=requested, qty=0.0, avg_price=None),
        )
        if position.qty <= 0.0 and trailing_return_bps >= self._entry_threshold_bps:
            return ({
                "symbol": requested,
                "side": "buy",
                "qty": self._qty_by_symbol[requested],
                "order_type": "market",
            },)
        if position.qty > 0.0 and trailing_return_bps <= -self._exit_threshold_bps:
            return ({
                "symbol": requested,
                "side": "sell",
                "qty": float(position.qty),
                "order_type": "market",
            },)
        return ()

    def _is_contiguous(self, bars):
        interval = self._interval_seconds()
        if interval is None:
            return False
        for newer, older in zip(bars, bars[1:]):
            if int((newer.ts - older.ts).total_seconds()) != interval:
                return False
        return True

    def _interval_seconds(self):
        if self._timeframe.endswith("Min"):
            return int(self._timeframe[:-3]) * 60
        if self._timeframe.endswith("Hour"):
            return int(self._timeframe[:-4]) * 60 * 60
        return None


def build_strategy(**kwargs):
    return TrailingReturnTransitionStrategy(**kwargs)
'''.lstrip()

RISK_SOURCE = '''
from trader.risk import RiskManager


class EntryQuantityLimitRiskManager(RiskManager):
    def __init__(self, max_entry_qty=2.0):
        self._max_entry_qty = float(max_entry_qty)

    def validate(self, orders, context):
        approved, _ = self._partition(orders, context)
        return approved

    def evaluate(self, orders, context):
        return self._partition(orders, context)

    def _partition(self, orders, context):
        approved = []
        rejected = []
        for order in orders:
            symbol = str(order.get("symbol") or "").strip().upper()
            side = str(order.get("side") or "").strip().lower()
            qty = float(order.get("qty") or 0.0)
            position = context.positions.get(symbol)
            position_qty = float(position.qty) if position is not None else 0.0
            reducing = (position_qty > 0.0 and side == "sell") or (
                position_qty < 0.0 and side == "buy"
            )
            if reducing or qty <= self._max_entry_qty:
                approved.append(order)
            else:
                rejected.append({**order, "rejection_reason": "entry_quantity_limit"})
        return tuple(approved), tuple(rejected)


def build_risk_manager(max_entry_qty=2.0):
    return EntryQuantityLimitRiskManager(max_entry_qty=max_entry_qty)
'''.lstrip()

OBJECTIVE_SOURCE = '''
def _required_numeric(mapping, name):
    value = mapping.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("required numeric observation field is unavailable: " + name)
    return float(value)


def objective(observation):
    metrics = observation["metrics"]
    costs = observation["costs"]
    total_return = _required_numeric(metrics, "total_return")
    max_drawdown = _required_numeric(metrics, "max_drawdown")
    fees = _required_numeric(costs, "fees")
    slippage = _required_numeric(costs, "slippage")
    cost_penalty = (fees + slippage) / 100000.0
    value = total_return - (0.5 * max_drawdown) - cost_penalty
    return {
        "value": value,
        "diagnostics": {
            "total_return": total_return,
            "max_drawdown": max_drawdown,
            "cost_penalty": cost_penalty,
        },
    }
'''.lstrip()


_SELECTION_PATTERNS = {
    "ALPHA": (0, 1, 3, 6, 9, 7, 4, 1, -2, -1, 2, 5),
    "BETA": (0, -1, 1, 4, 8, 12, 10, 6, 2, -2, -4, -1, 3, 7, 11, 8),
    "GAMMA": (-2, 0, 3, 7, 11, 9, 5, 1, -3, -1, 2, 6),
}
_HOLDOUT_PATTERNS = {
    "ALPHA": (1, 3, 6, 10, 8, 4, 0, -3, -1, 2, 5, 9, 12, 8, 5, 10),
    "BETA": (-1, 1, 5, 9, 13, 10, 6, 2, -2, -5, -1, 3, 7, 11, 6, 10),
    "GAMMA": (0, 2, 4, 8, 12, 9, 5, 1, -4, -2, 1, 5, 10, 7, 4, 9),
}
_BASE_PRICES = {"ALPHA": 100.0, "BETA": 80.0, "GAMMA": 120.0}
_PRICE_STEP = {"ALPHA": 0.20, "BETA": 0.18, "GAMMA": 0.22}


@dataclass(frozen=True)
class FixtureRegion:
    """One exact chronological market-data region."""

    name: str
    start: datetime
    bar_count: int
    patterns: Mapping[str, Sequence[int]]

    @property
    def end(self) -> datetime:
        """Return the inclusive final bar timestamp."""
        return self.start + timedelta(hours=self.bar_count - 1)

    def rows(self) -> tuple[dict[str, object], ...]:
        """Return deterministic Postgres bar-event payloads."""
        rows: list[dict[str, object]] = []
        for index in range(self.bar_count):
            ts = self.start + timedelta(hours=index)
            for symbol in SYMBOLS:
                pattern = self.patterns[symbol]
                offset = pattern[index % len(pattern)]
                close = round(_BASE_PRICES[symbol] + (_PRICE_STEP[symbol] * offset), 6)
                previous_offset = pattern[(index - 1) % len(pattern)] if index else offset
                open_price = round(
                    _BASE_PRICES[symbol] + (_PRICE_STEP[symbol] * previous_offset),
                    6,
                )
                high = round(max(open_price, close) + 0.08, 6)
                low = round(min(open_price, close) - 0.08, 6)
                rows.append(
                    {
                        "symbol": symbol,
                        "timeframe": TIMEFRAME,
                        "ts": ts,
                        "ingested_at": ts,
                        "open": open_price,
                        "high": high,
                        "low": low,
                        "close": close,
                        "volume": float(1_000 + (index * 10) + SYMBOLS.index(symbol)),
                        "trade_count": float(100 + index),
                        "vwap": round((open_price + close) / 2.0, 6),
                        "source": SOURCE,
                    }
                )
        return tuple(rows)

    @property
    def content_sha256(self) -> str:
        """Return the exact bar-content digest for this region."""
        return bar_content_sha256(self.rows())


@dataclass(frozen=True)
class RealisticOptimizationFixture:
    """Complete bounded input contract shared by 57L and later 57M."""

    selection: FixtureRegion
    holdout: FixtureRegion


def build_realistic_optimization_fixture() -> RealisticOptimizationFixture:
    """Build the versioned task 57L fixture without reading external state."""
    selection_start = datetime(2026, 3, 2, 0, 0, tzinfo=timezone.utc)
    selection = FixtureRegion(
        name="selection",
        start=selection_start,
        bar_count=48,
        patterns=_SELECTION_PATTERNS,
    )
    holdout = FixtureRegion(
        name="holdout",
        start=selection.end + timedelta(hours=25),
        bar_count=32,
        patterns=_HOLDOUT_PATTERNS,
    )
    return RealisticOptimizationFixture(selection=selection, holdout=holdout)


def seed_fixture(store: EventStore, fixture: RealisticOptimizationFixture) -> None:
    """Insert the complete fixture into an injected event store."""
    for region in (fixture.selection, fixture.holdout):
        for row in region.rows():
            store.record_event("stock_bar_events", row)


def data_evidence(store: EventStore, region: FixtureRegion) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return Data Agent manifest and quality payloads for one fixture region."""
    request = {
        "symbols": SYMBOLS,
        "asset_class": ASSET_CLASS,
        "timeframe": TIMEFRAME,
        "start": region.start,
        "end": region.end,
    }
    inventory = get_data_inventory(store, DataInventoryRequest(**request))
    quality = data_summarize_quality(store, DataQualityRequest(**request))
    if not inventory.ok:
        raise ValueError(f"fixture inventory failed: {inventory.errors}")
    if not quality.ok:
        raise ValueError(f"fixture quality failed: {quality.errors}")
    return (
        _jsonable(inventory.data["dataset_manifest"]),
        _jsonable(quality.data["data_quality_report"]),
    )


def postgres_region_content_sha256(store: EventStore, region: FixtureRegion) -> str:
    """Read one region through the core query API and hash its canonical rows."""
    records = fetch_bars(
        store,
        BarQuery(
            symbols=SYMBOLS,
            asset_class=ASSET_CLASS,
            timeframe=TIMEFRAME,
            start=region.start,
            end=region.end,
            limit=region.bar_count * len(SYMBOLS),
        ),
    )
    rows = [
        {
            "symbol": record.symbol,
            "timeframe": record.timeframe,
            "ts": record.ts,
            "open": record.open,
            "high": record.high,
            "low": record.low,
            "close": record.close,
            "volume": record.volume,
            "trade_count": record.trade_count,
            "vwap": record.vwap,
            "source": record.source,
        }
        for record in records
    ]
    return bar_content_sha256(rows)


def bar_content_sha256(rows: Sequence[Mapping[str, object]]) -> str:
    """Hash ordered bar identity and values without ingestion metadata."""
    canonical = []
    for row in sorted(rows, key=lambda item: (str(item["ts"]), str(item["symbol"]), str(item["source"]))):
        canonical.append(
            {
                "symbol": str(row["symbol"]),
                "timeframe": str(row["timeframe"]),
                "ts": _timestamp(row["ts"]).isoformat(),
                "open": _float_identity(row["open"]),
                "high": _float_identity(row["high"]),
                "low": _float_identity(row["low"]),
                "close": _float_identity(row["close"]),
                "volume": _float_identity(row["volume"]),
                "trade_count": _optional_float_identity(row.get("trade_count")),
                "vwap": _optional_float_identity(row.get("vwap")),
                "source": str(row.get("source") or ""),
            }
        )
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_backtest_config(settings: Mapping[str, object]) -> Config:
    """Build deterministic runtime configuration for an injected Postgres store."""
    return Config(
        mode="once",
        strategy_type="research",
        strategy_id="verification-57l",
        strategy_timeframe=TIMEFRAME,
        sma_short_window=2,
        sma_long_window=5,
        db_path="",
        event_store="postgres",
        market_data_source="noop",
        market_data_asset_class=ASSET_CLASS,
        market_data_stock_feed="iex",
        market_data_symbols=SYMBOLS,
        market_data_max_age_seconds=60,
        alpaca_api_key="",
        alpaca_secret_key="",
        alpaca_data_base_url="https://data.alpaca.markets",
        alpaca_base_url="https://paper-api.alpaca.markets",
        pg_dsn="",
        pg_host=str(settings["host"]),
        pg_port=int(settings["port"]),
        pg_db=str(settings["dbname"]),
        pg_user=str(settings["user"]),
        pg_password=str(settings["password"]),
        buffered_event_store=False,
        buffer_flush_interval_ms=250,
        buffer_max_batch_size=500,
        buffer_max_queue_size=10_000,
        buffer_block_on_full=True,
        log_signal_events=True,
        log_indicator_events=True,
        log_order_events=True,
        log_fill_events=True,
        log_position_snapshots=True,
        broker_type="noop",
    )


def _timestamp(value: object) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _float_identity(value: object) -> str:
    return float(value).hex()


def _optional_float_identity(value: object | None) -> str | None:
    return None if value is None else _float_identity(value)


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value
