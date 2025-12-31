"""Single execution cycle entry point."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .broker import Broker, NoOpBroker
from .config import Config, load_config
from .data import DuckDBEventStore, EventStore
from .risk import RiskManager, NoOpRiskManager
from .strategy import Strategy, NoOpStrategy


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CycleResult:
    run_id: str
    status: str


def run_cycle(
    event_store: EventStore | None = None,
    strategy: Strategy | None = None,
    risk_manager: RiskManager | None = None,
    broker: Broker | None = None,
    config: Config | None = None,
) -> CycleResult:
    """Execute a cycle and record run events."""
    config = config or load_config()
    strategy = strategy or NoOpStrategy()
    risk_manager = risk_manager or NoOpRiskManager()
    broker = broker or NoOpBroker()

    owns_event_store = False
    if event_store is None:
        db_path = Path(config.db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        event_store = DuckDBEventStore(str(db_path))
        owns_event_store = True

    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)
    decision_ts = started_at

    try:
        with event_store.transaction():
            signals = list(strategy.generate_signals())
            validated_orders = risk_manager.validate(signals)
            broker.submit_orders(validated_orders)

            finished_at = datetime.now(timezone.utc)
            event_store.record_event(
                "run_events",
                {
                    "run_id": run_id,
                    "strategy_id": config.strategy_id,
                    "mode": config.mode,
                    "decision_ts": decision_ts,
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "status": "success",
                    "error_message": None,
                },
            )
    finally:
        if owns_event_store:
            event_store.close()

    logger.info("Completed cycle", extra={"run_id": run_id})
    return CycleResult(run_id=run_id, status="success")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    result = run_cycle()
    logger.info("Cycle complete", extra={"run_id": result.run_id, "status": result.status})


if __name__ == "__main__":
    main()
