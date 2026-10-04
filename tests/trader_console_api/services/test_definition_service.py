"""Preflight-gated immutable definition service contracts.

Subject: Definition create/list/get/revision orchestration and invalid-draft handling.
Level: Application-service unit tests.
Collaborators: In-memory preflight and repository/session doubles; Pydantic contracts.
Guarantees: Invalid drafts never reach persistence, valid drafts store normalized fingerprints, and revisions append.
Non-goals: PostgreSQL SQL syntax, worker execution, and frontend behavior.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from trader_console_api.contracts import (
    BacktestDefinitionRevision,
    BacktestPreflightRequest,
    BacktestPreflightResponse,
)
from trader_console_api.services.backtest_definitions import (
    BacktestDefinitionService,
    InvalidBacktestDefinition,
)


def _draft() -> BacktestPreflightRequest:
    """Build one minimal draft accepted by the fake preflight."""
    return BacktestPreflightRequest(
        strategy_profile_id="noop",
        asset_class="stock",
        symbols=("AAPL",),
        timeframe="1Min",
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 1, 1, tzinfo=UTC),
    )


class _Session:
    """Repository session double that records writes."""

    def __init__(self) -> None:
        self.writes = 0

    async def require_storage(self) -> None:
        """Pretend explicit storage is installed."""

    async def create(self, definition, *, fingerprint):
        """Return a representative first revision."""
        self.writes += 1
        now = datetime(2026, 1, 1, tzinfo=UTC)
        return BacktestDefinitionRevision(
            definition_id=str(uuid4()),
            scope_id="scope-a",
            revision=1,
            fingerprint=fingerprint,
            definition=definition,
            created_at=now,
            updated_at=now,
        )

    async def create_revision(self, definition_id, definition, *, fingerprint):
        """Return a representative appended revision."""
        self.writes += 1
        now = datetime(2026, 1, 1, tzinfo=UTC)
        return BacktestDefinitionRevision(
            definition_id=str(definition_id),
            scope_id="scope-a",
            revision=2,
            fingerprint=fingerprint,
            definition=definition,
            created_at=now,
            updated_at=now,
        )

    async def get(self, definition_id):
        """Return no row for the list-only service tests."""
        return None

    async def list(self, limit, offset):
        """Return an empty bounded result."""
        return [], 0


class _Repository:
    """Repository double that records transaction mode."""

    def __init__(self, session: _Session) -> None:
        self.session_value = session
        self.write_modes: list[bool] = []

    @asynccontextmanager
    async def session(self, *, write: bool = False):
        """Yield the configured session without a database transaction."""
        self.write_modes.append(write)
        yield self.session_value


class _Preflight:
    """Preflight double with configurable typed result."""

    def __init__(self, result: BacktestPreflightResponse) -> None:
        self.result = result

    async def preflight(self, draft):
        """Return the configured preflight response."""
        return self.result


def test_invalid_preflight_never_opens_a_write_session() -> None:
    """Rejected field-level issues stop before Console storage is touched."""
    session = _Session()
    result = BacktestPreflightResponse(valid=False, catalogue_version="standard-1")
    service = BacktestDefinitionService(_Repository(session), _Preflight(result))

    with pytest.raises(InvalidBacktestDefinition):
        asyncio.run(service.create(_draft()))

    assert session.writes == 0


def test_valid_preflight_persists_normalized_definition_and_revision() -> None:
    """Valid normalized content is stored through a command session and can append a revision."""
    from trader_standard.catalogue import maintained_catalogue
    from trader_console_api.services.catalogue import PreflightService

    class _Coverage:
        async def backtest_coverage(self, **kwargs):
            return [{
                "symbol": "AAPL", "first_ts": datetime(2025, 12, 31, tzinfo=UTC),
                "last_ts": datetime(2026, 1, 1, 1, tzinfo=UTC), "bar_count": 100,
            }]

    normalized = asyncio.run(PreflightService(_Coverage(), maintained_catalogue()).preflight(_draft()))
    session = _Session()
    service = BacktestDefinitionService(_Repository(session), _Preflight(normalized))

    created = asyncio.run(service.create(_draft()))
    revised = asyncio.run(service.create_revision(uuid4(), _draft()))

    assert created.fingerprint == revised.fingerprint
    assert session.writes == 2
