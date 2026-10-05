"""Read adapter for saved data scopes and their producer evidence."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
import json
from typing import Any
from uuid import UUID

import psycopg

from ..data_scope_contracts import SavedDataScope
from .database import ConsoleDatabase, ConsoleDatabaseUnavailable
from .resources import _row_dicts
from .saved_data_scopes import _stored
from .saved_data_scopes_schema import (
    CATALOG_SQL,
    COLUMNS,
)


class DataScopeComparisonStorageUnavailable(RuntimeError):
    """Saved-scope storage is absent or incompatible for comparison."""


class DataScopeComparisonNotFound(RuntimeError):
    """One or more selected saved scopes are absent from this Console scope."""


@dataclass(frozen=True)
class DataScopeComparisonCandidate:
    """One saved scope and the exact producer evidence row, if published."""

    scope: SavedDataScope
    evidence: dict[str, Any] | None


class DataScopeComparisonSession:
    """Read-only transaction bound to the server-owned Console scope."""

    def __init__(self, connection: Any, scope_id: str) -> None:
        """Bind trusted scope identity to every query."""
        self._connection = connection
        self._scope_id = scope_id

    async def require_storage(self) -> None:
        """Refuse absent saved-scope storage without creating it."""
        cursor = await self._connection.execute(CATALOG_SQL)
        if dict(await cursor.fetchall()) != COLUMNS:
            raise DataScopeComparisonStorageUnavailable(
                "Install Console saved data scope storage explicitly"
            )

    async def candidates(
        self, saved_scope_ids: tuple[UUID, ...]
    ) -> tuple[DataScopeComparisonCandidate, ...]:
        """Load selected scopes and exact evidence without widening the query."""
        cursor = await self._connection.execute(
            "SELECT * FROM console_app.saved_data_scopes "
            "WHERE scope_id = %s AND saved_scope_id = ANY(%s) "
            "ORDER BY saved_scope_id",
            [self._scope_id, list(saved_scope_ids)],
        )
        scopes = _stored(cursor, await cursor.fetchall())
        result: list[DataScopeComparisonCandidate] = []
        for scope in scopes:
            evidence_cursor = await self._connection.execute(
                """
                SELECT *
                FROM console_read.data_scope_evidence
                WHERE asset_class = %s
                  AND symbols = %s::jsonb
                  AND timeframe = %s
                  AND interval = %s
                  AND requested_start = %s
                  AND requested_end = %s
                  AND COALESCE(provider, '') = COALESCE(%s, '')
                  AND COALESCE(source_policy, '') = COALESCE(%s, '')
                ORDER BY quality_updated_at DESC NULLS LAST,
                         manifest_updated_at DESC NULLS LAST
                LIMIT 1
                """,
                [
                    scope.asset_class,
                    json.dumps(list(scope.symbols), separators=(",", ":")),
                    scope.timeframe,
                    scope.interval,
                    scope.start,
                    scope.end,
                    scope.source_policy.provider,
                    scope.source_policy.source,
                ],
            )
            rows = _row_dicts(evidence_cursor, await evidence_cursor.fetchall())
            result.append(
                DataScopeComparisonCandidate(scope=scope, evidence=rows[0] if rows else None)
            )
        return tuple(result)


class DataScopeComparisonRepository:
    """Keep alternative comparison reads separate from run comparisons."""

    def __init__(self, database: ConsoleDatabase, scope_id: str) -> None:
        """Bind comparison reads to the configured process scope."""
        self._database = database
        self._scope_id = scope_id

    @asynccontextmanager
    async def session(self) -> AsyncIterator[DataScopeComparisonSession]:
        """Yield one read-only transaction and preserve database failures."""
        try:
            async with self._database.transaction() as connection:
                yield DataScopeComparisonSession(connection, self._scope_id)
        except ConsoleDatabaseUnavailable as exc:
            if isinstance(exc.__cause__, psycopg.errors.UndefinedTable):
                raise DataScopeComparisonStorageUnavailable(
                    "Install Console saved data scope storage explicitly"
                ) from exc
            raise


__all__ = [
    "DataScopeComparisonCandidate",
    "DataScopeComparisonNotFound",
    "DataScopeComparisonRepository",
    "DataScopeComparisonSession",
    "DataScopeComparisonStorageUnavailable",
]
