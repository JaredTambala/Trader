"""Lightweight metrics sampling for realtime trading."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Mapping, Sequence
import json

from .portfolio import load_latest_positions, load_latest_cash
from .data import EventStore


logger = logging.getLogger(__name__)


@dataclass
class MetricsSample:
    """Simple equity snapshot."""

    ts: datetime
    equity: float
    cash: float
    net_exposure: float
    gross_exposure: float
    return_since_start: float | None = None
    drawdown: float | None = None


class MetricsWorker(threading.Thread):
    """Background sampler for realtime equity metrics."""

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

    def stop(self) -> None:
        """Request the worker to stop."""
        self._stop = True

    def run(self) -> None:
        """Main loop."""
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
        """Compute a metrics snapshot."""
        positions = load_latest_positions(self._event_store)
        cash = load_latest_cash(self._event_store) or 0.0
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
