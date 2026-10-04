"""Console mapping tests for exact Data manifest and quality evidence.

Subject: ``ResourceService.market_data_evidence`` projection.
Level: In-process service contract.
Collaborators: A fake repository returning one producer-owned evidence row.
Guarantees: Scope identity, artifact references, coverage and explicit states
survive normalization; absent evidence fails closed as unavailable.
Non-goals: PostgreSQL view SQL, Data quality calculations, or browser rendering.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import pytest

from trader_console_api.services.resources import ResourceService


_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
_END = datetime(2026, 1, 2, tzinfo=timezone.utc)


class _Repository:
    async def get_market_data_evidence(self, **_: Any) -> dict[str, Any] | None:
        return {
            "manifest_artifact_id": "manifest-1",
            "quality_artifact_id": "quality-1",
            "manifest_uri": "research://postgres/dataset_manifest/manifest-1",
            "quality_uri": "research://postgres/data_quality_report/quality-1",
            "evidence_status": "partial",
            "evidence_reason": "Quality evidence reports incomplete coverage.",
            "manifest_status": "captured",
            "quality_status": "captured",
            "manifest_schema_version": "2026-01",
            "quality_schema_version": "2026-01",
            "provider": "alpaca",
            "source_policy": "alpaca",
            "manifest_created_at": _START,
            "manifest_updated_at": _START,
            "quality_created_at": _START,
            "quality_updated_at": _START,
            "manifest_source_hash": "hash-manifest",
            "quality_source_hash": "hash-quality",
            "manifest_payload": {"total_rows": 2},
            "quality_payload": {"complete": False},
            "coverage": {"total_rows": 2, "total_bars": 2},
            "findings": ["AAPL has incomplete coverage."],
            "warnings": ["AAPL has incomplete coverage."],
            "provenance_refs": [
                "research://postgres/dataset_manifest/manifest-1",
                "research://postgres/data_quality_report/quality-1",
            ],
        }


class _EmptyRepository:
    async def get_market_data_evidence(self, **_: Any) -> dict[str, Any] | None:
        return None


def _kwargs() -> dict[str, Any]:
    return {
        "asset_class": "stock",
        "symbols": ("AAPL",),
        "timeframe": "1Min",
        "interval": "1Min",
        "bar_type": "trade_bar",
        "start": _START,
        "end": _END,
        "provider": "alpaca",
        "source_policy": "alpaca",
    }


def test_market_data_evidence_preserves_exact_scope_and_partial_findings() -> None:
    """Expose Data-owned identity and incomplete quality without recalculation."""
    result = asyncio.run(ResourceService(_Repository()).market_data_evidence(**_kwargs()))

    assert result.scope.symbols == ("AAPL",)
    assert result.scope.bar_type == "trade_bar"
    assert result.state == "partial"
    assert result.manifest is not None
    assert result.manifest.artifact_id == "manifest-1"
    assert result.quality is not None
    assert result.coverage["total_bars"] == 2
    assert result.warnings == ("AAPL has incomplete coverage.",)
    assert result.provenance[0].startswith("research://postgres/")


def test_market_data_evidence_fails_closed_when_scope_has_no_matching_pair() -> None:
    """Keep empty exact scopes distinct from a qualified dataset."""
    result = asyncio.run(ResourceService(_EmptyRepository()).market_data_evidence(**_kwargs()))

    assert result.state == "unavailable"
    assert result.manifest is None
    assert result.quality is None
    assert result.warnings == ("Data evidence is unavailable for the selected exact scope.",)


@pytest.mark.parametrize("state", ["complete", "stale", "warning", "empty"])
def test_market_data_evidence_preserves_published_qualification_states(state: str) -> None:
    """Do not collapse producer qualification states into a generic success result."""

    class _StateRepository(_Repository):
        async def get_market_data_evidence(self, **kwargs: Any) -> dict[str, Any] | None:
            row = await super().get_market_data_evidence(**kwargs)
            assert row is not None
            row["evidence_status"] = state
            return row

    result = asyncio.run(ResourceService(_StateRepository()).market_data_evidence(**_kwargs()))

    assert result.state == state
