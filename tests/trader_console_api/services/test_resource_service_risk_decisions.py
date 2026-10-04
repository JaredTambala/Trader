"""Resource-service risk trace contracts.

Subject: Bounded and filtered manager-decision projection normalization.
Level: Application-service unit tests.
Collaborators: Repository double and typed Console response contracts.
Guarantees: Published run traces become typed pages while unknown runs remain distinguishable.
Non-goals: SQL construction, HTTP routing, and frontend rendering.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from trader_console_api.services.resources import ResourceService


class _Repository:
    """Repository double returning one producer decision row."""

    async def list_risk_decisions(self, **_kwargs: object):
        """Return one bounded row and its total count."""
        return [
            {
                "risk_decision_id": "riskdec-1",
                "composition_fingerprint": "fingerprint",
                "run_id": "run-1",
                "session_id": "session-1",
                "cycle_id": "cycle-1",
                "client_order_id": "order-1",
                "decision_ts": datetime(2026, 1, 1, tzinfo=UTC),
                "manager_id": "max_orders_per_run",
                "manager_type": "trader_standard.risk.MaxOrdersPerRunRiskManager",
                "manager_position": 0,
                "outcome": "approved",
                "reason_code": "approved",
                "before_qty": 0.1,
                "after_qty": 0.1,
                "before_order": {"qty": 0.1},
                "after_order": {"qty": 0.1},
            }
        ], 1

    async def get_run_detail(self, **_kwargs: object):
        """Return one run with the producer's manager-parameter column name."""
        return {
            "run": {
                "experiment_run_id": "er-1",
                "experiment_id": "exp-1",
                "run_id": "run-1",
                "status": "completed",
            },
            "risk_composition": [
                {
                    "run_id": "run-1",
                    "session_id": "session-1",
                    "catalogue_version": "standard-1",
                    "composition_fingerprint": "fingerprint",
                    "manager_position": 0,
                    "manager_id": "max_orders_per_run",
                    "manager_type": "trader_standard.risk.MaxOrdersPerRunRiskManager",
                    "manager_parameters": {"limit": 0},
                }
            ],
        }


def test_risk_decisions_service_returns_typed_page() -> None:
    """Normalize producer rows into the public paginated risk decision contract."""
    result = asyncio.run(
        ResourceService(_Repository()).risk_decisions(
            run_id="run-1",
            manager_id="max_orders_per_run",
            outcome="approved",
            cycle_id=None,
            client_order_id=None,
            limit=25,
            offset=0,
        )
    )

    assert result is not None
    assert result.items[0].manager_id == "max_orders_per_run"
    assert result.page.total == 1


def test_run_detail_maps_producer_manager_parameters_to_public_parameters() -> None:
    """Normalize the projection column without leaking producer-only names."""
    result = asyncio.run(ResourceService(_Repository()).run_detail(run_id="run-1", section_limit=10))

    assert result is not None
    assert result.risk_composition[0].parameters == {"limit": 0}
