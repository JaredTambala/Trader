"""Subject: exact saved Data scope request and evidence-state contracts.

Level: Pydantic contract tests.
Collaborators: Real value models only.
Guarantees: timestamps, symbols, windows, and evidence explanations are normalized or rejected.
Non-goals: PostgreSQL persistence, HTTP serialization, and producer quality calculations.
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from trader_console_api.data_scope_contracts import (
    DataScopeEvidenceStatus,
    SavedDataScopeCreate,
)


def _request(**updates: object) -> SavedDataScopeCreate:
    """Build one representative exact-scope request."""
    values: dict[str, object] = {
        "name": "Research window",
        "asset_class": "stock",
        "symbols": ("aapl", "MSFT", "AAPL"),
        "universe": "research-universe",
        "timeframe": "1Min",
        "interval": "1Min",
        "start": "2026-01-01T00:00:00+00:00",
        "end": "2026-01-02T00:00:00+00:00",
        "source_policy": {"provider": "alpaca", "source": "iex", "allow_fallback": False},
        "research_role": "backtest_authoring",
        "manifest_artifact_id": "manifest-1",
        "quality_artifact_id": "quality-1",
        "created_by": "operator-1",
        "idempotency_key": "scope-request-1",
    }
    values.update(updates)
    return SavedDataScopeCreate.model_validate(values)


def test_request_normalizes_scope_identity_before_persistence() -> None:
    """Symbols are canonical and timestamps are UTC before fingerprinting."""
    request = _request(start="2026-01-01T00:00:00+01:00")

    assert request.symbols == ("AAPL", "MSFT")
    assert request.start == datetime(2025, 12, 31, 23, tzinfo=UTC)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"start": "2026-01-03T00:00:00Z", "end": "2026-01-02T00:00:00Z"}, "end must not precede"),
        ({"evidence_status": DataScopeEvidenceStatus.STALE}, "evidence_reason is required"),
        ({"start": datetime(2026, 1, 1)}, "timestamps must include a timezone"),
    ],
)
def test_request_rejects_ambiguous_scope_state(updates: dict[str, object], message: str) -> None:
    """A saved scope cannot hide reversed windows or degraded evidence reasons."""
    with pytest.raises(ValidationError, match=message):
        _request(**updates)
