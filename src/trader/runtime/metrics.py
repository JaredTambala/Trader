"""Runtime metrics sampling for live trading sessions.

Metrics workers run beside the trading service, derive portfolio exposure from
broker or event-store state, log each sample, and optionally persist snapshots
for later operator inspection.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Sequence
import json

from ..portfolio import Position, load_latest_positions, load_latest_cash
from ..broker import Broker
from ..event_store import EventStore
from ..symbols import normalize_broker_positions


logger = logging.getLogger(__name__)


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


class MetricsWorker(threading.Thread):
    """Background thread that samples portfolio metrics during live service runs.

    The worker can read broker account/positions when supplied, otherwise it
    reconstructs state from the event store. Samples are logged every interval
    and optionally persisted as JSON metrics snapshots.
    """

    def __init__(
        self,
        event_store: EventStore,
        symbols: Sequence[str],
        asset_class: str,
        interval_seconds: float = 60.0,
        window_seconds: float | None = None,
        *,
        run_id: str | None = None,
        persist_snapshots: bool = False,
        broker: Broker | None = None,
    ) -> None:
        super().__init__(daemon=True)
        self._event_store = event_store
        self._symbols = [s.strip().upper() for s in symbols if s]
        self._asset_class = asset_class.lower()
        self._interval = max(1.0, interval_seconds)
        self._window = window_seconds
        self._stop = False
        self._baseline_equity: float | None = None
        self._peak_equity: float | None = None
        self._run_id = run_id
        self._persist_snapshots = persist_snapshots
        self._broker = broker

    def stop(self) -> None:
        """Request the sampling loop to exit after the current sleep interval."""
        self._stop = True

    def run(self) -> None:
        """Run the sampling loop until `stop()` requests shutdown.

        Each iteration samples portfolio metrics, optionally persists a snapshot,
        logs the core exposure and drawdown values, and continues after recoverable
        sampling errors so observability does not terminate the trading process.
        """
        logger.info(
            "Metrics worker start interval=%ss window=%s",
            self._interval,
            self._window,
        )
        while not self._stop:
            try:
                sample = self._sample()
                if sample is not None:
                    if self._persist_snapshots:
                        self._persist(sample)
                    logger.info(
                        "Metrics ts=%s equity=%.2f cash=%.2f net=%.2f gross=%.2f return=%.4f drawdown=%.4f",
                        sample.ts.isoformat(),
                        sample.equity,
                        sample.cash,
                        sample.net_exposure,
                        sample.gross_exposure,
                        sample.return_since_start or 0.0,
                        sample.drawdown or 0.0,
                    )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Metrics worker sampling failed: %s", exc)
            time.sleep(self._interval)
        logger.info("Metrics worker stopped")

    def _sample(self) -> MetricsSample | None:
        """Compute one metrics snapshot from current positions, cash, and prices.

        The first valid sample establishes baseline and peak equity. Later
        samples use those retained values to compute return since start and
        drawdown.
        """
        positions, cash = self._load_positions_and_cash()
        if not positions and cash == 0.0:
            return None

        # latest price per symbol
        price_lookup = self._latest_prices()
        net = 0.0
        gross = 0.0
        equity = cash
        for pos in positions:
            px = price_lookup.get(pos.symbol)
            if px is None:
                continue
            notional = pos.qty * px
            equity += notional
            net += notional
            gross += abs(notional)

        now = datetime.now(timezone.utc)
        if self._baseline_equity is None:
            self._baseline_equity = equity
            self._peak_equity = equity

        if self._peak_equity is None or equity > self._peak_equity:
            self._peak_equity = equity

        ret = (equity / self._baseline_equity - 1.0) if self._baseline_equity else None
        dd = (equity / self._peak_equity - 1.0) if self._peak_equity else None

        return MetricsSample(
            ts=now,
            equity=equity,
            cash=cash,
            net_exposure=net,
            gross_exposure=gross,
            return_since_start=ret,
            drawdown=dd,
        )

    def _load_positions_and_cash(self) -> tuple[Sequence[Position], float]:
        """Load positions/cash from broker when available, else from event store."""
        if self._broker is None:
            return load_latest_positions(self._event_store), load_latest_cash(self._event_store) or 0.0

        try:
            account = self._broker.get_account()
            cash_raw = account.get("cash", 0.0) if isinstance(account, Mapping) else 0.0
            cash = float(cash_raw) if cash_raw is not None else 0.0
            positions_raw = self._broker.get_positions() or []
        except Exception as exc:  # pragma: no cover - broker calls
            logger.warning("Metrics broker load failed; using event store: %s", exc)
            return load_latest_positions(self._event_store), load_latest_cash(self._event_store) or 0.0

        positions: list[Position] = []
        for position in normalize_broker_positions(positions_raw):
            positions.append(Position(symbol=position.symbol, qty=position.qty, avg_price=position.avg_entry_price))
        return positions, cash

    def _latest_prices(self) -> Mapping[str, float]:
        """Fetch the latest bar close per symbol from the event store."""
        connection = getattr(self._event_store, "connection", lambda: None)()
        if connection is None or not hasattr(connection, "cursor"):
            return {}
        table = "crypto_bar_events" if self._asset_class in {"crypto", "cryptocurrency"} else "stock_bar_events"
        symbols = self._symbols
        if not symbols:
            return {}
        placeholders = ", ".join(["%s"] * len(symbols))
        query = f"""
            WITH latest AS (
                SELECT symbol, timeframe, ts, close,
                       ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY ts DESC) AS rn
                FROM {table}
                WHERE symbol IN ({placeholders})
            )
            SELECT symbol, close FROM latest WHERE rn = 1
        """
        with connection.cursor() as cursor:
            cursor.execute(query, symbols)
            rows = cursor.fetchall()
        return {row[0]: float(row[1]) for row in rows}

    def _persist(self, sample: MetricsSample) -> None:
        """Persist a metrics snapshot to the event store."""
        payload = {
            "ts": sample.ts,
            "run_id": self._run_id,
            "session_id": self._run_id,
            "cycle_id": None,
            "payload": json.dumps(
                {
                    "equity": sample.equity,
                    "cash": sample.cash,
                    "net_exposure": sample.net_exposure,
                    "gross_exposure": sample.gross_exposure,
                    "return_since_start": sample.return_since_start,
                    "drawdown": sample.drawdown,
                    "asset_class": self._asset_class,
                    "symbols": self._symbols,
                }
            ),
        }
        try:
            self._event_store.record_event("metrics_snapshots", payload)
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to persist metrics snapshot: %s", exc)
