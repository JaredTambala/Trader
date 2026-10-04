"""Application service for exact, reusable Console data scopes."""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

from ..data_scope_contracts import (
    DataScopeEvidenceStatus,
    DataScopePageInfo,
    SavedDataScope,
    SavedDataScopeCreate,
    SavedDataScopesResponse,
)
from ..repositories.database import ConsoleDatabaseUnavailable
from ..repositories.saved_data_scopes import (
    SavedDataScopeConflict,
    SavedDataScopeNotFound,
    SavedDataScopeRepository,
)
from ..repositories.saved_data_scopes_schema import SavedDataScopeStorageUnavailable


SavedDataScopeDatabaseUnavailable = ConsoleDatabaseUnavailable


def _fingerprint(request: SavedDataScopeCreate) -> str:
    """Hash exact scope and evidence identity, excluding mutable state and actor metadata."""
    payload = request.model_dump(
        mode="json",
        exclude={"evidence_status", "evidence_reason", "created_by", "idempotency_key"},
    )
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SavedDataScopeService:
    """Persist and revalidate immutable Data evidence handoffs."""

    def __init__(self, repository: SavedDataScopeRepository) -> None:
        """Bind the configured Console scope repository."""
        self._repository = repository

    async def create(self, request: SavedDataScopeCreate) -> SavedDataScope:
        """Create or replay one exact saved scope without changing its identity."""
        async with self._repository.session(write=True) as session:
            await session.require_storage()
            return await session.create(request, fingerprint=_fingerprint(request))

    async def get(self, saved_scope_id: UUID) -> SavedDataScope:
        """Reopen one scope with its latest persisted evidence state."""
        async with self._repository.session() as session:
            await session.require_storage()
            result = await session.get(saved_scope_id)
        if result is None:
            raise SavedDataScopeNotFound("Saved data scope not found")
        return result

    async def list(self, *, limit: int, offset: int) -> SavedDataScopesResponse:
        """Return a bounded page of saved scopes."""
        async with self._repository.session() as session:
            await session.require_storage()
            rows, total = await session.list(limit, offset)
        return SavedDataScopesResponse(
            items=tuple(rows),
            page=DataScopePageInfo(
                limit=limit,
                offset=offset,
                total=total,
                has_more=offset + limit < total,
            ),
        )

    async def revalidate(self, saved_scope_id: UUID) -> SavedDataScope:
        """Resolve current producer evidence and persist active/stale/unavailable state."""
        async with self._repository.session() as session:
            await session.require_storage()
            current = await session.get(saved_scope_id)
            if current is None:
                raise SavedDataScopeNotFound("Saved data scope not found")
            try:
                evidence = await session.current_evidence(current)
            except ConsoleDatabaseUnavailable:
                evidence = None
        status: DataScopeEvidenceStatus
        reason: str | None
        if evidence is None:
            status = DataScopeEvidenceStatus.UNAVAILABLE
            reason = "The referenced Data manifest or quality projection is unavailable."
        else:
            status, reason = evidence
            if status is not DataScopeEvidenceStatus.ACTIVE and not reason:
                reason = f"Referenced Data evidence is {status.value}."
        async with self._repository.session(write=True) as session:
            await session.require_storage()
            updated = await session.update_evidence(
                saved_scope_id,
                status=status,
                reason=reason,
            )
        if updated is None:
            raise SavedDataScopeNotFound("Saved data scope not found")
        return updated


__all__ = [
    "SavedDataScopeConflict",
    "SavedDataScopeDatabaseUnavailable",
    "SavedDataScopeNotFound",
    "SavedDataScopeService",
    "SavedDataScopeStorageUnavailable",
]
