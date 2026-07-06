"""Pure runtime metrics models, calculations, and query planning."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Mapping, Sequence

from ..portfolio import PortfolioState, Position
from ..symbols import normalize_broker_positions


@dataclass
class MetricsSample:
    """Point-in-time portfolio metrics derived from cash, positions, and prices.

    Attributes:
        ts: UTC timestamp when the sample was computed.
        equity: Cash plus priced position notionals.
        cash: Current cash balance.
        net_exposure: Signed priced exposure.
        gross_exposure: Absolute priced exposure.
        return_since_start: Return relative to the worker baseline equity.
        drawdown: Return relative to the worker peak equity.
    """

    ts: datetime
    equity: float
    cash: float
    net_exposure: float
    gross_exposure: float
    return_since_start: float | None = None
    drawdown: float | None = None


@dataclass(frozen=True)
class MetricsSampleComputation:
    """Pure result of one metrics sample calculation."""

    sample: MetricsSample
    baseline_equity: float
    peak_equity: float


@dataclass(frozen=True)
class RuntimeMetricsSnapshotRecord:
    """Event-store record for a runtime metrics snapshot."""

    ts: datetime
    run_id: str | None
    session_id: str | None
    cycle_id: str | None
    sample: MetricsSample
    asset_class: str
    symbols: tuple[str, ...]

    def to_record(self) -> dict[str, object]:
        """Return an event-store-compatible metrics snapshot mapping."""
        return {
            "ts": self.ts,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "cycle_id": self.cycle_id,
            "payload": json.dumps(
                {
                    "equity": self.sample.equity,
                    "cash": self.sample.cash,
                    "net_exposure": self.sample.net_exposure,
                    "gross_exposure": self.sample.gross_exposure,
                    "return_since_start": self.sample.return_since_start,
                    "drawdown": self.sample.drawdown,
                    "asset_class": self.asset_class,
                    "symbols": list(self.symbols),
                }
            ),
        }


@dataclass(frozen=True)
class RuntimeLatestPriceQueryPlan:
    """Parameterized event-store query for latest bar closes."""

    query: str
    parameters: tuple[str, ...]


def compute_metrics_sample(
    *,
    positions: Sequence[Position],
    cash: float,
    price_lookup: Mapping[str, float],
    ts: datetime,
    baseline_equity: float | None,
    peak_equity: float | None,
) -> MetricsSampleComputation | None:
    """Compute one runtime metrics sample without side effects.

    Args:
        positions: Current positions to value.
        cash: Current cash balance.
        price_lookup: Latest prices keyed by symbol.
        ts: Explicit sample timestamp supplied by the shell.
        baseline_equity: Existing return baseline, if any.
        peak_equity: Existing drawdown peak, if any.

    Returns:
        Immutable sample computation, or `None` when there is no position and
        no cash state to report. Positions without prices are ignored.
    """
    if not positions and cash == 0.0:
        return None
    net = 0.0
    gross = 0.0
    equity = cash
    for position in positions:
        price = price_lookup.get(position.symbol)
        if price is None:
            continue
        notional = position.qty * price
        equity += notional
        net += notional
        gross += abs(notional)

    next_baseline = equity if baseline_equity is None else baseline_equity
    next_peak = equity if peak_equity is None or equity > peak_equity else peak_equity
    ret = (equity / next_baseline - 1.0) if next_baseline else None
    drawdown = (equity / next_peak - 1.0) if next_peak else None

    return MetricsSampleComputation(
        sample=MetricsSample(
            ts=ts,
            equity=equity,
            cash=cash,
            net_exposure=net,
            gross_exposure=gross,
            return_since_start=ret,
            drawdown=drawdown,
        ),
        baseline_equity=next_baseline,
        peak_equity=next_peak,
    )


def build_runtime_metrics_snapshot_record(
    sample: MetricsSample,
    *,
    run_id: str | None,
    asset_class: str,
    symbols: Sequence[str],
) -> RuntimeMetricsSnapshotRecord:
    """Build a runtime metrics snapshot record without persistence."""
    return RuntimeMetricsSnapshotRecord(
        ts=sample.ts,
        run_id=run_id,
        session_id=run_id,
        cycle_id=None,
        sample=sample,
        asset_class=asset_class,
        symbols=tuple(symbols),
    )


def positions_and_cash_from_portfolio_state(state: PortfolioState) -> tuple[Sequence[Position], float]:
    """Return metrics inputs from an immutable portfolio state."""
    return tuple(state.positions.values()), state.cash_balance


def positions_and_cash_from_broker_payload(
    *,
    account: object,
    positions_raw: Sequence[Mapping[str, object]],
) -> tuple[Sequence[Position], float]:
    """Return metrics inputs from broker account and position payloads."""
    cash_raw = account.get("cash", 0.0) if isinstance(account, Mapping) else 0.0
    cash = float(cash_raw) if cash_raw is not None else 0.0
    positions = tuple(
        Position(
            symbol=position.symbol,
            qty=position.qty,
            avg_price=position.avg_entry_price,
        )
        for position in normalize_broker_positions(positions_raw)
    )
    return positions, cash


def latest_price_query_plan(
    *,
    asset_class: str,
    symbols: Sequence[str],
) -> RuntimeLatestPriceQueryPlan | None:
    """Return the latest-price query plan for a bounded symbol universe."""
    normalized_symbols = tuple(symbol.strip().upper() for symbol in symbols if symbol and symbol.strip())
    if not normalized_symbols:
        return None

    table = "crypto_bar_events" if asset_class.lower() in {"crypto", "cryptocurrency"} else "stock_bar_events"
    placeholders = ", ".join(["%s"] * len(normalized_symbols))
    return RuntimeLatestPriceQueryPlan(
        query=f"""
            WITH latest AS (
                SELECT symbol, timeframe, ts, close,
                       ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY ts DESC) AS rn
                FROM {table}
                WHERE symbol IN ({placeholders})
            )
            SELECT symbol, close FROM latest WHERE rn = 1
        """,
        parameters=normalized_symbols,
    )


def latest_price_lookup_from_rows(rows: Sequence[Sequence[object]]) -> dict[str, float]:
    """Return latest prices keyed by symbol from query rows."""
    return {str(row[0]): float(row[1]) for row in rows}


__all__ = [
    "MetricsSample",
    "MetricsSampleComputation",
    "RuntimeLatestPriceQueryPlan",
    "RuntimeMetricsSnapshotRecord",
    "build_runtime_metrics_snapshot_record",
    "compute_metrics_sample",
    "latest_price_lookup_from_rows",
    "latest_price_query_plan",
    "positions_and_cash_from_broker_payload",
    "positions_and_cash_from_portfolio_state",
]
