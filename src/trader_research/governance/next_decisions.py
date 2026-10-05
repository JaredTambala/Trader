"""Human-owned, append-only research next-decision artifacts.

The review boundary records what a human decided after inspecting a run.  The
artifact carries exact evidence references and a bounded successor experiment;
it never turns a review conclusion into a deployment approval or a model-owned
decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Mapping, Sequence

from trader_research.foundation import (
    ApplicationResult,
    ResearchArtifactNotFound,
    ResearchArtifactRecord,
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    error_result,
    json_payload_hash,
    jsonable,
    parse_research_artifact_uri,
    stable_research_id,
    success_result,
)

from .artifacts import (
    BACKTEST_RUN,
    DATASET_MANIFEST,
    DATA_LOAD_EVIDENCE,
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    EVALUATION_REPORT,
    IMPLEMENTATION_VERSION,
    MULTIPLE_TESTING_REPORT,
    PARAMETER_OPTIMIZATION_EVALUATION_REPORT,
    PARAMETER_OPTIMIZATION_ROBUSTNESS_REPORT,
    RESEARCH_NEXT_DECISION,
    ROBUSTNESS_REPORT,
    STRATEGY_SPECIFICATION,
    RISK_STACK_SPECIFICATION,
)
from .handoffs import ArtifactReportRef


RESEARCH_RECORD_NEXT_DECISION = "research_record_next_decision"
RESEARCH_GET_NEXT_DECISION = "research_get_next_decision"


class NextDecisionOutcome(StrEnum):
    """Human decision after reviewing one exact research run."""

    REJECT = "reject"
    REFINE = "refine"
    CONTINUE = "continue"


_ALLOWED_FIELDS = frozenset(
    {
        "artifact_type",
        "schema_version",
        "artifact_id",
        "decision_id",
        "revision",
        "outcome",
        "rationale",
        "operator",
        "decided_at",
        "source_run_ref",
        "data_ref",
        "implementation_refs",
        "assumptions",
        "review_refs",
        "limitations",
        "next_experiment",
        "supersedes_artifact_id",
        "metadata",
        "decision_digest",
    }
)

_REVIEW_ARTIFACT_TYPES = frozenset(
    {
        EVALUATION_REPORT,
        MULTIPLE_TESTING_REPORT,
        ROBUSTNESS_REPORT,
        PARAMETER_OPTIMIZATION_EVALUATION_REPORT,
        PARAMETER_OPTIMIZATION_ROBUSTNESS_REPORT,
    }
)
_IMPLEMENTATION_ARTIFACT_TYPES = frozenset(
    {IMPLEMENTATION_VERSION, STRATEGY_SPECIFICATION, RISK_STACK_SPECIFICATION}
)
_DATA_ARTIFACT_TYPES = frozenset({DATASET_MANIFEST, DATA_LOAD_EVIDENCE})


@dataclass(frozen=True)
class BoundedNextExperiment:
    """A prospective experiment with explicit data, implementation, and limits."""

    question: str
    data_ref: ArtifactReportRef
    implementation_refs: tuple[ArtifactReportRef, ...]
    assumptions: Mapping[str, Any]
    evaluation_start: str
    evaluation_end: str
    max_runs: int
    success_criteria: tuple[str, ...]

    def __post_init__(self) -> None:
        """Reject an unbounded or internally inconsistent successor experiment."""
        _required_text(self.question, "next_experiment.question")
        if self.data_ref.artifact_type not in _DATA_ARTIFACT_TYPES:
            raise ValueError("next_experiment.data_ref must be a Data artifact")
        _require_implementation_refs(self.implementation_refs, "next_experiment")
        _require_mapping(self.assumptions, "next_experiment.assumptions")
        start = _parse_timestamp(self.evaluation_start, "next_experiment.evaluation_start")
        end = _parse_timestamp(self.evaluation_end, "next_experiment.evaluation_end")
        if end <= start:
            raise ValueError("next_experiment.evaluation_end must be after evaluation_start")
        if not 1 <= self.max_runs <= 100:
            raise ValueError("next_experiment.max_runs must be between 1 and 100")
        if not self.success_criteria or any(
            not str(item or "").strip() for item in self.success_criteria
        ):
            raise ValueError("next_experiment.success_criteria are required")
        if len(self.success_criteria) > 16:
            raise ValueError("next_experiment supports at most 16 success criteria")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the bounded successor experiment."""
        return {
            "question": self.question,
            "data_ref": self.data_ref.to_dict(),
            "implementation_refs": [item.to_dict() for item in self.implementation_refs],
            "assumptions": jsonable(self.assumptions),
            "evaluation_start": _parse_timestamp(self.evaluation_start, "evaluation_start").isoformat(),
            "evaluation_end": _parse_timestamp(self.evaluation_end, "evaluation_end").isoformat(),
            "max_runs": self.max_runs,
            "success_criteria": list(self.success_criteria),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BoundedNextExperiment":
        """Parse one bounded successor experiment from JSON data."""
        return cls(
            question=str(payload.get("question") or ""),
            data_ref=ArtifactReportRef.from_dict(_mapping(payload.get("data_ref"))),
            implementation_refs=tuple(
                ArtifactReportRef.from_dict(item)
                for item in _mapping_sequence(payload.get("implementation_refs"))
            ),
            assumptions=_mapping(payload.get("assumptions")),
            evaluation_start=str(payload.get("evaluation_start") or ""),
            evaluation_end=str(payload.get("evaluation_end") or ""),
            max_runs=_integer(payload, "max_runs"),
            success_criteria=_text_tuple(payload.get("success_criteria")),
        )


@dataclass(frozen=True)
class NextResearchDecision:
    """One immutable human decision and its exact review evidence chain."""

    decision_id: str
    revision: int
    outcome: NextDecisionOutcome
    rationale: str
    operator: str
    decided_at: str
    source_run_ref: ArtifactReportRef
    data_ref: ArtifactReportRef
    implementation_refs: tuple[ArtifactReportRef, ...]
    assumptions: Mapping[str, Any]
    review_refs: tuple[ArtifactReportRef, ...]
    limitations: tuple[str, ...]
    next_experiment: BoundedNextExperiment | None = None
    supersedes_artifact_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = "1"

    artifact_type = RESEARCH_NEXT_DECISION

    def __post_init__(self) -> None:
        """Validate decision authority, lineage, and successor bounds."""
        for value, label in (
            (self.decision_id, "decision_id"),
            (self.rationale, "rationale"),
            (self.operator, "operator"),
            (self.decided_at, "decided_at"),
        ):
            _required_text(value, label)
        if self.revision <= 0:
            raise ValueError("revision must be positive")
        if not isinstance(self.outcome, NextDecisionOutcome):
            raise ValueError("outcome must be a NextDecisionOutcome")
        if self.source_run_ref.artifact_type != BACKTEST_RUN:
            raise ValueError("source_run_ref must be a backtest_run artifact")
        if self.data_ref.artifact_type not in _DATA_ARTIFACT_TYPES:
            raise ValueError("data_ref must be a Data artifact")
        _require_implementation_refs(self.implementation_refs, "decision")
        _require_mapping(self.assumptions, "assumptions")
        if not self.review_refs:
            raise ValueError("review_refs are required")
        if any(item.artifact_type not in _REVIEW_ARTIFACT_TYPES for item in self.review_refs):
            raise ValueError("review_refs must contain review artifacts")
        if not self.limitations or any(not str(item or "").strip() for item in self.limitations):
            raise ValueError("limitations are required")
        if len(self.limitations) > 32:
            raise ValueError("decision supports at most 32 limitations")
        _parse_timestamp(self.decided_at, "decided_at")
        if self.outcome in {NextDecisionOutcome.REFINE, NextDecisionOutcome.CONTINUE}:
            if self.next_experiment is None:
                raise ValueError(f"{self.outcome.value} decisions require next_experiment")
        elif self.next_experiment is not None:
            raise ValueError("reject decisions cannot include next_experiment")
        _require_mapping(self.metadata, "metadata")

    @property
    def decision_digest(self) -> str:
        """Return the digest of the immutable decision content."""
        return json_payload_hash(self._identity_payload())

    @property
    def artifact_id(self) -> str:
        """Return a content-derived canonical artifact identity."""
        return stable_research_id("research_next_decision", self._identity_payload())

    def to_dict(self) -> dict[str, Any]:
        """Serialize the complete canonical decision payload."""
        return {
            "artifact_type": self.artifact_type,
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id,
            **self._identity_payload(),
            "decision_digest": self.decision_digest,
        }

    def _identity_payload(self) -> dict[str, Any]:
        """Return fields that determine the immutable revision identity."""
        return {
            "decision_id": self.decision_id,
            "revision": self.revision,
            "outcome": self.outcome.value,
            "rationale": self.rationale,
            "operator": self.operator,
            "decided_at": _parse_timestamp(self.decided_at, "decided_at").isoformat(),
            "source_run_ref": self.source_run_ref.to_dict(),
            "data_ref": self.data_ref.to_dict(),
            "implementation_refs": [item.to_dict() for item in self.implementation_refs],
            "assumptions": jsonable(self.assumptions),
            "review_refs": [item.to_dict() for item in self.review_refs],
            "limitations": list(self.limitations),
            "next_experiment": (
                self.next_experiment.to_dict() if self.next_experiment is not None else None
            ),
            "supersedes_artifact_id": self.supersedes_artifact_id,
            "metadata": jsonable(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "NextResearchDecision":
        """Parse and verify one serialized decision revision."""
        unknown = sorted(set(payload) - _ALLOWED_FIELDS)
        if unknown:
            raise ValueError("next decision contains unknown fields: " + ", ".join(unknown))
        _expect_constant(payload, "artifact_type", cls.artifact_type)
        _expect_constant(payload, "schema_version", "1")
        try:
            outcome = NextDecisionOutcome(str(payload.get("outcome") or ""))
        except ValueError as exc:
            raise ValueError("unsupported next decision outcome") from exc
        decision = cls(
            decision_id=str(payload.get("decision_id") or ""),
            revision=_integer(payload, "revision"),
            outcome=outcome,
            rationale=str(payload.get("rationale") or ""),
            operator=str(payload.get("operator") or ""),
            decided_at=str(payload.get("decided_at") or ""),
            source_run_ref=ArtifactReportRef.from_dict(_mapping(payload.get("source_run_ref"))),
            data_ref=ArtifactReportRef.from_dict(_mapping(payload.get("data_ref"))),
            implementation_refs=tuple(
                ArtifactReportRef.from_dict(item)
                for item in _mapping_sequence(payload.get("implementation_refs"))
            ),
            assumptions=_mapping(payload.get("assumptions")),
            review_refs=tuple(
                ArtifactReportRef.from_dict(item)
                for item in _mapping_sequence(payload.get("review_refs"))
            ),
            limitations=_text_tuple(payload.get("limitations")),
            next_experiment=(
                BoundedNextExperiment.from_dict(_mapping(payload.get("next_experiment")))
                if payload.get("next_experiment") is not None
                else None
            ),
            supersedes_artifact_id=_optional_text(payload.get("supersedes_artifact_id")),
            metadata=_mapping(payload.get("metadata")),
            schema_version=str(payload.get("schema_version") or "1"),
        )
        supplied_digest = str(payload.get("decision_digest") or "")
        if supplied_digest and supplied_digest != decision.decision_digest:
            raise ValueError("decision_digest does not match decision content")
        supplied_id = str(payload.get("artifact_id") or "")
        if supplied_id and supplied_id != decision.artifact_id:
            raise ValueError("artifact_id does not match decision content")
        return decision


def build_next_research_decision(
    *,
    decision_id: str,
    revision: int,
    outcome: NextDecisionOutcome,
    rationale: str,
    operator: str,
    decided_at: str,
    source_run_ref: ArtifactReportRef,
    data_ref: ArtifactReportRef,
    implementation_refs: Sequence[ArtifactReportRef],
    assumptions: Mapping[str, Any],
    review_refs: Sequence[ArtifactReportRef],
    limitations: Sequence[str],
    next_experiment: BoundedNextExperiment | None = None,
    supersedes_artifact_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> NextResearchDecision:
    """Build one validated immutable next-decision revision."""
    return NextResearchDecision(
        decision_id=decision_id,
        revision=revision,
        outcome=outcome,
        rationale=rationale,
        operator=operator,
        decided_at=decided_at,
        source_run_ref=source_run_ref,
        data_ref=data_ref,
        implementation_refs=tuple(implementation_refs),
        assumptions=dict(assumptions),
        review_refs=tuple(review_refs),
        limitations=tuple(limitations),
        next_experiment=next_experiment,
        supersedes_artifact_id=supersedes_artifact_id,
        metadata=dict(metadata or {}),
    )


def create_next_research_decision(
    payload: Mapping[str, Any],
    *,
    artifact_store: ResearchArtifactStore | None,
    requested_by: str,
    actor: str,
) -> ApplicationResult:
    """Validate evidence and persist one human-owned immutable revision."""
    if artifact_store is None:
        return error_result(
            command=RESEARCH_RECORD_NEXT_DECISION,
            code="research_artifact_store_required",
            message="A ResearchArtifactStore is required.",
        )
    try:
        _require_human_principal(requested_by, "requested_by")
        _require_human_principal(actor, "actor")
        decision = NextResearchDecision.from_dict(payload)
        if decision.operator != actor:
            raise ValueError("decision operator must match the authenticated actor")
        _validate_references(artifact_store, decision)
        try:
            existing = artifact_store.load_artifact_record(
                RESEARCH_NEXT_DECISION, decision.artifact_id
            )
        except ResearchArtifactNotFound:
            existing = None
        if existing is not None:
            if dict(existing.payload) != decision.to_dict():
                raise ResearchArtifactStoreError(
                    f"conflicting immutable {RESEARCH_NEXT_DECISION}: {decision.artifact_id}"
                )
            return success_result(
                command=RESEARCH_RECORD_NEXT_DECISION,
                data={"research_next_decision": decision.to_dict()},
                artifacts={"research_next_decision": existing.reference().to_dict()},
            )
        _validate_revision_lineage(artifact_store, decision)
        record = _save_immutable(
            artifact_store,
            decision=decision,
            requested_by=requested_by,
            actor=actor,
        )
    except (ValueError, ResearchArtifactStoreError) as exc:
        return error_result(
            command=RESEARCH_RECORD_NEXT_DECISION,
            code="research_next_decision_failed",
            message=str(exc),
        )
    return success_result(
        command=RESEARCH_RECORD_NEXT_DECISION,
        data={"research_next_decision": decision.to_dict()},
        artifacts={"research_next_decision": record.reference().to_dict()},
    )


def get_next_research_decision(
    decision_ref: str,
    *,
    artifact_store: ResearchArtifactStore | None,
) -> ApplicationResult:
    """Resolve one exact immutable next-decision revision."""
    if artifact_store is None:
        return error_result(
            command=RESEARCH_GET_NEXT_DECISION,
            code="research_artifact_store_required",
            message="A ResearchArtifactStore is required.",
        )
    try:
        artifact_id = str(decision_ref or "").strip()
        if decision_ref.startswith("research://"):
            artifact_type, artifact_id = parse_research_artifact_uri(decision_ref)
            if artifact_type != RESEARCH_NEXT_DECISION:
                raise ValueError("decision URI has the wrong artifact type")
        record = artifact_store.load_artifact_record(RESEARCH_NEXT_DECISION, artifact_id)
        decision = NextResearchDecision.from_dict(record.payload)
    except (ValueError, ResearchArtifactNotFound, ResearchArtifactStoreError) as exc:
        return error_result(
            command=RESEARCH_GET_NEXT_DECISION,
            code="research_next_decision_resolution_failed",
            message=str(exc),
        )
    return success_result(
        command=RESEARCH_GET_NEXT_DECISION,
        data={"research_next_decision": decision.to_dict()},
        artifacts={"research_next_decision": record.reference().to_dict()},
    )


def _validate_references(store: ResearchArtifactStore, decision: NextResearchDecision) -> None:
    """Resolve every exact ref and reject missing or incompatible evidence."""
    source = _resolve_reference(store, decision.source_run_ref)
    source_payload = dict(source.payload)
    run_id = str(source_payload.get("run_id") or source.artifact_id)
    if decision.source_run_ref.artifact_id != run_id and decision.source_run_ref.metadata.get("run_id") != run_id:
        raise ValueError("source_run_ref does not identify the cited run")
    data = _resolve_reference(store, decision.data_ref)
    _match_ref_metadata(decision.data_ref, data)
    for reference in decision.implementation_refs:
        record = _resolve_reference(store, reference)
        _match_ref_metadata(reference, record)
    for reference in decision.review_refs:
        record = _resolve_reference(store, reference)
        if (record.status or "").lower() in {"missing", "incompatible", "blocked", "failed", "error"}:
            raise ValueError(f"review evidence is not actionable: {reference.artifact_id}")
        _match_ref_metadata(reference, record)
    if decision.next_experiment is not None:
        _resolve_reference(store, decision.next_experiment.data_ref)
        for reference in decision.next_experiment.implementation_refs:
            _resolve_reference(store, reference)


def _validate_revision_lineage(store: ResearchArtifactStore, decision: NextResearchDecision) -> None:
    """Require contiguous append-only revisions for one decision stream."""
    records = [
        NextResearchDecision.from_dict(record.payload)
        for record in store.list_artifacts(artifact_type=RESEARCH_NEXT_DECISION)
        if record.payload.get("decision_id") == decision.decision_id
    ]
    if not records:
        if decision.revision != 1:
            raise ValueError("the first next-decision revision must be 1")
        if decision.supersedes_artifact_id is not None:
            raise ValueError("the first next-decision revision cannot supersede another artifact")
        return
    latest = max(records, key=lambda item: item.revision)
    if decision.revision != latest.revision + 1:
        raise ValueError("next-decision revision must append exactly after the latest revision")
    if decision.supersedes_artifact_id != latest.artifact_id:
        raise ValueError("next-decision revision must supersede the latest artifact")


def _save_immutable(
    store: ResearchArtifactStore,
    *,
    decision: NextResearchDecision,
    requested_by: str,
    actor: str,
) -> ResearchArtifactRecord:
    """Persist without overwriting a conflicting immutable artifact."""
    payload = decision.to_dict()
    try:
        existing = store.load_artifact_record(RESEARCH_NEXT_DECISION, decision.artifact_id)
    except ResearchArtifactNotFound:
        return store.save_artifact(
            artifact_type=RESEARCH_NEXT_DECISION,
            artifact_id=decision.artifact_id,
            domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[RESEARCH_NEXT_DECISION],
            producer_tool=RESEARCH_RECORD_NEXT_DECISION,
            payload=payload,
            requested_by=requested_by,
            actor=actor,
            status=decision.outcome.value,
            source_hash=decision.decision_digest,
        )
    if dict(existing.payload) != payload:
        raise ResearchArtifactStoreError(
            f"conflicting immutable {RESEARCH_NEXT_DECISION}: {decision.artifact_id}"
        )
    return existing


def _resolve_reference(store: ResearchArtifactStore, reference: ArtifactReportRef) -> ResearchArtifactRecord:
    """Resolve one typed canonical reference and verify its URI and owner."""
    record = store.load_artifact_record(reference.artifact_type, reference.artifact_id)
    if record.uri != reference.uri:
        raise ValueError(f"artifact reference URI does not match {reference.artifact_id}")
    if record.domain_owner != reference.domain_owner:
        raise ValueError(f"artifact reference owner does not match {reference.artifact_id}")
    return record


def _match_ref_metadata(reference: ArtifactReportRef, record: ResearchArtifactRecord) -> None:
    """Revalidate optional payload/source hashes pinned by a reference."""
    metadata = reference.metadata
    expected_source_hash = metadata.get("source_hash")
    if expected_source_hash is not None and expected_source_hash != record.source_hash:
        raise ValueError(f"artifact source hash has changed: {reference.artifact_id}")
    expected_payload_hash = metadata.get("payload_sha256")
    if expected_payload_hash is not None and expected_payload_hash != json_payload_hash(record.payload):
        raise ValueError(f"artifact payload has changed: {reference.artifact_id}")


def _require_implementation_refs(refs: Sequence[ArtifactReportRef], label: str) -> None:
    """Require at least one exact strategy/risk implementation reference."""
    if not refs:
        raise ValueError(f"{label}.implementation_refs are required")
    if any(item.artifact_type not in _IMPLEMENTATION_ARTIFACT_TYPES for item in refs):
        raise ValueError(f"{label}.implementation_refs must contain implementation artifacts")


def _require_human_principal(value: str, label: str) -> None:
    """Reject registered agent and MCP identities at the human decision gate."""
    text = str(value or "").strip().lower()
    if not text or not text.startswith(("human:", "operator:")):
        raise ValueError(f"{label} must be a human principal")


def _parse_timestamp(value: str, label: str) -> datetime:
    """Parse an aware ISO-8601 timestamp and normalize it to UTC."""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _required_text(value: object, label: str) -> str:
    """Require non-empty bounded text."""
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} is required")
    if len(text) > 4_000:
        raise ValueError(f"{label} exceeds 4000 characters")
    return text


def _require_mapping(value: Mapping[str, Any], label: str) -> None:
    """Require a JSON object at a contract boundary."""
    if not isinstance(jsonable(value), Mapping):
        raise ValueError(f"{label} must be a JSON object")


def _mapping(value: object) -> Mapping[str, Any]:
    """Normalize a JSON object or reject the boundary value."""
    if not isinstance(value, Mapping):
        raise ValueError("expected a JSON object")
    return dict(value)


def _mapping_sequence(value: object) -> tuple[Mapping[str, Any], ...]:
    """Normalize a sequence of JSON objects."""
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("expected a sequence of JSON objects")
    if any(not isinstance(item, Mapping) for item in value):
        raise ValueError("expected a sequence of JSON objects")
    return tuple(dict(item) for item in value)


def _text_tuple(value: object) -> tuple[str, ...]:
    """Normalize a sequence of non-empty text values."""
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("expected a sequence of text values")
    result = tuple(str(item).strip() for item in value)
    if any(not item for item in result):
        raise ValueError("text sequence values are required")
    return result


def _integer(payload: Mapping[str, Any], key: str) -> int:
    """Read one strict integer field."""
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _optional_text(value: object) -> str | None:
    """Normalize an optional text field."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _expect_constant(payload: Mapping[str, Any], key: str, expected: str) -> None:
    """Validate an optional serialized schema constant."""
    value = payload.get(key)
    if value is not None and value != expected:
        raise ValueError(f"{key} must be {expected}")


__all__ = [
    "BoundedNextExperiment",
    "NextDecisionOutcome",
    "NextResearchDecision",
    "RESEARCH_GET_NEXT_DECISION",
    "RESEARCH_RECORD_NEXT_DECISION",
    "build_next_research_decision",
    "create_next_research_decision",
    "get_next_research_decision",
]
