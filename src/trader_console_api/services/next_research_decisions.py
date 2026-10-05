"""Application service for human next-decision commands and reads."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from trader.runtime.operator_control import is_human_operator_principal
from trader_research.governance import (
    BoundedNextExperiment,
    NextDecisionOutcome,
    build_next_research_decision,
)
from trader_research.governance.handoffs import ArtifactReportRef

from ..contracts import (
    BoundedNextExperimentContract,
    NextDecisionArtifactReference,
    NextResearchDecisionRecord,
    NextResearchDecisionsResponse,
    NextResearchDecisionRequest,
    PageInfo,
    TraderPrincipal,
)
from ..repositories.database import ConsoleDatabaseUnavailable
from ..repositories.next_research_decisions import (
    NextResearchDecisionConflict,
    NextResearchDecisionEvidenceUnavailable,
    NextResearchDecisionNotFound,
    NextResearchDecisionRepository,
)
from ..repositories.next_research_decisions_schema import NextResearchDecisionStorageUnavailable


class NextDecisionAuthorityError(RuntimeError):
    """The authenticated principal cannot record a human decision."""


class NextDecisionRevisionConflict(RuntimeError):
    """A revision does not append to the current decision stream."""


NextDecisionDatabaseUnavailable = ConsoleDatabaseUnavailable


def _artifact_ref(reference: NextDecisionArtifactReference) -> ArtifactReportRef:
    """Convert the transport reference into the research-owned typed pointer."""
    return ArtifactReportRef(
        artifact_id=reference.artifact_id,
        artifact_type=reference.artifact_type,
        domain_owner=reference.domain_owner,
        uri=reference.uri,
        metadata=dict(reference.metadata),
    )


def _experiment(value: BoundedNextExperimentContract | None) -> BoundedNextExperiment | None:
    """Convert an optional transport successor into its domain contract."""
    if value is None:
        return None
    return BoundedNextExperiment(
        question=value.question,
        data_ref=_artifact_ref(value.data_ref),
        implementation_refs=tuple(_artifact_ref(item) for item in value.implementation_refs),
        assumptions=value.assumptions,
        evaluation_start=value.evaluation_start.isoformat(),
        evaluation_end=value.evaluation_end.isoformat(),
        max_runs=value.max_runs,
        success_criteria=value.success_criteria,
    )


def _record(decision: Any) -> NextResearchDecisionRecord:
    """Normalize a domain artifact into the public immutable response."""
    payload = decision.to_dict()
    payload.pop("schema_version", None)
    payload.pop("metadata", None)
    return NextResearchDecisionRecord.model_validate(payload)


class NextResearchDecisionService:
    """Validate human authority, evidence lineage, and append-only revisions."""

    def __init__(self, repository: NextResearchDecisionRepository) -> None:
        """Bind one scope-owned decision repository."""
        self._repository = repository

    async def create(
        self,
        run_id: str,
        request: NextResearchDecisionRequest,
        principal: TraderPrincipal,
    ) -> NextResearchDecisionRecord:
        """Record one first or successor revision for the reviewed run."""
        self._require_human(principal)
        if request.source_run_ref.artifact_id != run_id:
            raise NextResearchDecisionEvidenceUnavailable(
                "source_run_ref must identify the reviewed run in the route"
            )
        async def build(decided_at: str):
            """Build one domain candidate with a caller-selected timestamp."""
            return build_next_research_decision(
            decision_id=request.decision_id,
            revision=request.revision,
            outcome=NextDecisionOutcome(request.outcome),
            rationale=request.rationale,
            operator=principal.principal_id,
            decided_at=decided_at,
            source_run_ref=_artifact_ref(request.source_run_ref),
            data_ref=_artifact_ref(request.data_ref),
            implementation_refs=tuple(_artifact_ref(item) for item in request.implementation_refs),
            assumptions=request.assumptions,
            review_refs=tuple(_artifact_ref(item) for item in request.review_refs),
            limitations=request.limitations,
            next_experiment=_experiment(request.next_experiment),
            supersedes_artifact_id=request.supersedes_artifact_id,
            metadata={"scope_id": self._repository.scope_id},
            )
        async with self._repository.session(write=True) as session:
            await session.require_storage()
            existing = await session.get(run_id, request.decision_id, request.revision)
            if existing is not None:
                replay = await build(existing.decided_at)
                if replay.to_dict() != existing.to_dict():
                    raise NextDecisionRevisionConflict(
                        "decision revision already exists with different content"
                    )
                await session.validate_evidence(replay, run_id=run_id)
                return _record(existing)
            decision = await build(datetime.now(timezone.utc).isoformat())
            await session.validate_evidence(decision, run_id=run_id)
            latest = await session.latest(decision.decision_id)
            if latest is not None:
                latest_revision, latest_artifact_id = latest
                if request.revision <= latest_revision:
                    raise NextDecisionRevisionConflict(
                        "decision revision already exists; replay the stored artifact"
                    )
                if request.revision != latest_revision + 1:
                    raise NextDecisionRevisionConflict(
                        "decision revision must append exactly after the latest revision"
                    )
                if request.supersedes_artifact_id != latest_artifact_id:
                    raise NextDecisionRevisionConflict(
                        "decision revision must supersede the latest artifact"
                    )
            elif request.revision != 1:
                raise NextDecisionRevisionConflict("the first decision revision must be 1")
            stored = await session.create(decision, requested_by=principal.principal_id)
        return _record(stored)

    async def get(
        self,
        run_id: str,
        decision_id: str,
        principal: TraderPrincipal,
        revision: int | None = None,
    ) -> NextResearchDecisionRecord:
        """Return one latest or exact revision to an authorized human."""
        self._require_human(principal)
        async with self._repository.session() as session:
            await session.require_storage()
            result = await session.get(run_id, decision_id, revision)
        if result is None:
            raise NextResearchDecisionNotFound("next research decision not found")
        return _record(result)

    async def list(
        self,
        run_id: str,
        *,
        limit: int,
        offset: int,
        principal: TraderPrincipal,
    ) -> NextResearchDecisionsResponse:
        """Return latest revisions for one reviewed run."""
        self._require_human(principal)
        async with self._repository.session() as session:
            await session.require_storage()
            rows, total = await session.list(run_id, limit, offset)
        return NextResearchDecisionsResponse(
            items=tuple(_record(item) for item in rows),
            page=PageInfo(limit=limit, offset=offset, total=total, has_more=offset + limit < total),
        )

    @staticmethod
    def _require_human(principal: TraderPrincipal) -> None:
        """Keep agent and MCP identities outside the human decision command."""
        if not is_human_operator_principal(principal.principal_id):
            raise NextDecisionAuthorityError(
                "Recording a next research decision requires a human operator principal"
            )


__all__ = [
    "NextDecisionAuthorityError",
    "NextDecisionDatabaseUnavailable",
    "NextDecisionRevisionConflict",
    "NextResearchDecisionConflict",
    "NextResearchDecisionService",
    "NextResearchDecisionStorageUnavailable",
]
