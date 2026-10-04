"""Contracts for the paper-runtime read model.

Subject: Mapping published runtime evidence into typed operational state.
Level: In-process application service.
Collaborators: Repository fixture only; no database or broker.
Guarantees: stale, unavailable, and configured-only states remain explicit.
Non-goals: broker mutation, operator authorization, and producer migrations.
"""

import asyncio
from datetime import datetime, timezone

from trader_console_api.contracts import BrokerAccountBinding, ConsoleEnvironment, ConsoleScope
from trader_console_api.services.paper_runtime import PaperRuntimeService


class _Repository:
    async def snapshot(self, *, stale_after_seconds: int) -> dict[str, object]:
        return {
            "session": {
                "session_id": "session-1", "strategy_id": "strategy-1", "status": "running",
                "mode": "paper", "symbols": ["AAPL"], "timeframe": "1Min",
                "started_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            },
            "freshness": [{"asset_class": "stock", "symbol": "AAPL", "timeframe": "1Min", "latest_ts": datetime(2025, 1, 1, tzinfo=timezone.utc)}],
            "positions": [{"symbol": "AAPL", "qty": 1, "avg_price": 100, "asof_ts": datetime(2026, 1, 1, tzinfo=timezone.utc), "cash_balance": 900}],
            "orders": [], "fills": [], "risk": [],
        }


def _scope() -> ConsoleScope:
    return ConsoleScope(
        scope_id="paper", display_name="Paper", environment=ConsoleEnvironment.PAPER,
        broker_account_binding=BrokerAccountBinding.CONFIGURED,
    )


def test_operations_preserve_stale_data_and_unavailable_operator_projections() -> None:
    """A green database response must not hide stale data or missing control evidence."""
    result = asyncio.run(PaperRuntimeService(_Repository(), _scope()).operations(now=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    assert result.session.session_id == "session-1"
    assert result.data_freshness.status == "stale"
    assert result.health.status == "unhealthy"
    assert result.reconciliation.evidence.status == "unavailable"
    assert result.halt.evidence.reason == "projection_not_published"
    assert result.broker_identity_verified is False


def test_operations_marks_non_paper_scope_out_of_scope() -> None:
    """Do not present backtest or demo evidence as paper runtime state."""
    scope = ConsoleScope(
        scope_id="demo", display_name="Demo", environment=ConsoleEnvironment.SYNTHETIC_DEMO,
        broker_account_binding=BrokerAccountBinding.NOT_APPLICABLE,
    )
    result = asyncio.run(PaperRuntimeService(_Repository(), scope).operations())
    assert result.data_freshness.evidence.status == "out_of_scope"
    assert result.session.evidence.reason == "paper_runtime_requires_paper_scope"
