"""Single execution cycle entry point."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import time
import uuid

from .broker import Broker, NoOpBroker
from .config import Config, load_config
from .data import EventStore, NoOpEventStore
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
    """Execute a no-op cycle and record start/finish events."""
    config = config or load_config()
    event_store = event_store or NoOpEventStore()
    strategy = strategy or NoOpStrategy()
    risk_manager = risk_manager or NoOpRiskManager()
    broker = broker or NoOpBroker()

    run_id = str(uuid.uuid4())
    started_at = time.time()
    event_store.record_event("run_started", {"run_id": run_id, "mode": config.mode})

    signals = list(strategy.generate_signals())
    validated_orders = risk_manager.validate(signals)
    broker.submit_orders(validated_orders)

    finished_at = time.time()
    event_store.record_event(
        "run_finished",
        {
            "run_id": run_id,
            "status": "success",
            "duration_seconds": finished_at - started_at,
        },
    )
    logger.info("Completed no-op cycle", extra={"run_id": run_id})
    return CycleResult(run_id=run_id, status="success")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    result = run_cycle()
    logger.info("Cycle complete", extra={"run_id": result.run_id, "status": result.status})


if __name__ == "__main__":
    main()
