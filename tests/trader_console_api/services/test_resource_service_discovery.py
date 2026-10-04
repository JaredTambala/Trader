"""Console mapping tests for data discovery and provider capability states.

Subject: ``ResourceService.market_datasets`` discovery metadata projection.
Level: In-process service contract.
Collaborators: A fake repository returning producer-shaped dataset rows.
Guarantees: Stored slices are explicitly partial/discover-only by default and
producer capability fields are preserved when available.
Non-goals: PostgreSQL SQL, provider network calls, or browser rendering.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from trader_console_api.services.resources import ResourceService


class _Repository:
    async def list_market_datasets(
        self, *, limit: int, offset: int
    ) -> tuple[list[dict[str, Any]], int]:
        return [
            {
                "asset_class": "stock",
                "symbol": "DEMO",
                "timeframe": "1Min",
                "source": "sample",
                "first_ts": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "last_ts": datetime(2026, 1, 2, tzinfo=timezone.utc),
                "bar_count": 10,
            }
        ], 1


class _CapabilityRepository(_Repository):
    async def list_market_datasets(
        self, *, limit: int, offset: int
    ) -> tuple[list[dict[str, Any]], int]:
        rows, total = await super().list_market_datasets(limit=limit, offset=offset)
        rows[0].update(
            {
                "provider": "alpaca",
                "catalogue_completeness": "stale",
                "catalogue_freshness": "stale",
                "can_discover": True,
                "can_load": True,
                "load_capability": "load_capable",
                "capability_reason": "Provider receipt is older than the freshness window.",
            }
        )
        return rows, total


def test_market_datasets_does_not_infer_catalogue_completeness_from_rows() -> None:
    """Visible SQL slices remain partial and discover-only without Data evidence."""
    response = asyncio.run(ResourceService(_Repository()).market_datasets(limit=10, offset=0))

    assert response.discovery.catalogue_completeness == "partial"
    assert response.discovery.catalogue_freshness == "unknown"
    assert response.discovery.can_discover is True
    assert response.discovery.can_load is False
    assert response.discovery.load_capability == "discover_only"


def test_market_datasets_preserves_stale_load_capable_provider_evidence() -> None:
    """Producer capability metadata survives API normalization without collapsing stale evidence."""
    response = asyncio.run(
        ResourceService(_CapabilityRepository()).market_datasets(limit=10, offset=0)
    )

    assert response.discovery.provider == "alpaca"
    assert response.discovery.catalogue_completeness == "stale"
    assert response.discovery.catalogue_freshness == "stale"
    assert response.discovery.can_load is True
    assert response.discovery.load_capability == "load_capable"
    assert "older" in (response.discovery.reason or "")
