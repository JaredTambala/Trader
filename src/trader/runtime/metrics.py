"""Runtime metrics sampling for live trading sessions.

Metrics workers run beside the trading service, derive portfolio exposure from
broker or event-store state, log each sample, and optionally persist snapshots
for later operator inspection.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Mapping, Sequence

from ..portfolio import Position, load_latest_portfolio_state
from ..broker import Broker
from ..event_store import EventStore
from .metrics_core import (
    MetricsSample,
    MetricsSampleComputation,
    RuntimeLatestPriceQueryPlan,
    RuntimeMetricsSnapshotRecord,
    build_runtime_metrics_snapshot_record,
    compute_metrics_sample,
    latest_price_lookup_from_rows as _latest_price_lookup_from_rows,
    latest_price_query_plan as _latest_price_query_plan,
    positions_and_cash_from_broker_payload as _positions_and_cash_from_broker_payload,
    positions_and_cash_from_portfolio_state as _positions_and_cash_from_portfolio_state,
)


logger = logging.getLogger(__name__)


__all__ = [
    "MetricsSample",
    "MetricsSampleComputation",
    "MetricsWorker",
    "RuntimeLatestPriceQueryPlan",
    "RuntimeMetricsSnapshotRecord",
    "build_runtime_metrics_snapshot_record",
    "compute_metrics_sample",
]


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

        price_lookup = self._latest_prices()
        computation = compute_metrics_sample(
            positions=positions,
            cash=cash,
            price_lookup=price_lookup,
            ts=datetime.now(timezone.utc),
            baseline_equity=self._baseline_equity,
            peak_equity=self._peak_equity,
        )
        if computation is None:
            return None
        self._baseline_equity = computation.baseline_equity
        self._peak_equity = computation.peak_equity
        return computation.sample

    def _load_positions_and_cash(self) -> tuple[Sequence[Position], float]:
        """Load positions/cash from broker when available, else from event store."""
        if self._broker is None:
            return _positions_and_cash_from_portfolio_state(load_latest_portfolio_state(self._event_store))

        try:
            account = self._broker.get_account()
            positions_raw = self._broker.get_positions() or []
        except Exception as exc:  # pragma: no cover - broker calls
            logger.warning("Metrics broker load failed; using event store: %s", exc)
            return _positions_and_cash_from_portfolio_state(load_latest_portfolio_state(self._event_store))

        return _positions_and_cash_from_broker_payload(
            account=account,
            positions_raw=positions_raw,
        )

    def _latest_prices(self) -> Mapping[str, float]:
        """Fetch the latest bar close per symbol from the event store."""
        connection = getattr(self._event_store, "connection", lambda: None)()
        if connection is None or not hasattr(connection, "cursor"):
            return {}
        plan = _latest_price_query_plan(asset_class=self._asset_class, symbols=self._symbols)
        if plan is None:
            return {}
        with connection.cursor() as cursor:
            cursor.execute(plan.query, list(plan.parameters))
            rows = cursor.fetchall()
        return _latest_price_lookup_from_rows(rows)

    def _persist(self, sample: MetricsSample) -> None:
        """Persist a metrics snapshot to the event store."""
        payload = build_runtime_metrics_snapshot_record(
            sample,
            run_id=self._run_id,
            asset_class=self._asset_class,
            symbols=self._symbols,
        ).to_record()
        try:
            self._event_store.record_event("metrics_snapshots", payload)
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to persist metrics snapshot: %s", exc)
