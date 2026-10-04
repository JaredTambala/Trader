"""Persist immutable, falsifiable hypothesis and experiment briefs.

A hypothesis brief is the human-facing contract between an initial research
question and downstream Data, Strategy, and Evaluation work.  It keeps the
scientific intent in one canonical artifact, versions revisions instead of
rewriting them, and exposes only a bounded handoff reference to downstream
roles.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from trader_research.foundation import (
    ApplicationResult,
    ResearchArtifactNotFound,
    ResearchArtifactRecord,
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    error_result,
    json_payload_hash,
    jsonable,
    research_artifact_uri,
    stable_research_id,
    success_result,
)

from .artifacts import (
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    EXPERIMENT_DESIGN_AGENT_OWNER,
    HYPOTHESIS_AGENT_OWNER,
    HYPOTHESIS_CARD,
)
from .handoffs import ArtifactReportRef, DataRequirement


RESEARCH_PERSIST_HYPOTHESIS_BRIEF = "research_persist_hypothesis_brief"
# Keep a descriptive alias for callers that use the create vocabulary.
RESEARCH_CREATE_HYPOTHESIS_BRIEF = RESEARCH_PERSIST_HYPOTHESIS_BRIEF
RESEARCH_RESOLVE_HYPOTHESIS_BRIEF_HANDOFF = "research_resolve_hypothesis_brief_handoff"
HYPOTHESIS_BRIEF_STATUS_VALUES = frozenset({"draft", "proposed", "accepted"})
HYPOTHESIS_BRIEF_DOWNSTREAM_ROLES = (
    "Data Agent",
    "Strategy Engineering Agent",
    "Evaluation Agent",
)


@dataclass(frozen=True)
class HypothesisScope:
    """Intended universe and evaluation window for one hypothesis.

    ``universe`` stays textual so the brief can remain instrument-agnostic while
    a later Data handoff resolves exact symbols.  Optional symbols and exclusions
    make contradictory scope claims detectable before any downstream work runs.
    """

    universe: str
    timeframe: str
    start: str
    end: str
    asset_class: str | None = None
    source_policy: str | None = None
    symbols: tuple[str, ...] = ()
    excluded_symbols: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate window, universe, and explicit inclusion/exclusion rules."""
        _required_text(self.universe, "hypothesis scope universe")
        _required_text(self.timeframe, "hypothesis scope timeframe")
        _required_text(self.start, "hypothesis scope start")
        _required_text(self.end, "hypothesis scope end")
        _ordered_timestamps(self.start, self.end)
        symbols = _normalize_symbols(self.symbols, "hypothesis scope symbols")
        excluded = _normalize_symbols(
            self.excluded_symbols,
            "hypothesis scope excluded_symbols",
        )
        overlap = sorted(set(symbols).intersection(excluded))
        if overlap:
            raise ValueError(
                "hypothesis scope is contradictory: symbols are both included and "
                "excluded: "
                + ", ".join(overlap)
            )
        object.__setattr__(self, "symbols", symbols)
        object.__setattr__(self, "excluded_symbols", excluded)
        if self.asset_class is not None:
            _required_text(self.asset_class, "hypothesis scope asset_class")
        if self.source_policy is not None:
            _required_text(self.source_policy, "hypothesis scope source_policy")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the bounded scope without adding Data-owned evidence."""
        payload: dict[str, Any] = {
            "universe": self.universe,
            "timeframe": self.timeframe,
            "start": self.start,
            "end": self.end,
            "symbols": list(self.symbols),
            "excluded_symbols": list(self.excluded_symbols),
        }
        if self.asset_class is not None:
            payload["asset_class"] = self.asset_class
        if self.source_policy is not None:
            payload["source_policy"] = self.source_policy
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HypothesisScope":
        """Parse and validate a scope mapping."""
        _reject_unknown_fields(
            payload,
            {
                "universe",
                "timeframe",
                "start",
                "end",
                "asset_class",
                "source_policy",
                "symbols",
                "excluded_symbols",
            },
            "hypothesis scope",
        )
        return cls(
            universe=str(payload.get("universe") or ""),
            timeframe=str(payload.get("timeframe") or ""),
            start=str(payload.get("start") or ""),
            end=str(payload.get("end") or ""),
            asset_class=(
                str(payload["asset_class"])
                if payload.get("asset_class") is not None
                else None
            ),
            source_policy=(
                str(payload["source_policy"])
                if payload.get("source_policy") is not None
                else None
            ),
            symbols=_text_sequence(payload.get("symbols", ()), "hypothesis scope symbols"),
            excluded_symbols=_text_sequence(
                payload.get("excluded_symbols", ()),
                "hypothesis scope excluded_symbols",
            ),
        )


@dataclass(frozen=True)
class HypothesisBrief:
    """Immutable, revisioned research intent handed to downstream specialists.

    The brief keeps the scientific claim separate from executable strategy and
    risk specifications while recording the intent those later specifications
    must satisfy.  Data requirements are typed using the shared bounded
    requirement contract so Data can resolve them without copying the brief.
    """

    brief_id: str
    revision: int
    question: str
    mechanism: str
    falsifier: str
    scope: HypothesisScope
    data_requirements: tuple[DataRequirement, ...]
    strategy_intent: str
    risk_intent: str
    expected_evidence: tuple[str, ...]
    assumptions: tuple[str, ...]
    decision_rules: Mapping[str, str]
    requested_by: str
    actor: str
    supersedes_id: str | None = None
    status: str = "proposed"

    artifact_type = HYPOTHESIS_CARD

    def __post_init__(self) -> None:
        """Reject incomplete claims, invalid revisions, and unauthorized lifecycle states."""
        _required_text(self.brief_id, "hypothesis brief_id")
        if not isinstance(self.scope, HypothesisScope):
            if not isinstance(self.scope, Mapping):
                raise ValueError("hypothesis scope must be a mapping or HypothesisScope")
            object.__setattr__(self, "scope", HypothesisScope.from_dict(self.scope))
        if isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("hypothesis revision must be a positive integer")
        _required_text(self.question, "hypothesis question")
        _required_text(self.mechanism, "hypothesis mechanism")
        _required_text(self.falsifier, "hypothesis falsifier")
        data_requirements = _normalize_data_requirements(self.data_requirements)
        if not data_requirements:
            raise ValueError("hypothesis data_requirements are required")
        _required_text(self.strategy_intent, "hypothesis strategy_intent")
        _required_text(self.risk_intent, "hypothesis risk_intent")
        excluded_symbols = set(self.scope.excluded_symbols)
        for requirement in data_requirements:
            requirement_symbols = {
                str(symbol).strip().upper() for symbol in requirement.symbols
            }
            overlap = sorted(excluded_symbols.intersection(requirement_symbols))
            if overlap:
                raise ValueError(
                    "hypothesis data requirement contradicts excluded scope symbols: "
                    + ", ".join(overlap)
                )
        _required_text(self.requested_by, "hypothesis requested_by")
        _required_text(self.actor, "hypothesis actor")
        if self.status not in HYPOTHESIS_BRIEF_STATUS_VALUES:
            raise ValueError(
                "hypothesis status must be one of: "
                + ", ".join(sorted(HYPOTHESIS_BRIEF_STATUS_VALUES))
            )
        _required_text_sequence(self.expected_evidence, "hypothesis expected_evidence")
        _required_text_sequence(self.assumptions, "hypothesis assumptions")
        if not isinstance(self.decision_rules, Mapping) or not self.decision_rules:
            raise ValueError("hypothesis decision_rules are required")
        normalized_rules = {
            _required_text(str(outcome), "hypothesis decision outcome"): _required_text(
                str(decision), "hypothesis decision rule"
            )
            for outcome, decision in self.decision_rules.items()
        }
        object.__setattr__(self, "data_requirements", data_requirements)
        object.__setattr__(self, "expected_evidence", tuple(self.expected_evidence))
        object.__setattr__(self, "assumptions", tuple(self.assumptions))
        object.__setattr__(self, "decision_rules", normalized_rules)
        if self.revision == 1 and self.supersedes_id is not None:
            raise ValueError("first hypothesis revision cannot supersede another brief")
        if self.revision > 1 and not str(self.supersedes_id or "").strip():
            raise ValueError("later hypothesis revisions must name supersedes_id")
        if not _authorized_actor(self.actor):
            raise ValueError(f"unauthorized hypothesis brief actor: {self.actor}")
        if self.status == "accepted" and not _human_actor(self.actor):
            raise ValueError("only a human operator may accept a hypothesis brief")

    @property
    def artifact_id(self) -> str:
        """Return the stable canonical identity for this brief revision."""
        return stable_research_id(
            HYPOTHESIS_CARD,
            {"brief_id": self.brief_id, "revision": self.revision},
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the complete brief payload used for canonical persistence."""
        return {
            "artifact_type": self.artifact_type,
            "brief_id": self.brief_id,
            "revision": self.revision,
            "artifact_id": self.artifact_id,
            "question": self.question,
            "mechanism": self.mechanism,
            "falsifier": self.falsifier,
            "scope": self.scope.to_dict(),
            "data_requirements": [item.to_dict() for item in self.data_requirements],
            "strategy_intent": self.strategy_intent,
            "risk_intent": self.risk_intent,
            "expected_evidence": list(self.expected_evidence),
            "assumptions": list(self.assumptions),
            "decision_rules": jsonable(self.decision_rules),
            "requested_by": self.requested_by,
            "actor": self.actor,
            "supersedes_id": self.supersedes_id,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HypothesisBrief":
        """Parse a closed JSON-compatible brief payload."""
        allowed = {
            "artifact_type",
            "brief_id",
            "revision",
            "artifact_id",
            "question",
            "mechanism",
            "falsifier",
            "scope",
            "data_requirements",
            "strategy_intent",
            "risk_intent",
            "expected_evidence",
            "assumptions",
            "decision_rules",
            "requested_by",
            "actor",
            "supersedes_id",
            "status",
        }
        _reject_unknown_fields(payload, allowed, "hypothesis brief")
        if payload.get("artifact_type") != HYPOTHESIS_CARD:
            raise ValueError(f"hypothesis brief artifact_type must be {HYPOTHESIS_CARD}")
        revision = payload.get("revision")
        if isinstance(revision, bool) or not isinstance(revision, int):
            raise ValueError("hypothesis revision must be a positive integer")
        brief = cls(
            brief_id=str(payload.get("brief_id") or ""),
            revision=revision,
            question=str(payload.get("question") or ""),
            mechanism=str(payload.get("mechanism") or ""),
            falsifier=str(payload.get("falsifier") or ""),
            scope=HypothesisScope.from_dict(_mapping(payload.get("scope"))),
            data_requirements=_normalize_data_requirements(
                payload.get("data_requirements"),
            ),
            strategy_intent=str(payload.get("strategy_intent") or ""),
            risk_intent=str(payload.get("risk_intent") or ""),
            expected_evidence=_text_sequence(
                payload.get("expected_evidence"),
                "hypothesis expected_evidence",
            ),
            assumptions=_text_sequence(
                payload.get("assumptions"),
                "hypothesis assumptions",
            ),
            decision_rules=_string_mapping(
                payload.get("decision_rules"),
                "hypothesis decision_rules",
            ),
            requested_by=str(payload.get("requested_by") or ""),
            actor=str(payload.get("actor") or ""),
            supersedes_id=(
                str(payload["supersedes_id"])
                if payload.get("supersedes_id") is not None
                else None
            ),
            status=str(payload.get("status") or ""),
        )
        supplied_id = payload.get("artifact_id")
        if supplied_id is not None and str(supplied_id) != brief.artifact_id:
            raise ValueError("hypothesis brief artifact_id does not match revision identity")
        return brief


@dataclass(frozen=True)
class HypothesisBriefHandoff:
    """Bounded downstream handoff that preserves brief identity and decisions."""

    brief_ref: ArtifactReportRef
    brief_id: str
    revision: int
    target_roles: tuple[str, ...] = HYPOTHESIS_BRIEF_DOWNSTREAM_ROLES
    decision_rules: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate handoff identity and downstream ownership targets."""
        if self.brief_ref.artifact_type != HYPOTHESIS_CARD:
            raise ValueError("hypothesis brief handoff must reference a hypothesis card")
        _required_text(self.brief_id, "hypothesis handoff brief_id")
        if isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("hypothesis handoff revision must be positive")
        expected_id = stable_research_id(
            HYPOTHESIS_CARD,
            {"brief_id": self.brief_id, "revision": self.revision},
        )
        if self.brief_ref.artifact_id != expected_id:
            raise ValueError("hypothesis brief handoff identity drift")
        if not self.target_roles:
            raise ValueError("hypothesis brief handoff target_roles are required")
        target_roles = tuple(
            _required_text(str(role), "hypothesis handoff target role")
            for role in self.target_roles
        )
        if len(target_roles) != len(set(target_roles)):
            raise ValueError("hypothesis brief handoff target_roles must be unique")
        unsupported_roles = sorted(
            set(target_roles).difference(HYPOTHESIS_BRIEF_DOWNSTREAM_ROLES)
        )
        if unsupported_roles:
            raise ValueError(
                "hypothesis brief handoff target_roles contain unsupported roles: "
                + ", ".join(unsupported_roles)
            )
        object.__setattr__(self, "target_roles", target_roles)
        normalized_rules = _normalized_decision_rules(self.decision_rules)
        if not normalized_rules:
            raise ValueError("hypothesis brief handoff decision_rules are required")
        object.__setattr__(self, "decision_rules", normalized_rules)
        metadata = self.brief_ref.metadata
        payload_hash = metadata.get("payload_sha256")
        if not isinstance(payload_hash, str) or len(payload_hash) != 64:
            raise ValueError("hypothesis brief handoff payload_sha256 is required")
        if metadata.get("brief_id") != self.brief_id:
            raise ValueError("hypothesis brief handoff metadata brief_id drift")
        if metadata.get("revision") != self.revision:
            raise ValueError("hypothesis brief handoff metadata revision drift")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the bounded reference and decision continuity."""
        return {
            "brief_ref": self.brief_ref.to_dict(),
            "brief_id": self.brief_id,
            "revision": self.revision,
            "target_roles": list(self.target_roles),
            "decision_rules": jsonable(self.decision_rules),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HypothesisBriefHandoff":
        """Parse and validate a downstream handoff."""
        return cls(
            brief_ref=ArtifactReportRef.from_dict(_mapping(payload.get("brief_ref"))),
            brief_id=str(payload.get("brief_id") or ""),
            revision=int(payload.get("revision") or 0),
            target_roles=_text_sequence(payload.get("target_roles"), "target_roles"),
            decision_rules=_string_mapping(
                payload.get("decision_rules"),
                "decision_rules",
            ),
        )


def persist_hypothesis_brief(
    *,
    brief: HypothesisBrief | Mapping[str, Any],
    artifact_store: ResearchArtifactStore | None,
    requested_by: str | None = None,
    actor: str | None = None,
) -> ApplicationResult:
    """Persist one immutable brief revision and return a downstream handoff.

    Exact retries of the same ``brief_id`` and revision return the original
    record. A changed payload for that identity fails closed. Later revisions
    must name and resolve the immediately preceding revision, preserving an
    append-only lineage.
    """
    command = RESEARCH_PERSIST_HYPOTHESIS_BRIEF
    if artifact_store is None:
        return error_result(
            command=command,
            code="research_artifact_store_required",
            message="A ResearchArtifactStore is required.",
        )
    try:
        parsed = brief if isinstance(brief, HypothesisBrief) else HypothesisBrief.from_dict(brief)
        _validate_attribution(parsed, requested_by=requested_by, actor=actor)
        _validate_revision_lineage(parsed, artifact_store)
        payload = parsed.to_dict()
        metadata = {
            "brief_id": parsed.brief_id,
            "revision": parsed.revision,
            "supersedes_id": parsed.supersedes_id,
            "scope_sha256": json_payload_hash(parsed.scope.to_dict()),
        }
        record, replay = _save_brief_idempotently(
            artifact_store,
            brief=parsed,
            payload=payload,
            metadata=metadata,
            command=command,
        )
        handoff = _build_handoff(parsed, record)
    except (ValueError, ResearchArtifactStoreError) as exc:
        return error_result(
            command=command,
            code="hypothesis_brief_persistence_failed",
            message=str(exc),
        )
    return success_result(
        command=command,
        data={
            "hypothesis_brief": payload,
            "downstream_handoff": handoff.to_dict(),
            "idempotent_replay": replay,
        },
        artifacts={
            "hypothesis_card": record.reference().to_dict(),
            "downstream_handoff": handoff.to_dict(),
        },
    )


def create_hypothesis_brief(
    *,
    brief: HypothesisBrief | Mapping[str, Any],
    artifact_store: ResearchArtifactStore | None,
    requested_by: str | None = None,
    actor: str | None = None,
) -> ApplicationResult:
    """Compatibility-named entry point for brief creation."""
    return persist_hypothesis_brief(
        brief=brief,
        artifact_store=artifact_store,
        requested_by=requested_by,
        actor=actor,
    )


def resolve_hypothesis_brief_handoff(
    *,
    handoff: HypothesisBriefHandoff | Mapping[str, Any],
    recipient: str,
    artifact_store: ResearchArtifactStore | None,
) -> ApplicationResult:
    """Resolve a digest-pinned brief for one authorized downstream recipient.

    The handoff is deliberately only a reference.  A recipient must be named
    in ``target_roles`` and the canonical artifact is re-read from the store;
    the reference's payload digest then protects the recipient from consuming
    a replaced or stale brief.  This is the executable boundary used by Data,
    Strategy Engineering, and Evaluation before they construct downstream
    artifacts.
    """
    command = RESEARCH_RESOLVE_HYPOTHESIS_BRIEF_HANDOFF
    if artifact_store is None:
        return error_result(
            command=command,
            code="research_artifact_store_required",
            message="A ResearchArtifactStore is required.",
        )
    try:
        parsed = (
            handoff
            if isinstance(handoff, HypothesisBriefHandoff)
            else HypothesisBriefHandoff.from_dict(handoff)
        )
        recipient_name = _required_text(recipient, "hypothesis handoff recipient")
        if recipient_name not in parsed.target_roles:
            raise ValueError(
                f"hypothesis handoff recipient is not authorized: {recipient_name}"
            )
        expected_hash = str(parsed.brief_ref.metadata.get("payload_sha256") or "")
        if not expected_hash:
            raise ValueError("hypothesis handoff payload_sha256 is required")
        record = artifact_store.load_artifact_record(
            parsed.brief_ref.artifact_type,
            parsed.brief_ref.artifact_id,
        )
        if record.artifact_type != HYPOTHESIS_CARD:
            raise ValueError("hypothesis handoff resolved an unexpected artifact type")
        if record.domain_owner != DOMAIN_OWNER_BY_ARTIFACT_TYPE[HYPOTHESIS_CARD]:
            raise ValueError("hypothesis handoff resolved an unauthorized artifact owner")
        actual_hash = json_payload_hash(record.payload)
        if actual_hash != expected_hash:
            raise ValueError("hypothesis handoff payload digest does not match canonical artifact")
        brief = HypothesisBrief.from_dict(record.payload)
        if brief.brief_id != parsed.brief_id or brief.revision != parsed.revision:
            raise ValueError("hypothesis handoff resolved brief identity drift")
        if dict(parsed.decision_rules) != dict(brief.decision_rules):
            raise ValueError("hypothesis handoff decision rules drift from canonical brief")
    except (ValueError, ResearchArtifactStoreError) as exc:
        return error_result(
            command=command,
            code="hypothesis_brief_handoff_resolution_failed",
            message=str(exc),
        )
    return success_result(
        command=command,
        data={
            "hypothesis_brief": brief.to_dict(),
            "recipient": recipient_name,
            "downstream_handoff": parsed.to_dict(),
        },
        artifacts={"hypothesis_card": record.reference().to_dict()},
    )


def _save_brief_idempotently(
    artifact_store: ResearchArtifactStore,
    *,
    brief: HypothesisBrief,
    payload: Mapping[str, Any],
    metadata: Mapping[str, Any],
    command: str,
) -> tuple[ResearchArtifactRecord, bool]:
    try:
        existing = artifact_store.load_artifact_record(HYPOTHESIS_CARD, brief.artifact_id)
    except ResearchArtifactNotFound:
        existing = None
    if existing is not None:
        if (
            existing.payload != payload
            or existing.domain_owner != DOMAIN_OWNER_BY_ARTIFACT_TYPE[HYPOTHESIS_CARD]
            or existing.producer_tool != command
            or existing.requested_by != brief.requested_by
            or existing.actor != brief.actor
            or existing.status != brief.status
            or dict(existing.metadata) != dict(metadata)
        ):
            raise ValueError("existing hypothesis brief revision conflicts")
        return existing, True
    record = artifact_store.save_artifact(
        artifact_type=HYPOTHESIS_CARD,
        artifact_id=brief.artifact_id,
        domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[HYPOTHESIS_CARD],
        producer_tool=command,
        payload=payload,
        requested_by=brief.requested_by,
        actor=brief.actor,
        status=brief.status,
        metadata=metadata,
        source_hash=json_payload_hash(payload),
    )
    return record, False


def _validate_revision_lineage(
    brief: HypothesisBrief,
    artifact_store: ResearchArtifactStore,
) -> None:
    if brief.revision == 1:
        return
    expected_prior_id = stable_research_id(
        HYPOTHESIS_CARD,
        {"brief_id": brief.brief_id, "revision": brief.revision - 1},
    )
    if brief.supersedes_id != expected_prior_id:
        raise ValueError(
            "hypothesis revision must supersede the immediately preceding revision"
        )
    try:
        prior = artifact_store.load_artifact_record(HYPOTHESIS_CARD, expected_prior_id)
    except ResearchArtifactNotFound as exc:
        raise ValueError("hypothesis superseded revision is not persisted") from exc
    prior_payload = HypothesisBrief.from_dict(prior.payload)
    if prior_payload.brief_id != brief.brief_id or prior_payload.revision != brief.revision - 1:
        raise ValueError("hypothesis superseded revision lineage is inconsistent")


def _validate_attribution(
    brief: HypothesisBrief,
    *,
    requested_by: str | None,
    actor: str | None,
) -> None:
    if requested_by is not None and requested_by.strip() != brief.requested_by:
        raise ValueError("hypothesis requested_by attribution drift")
    if actor is not None and actor.strip() != brief.actor:
        raise ValueError("hypothesis actor attribution drift")


def _build_handoff(
    brief: HypothesisBrief,
    record: ResearchArtifactRecord,
) -> HypothesisBriefHandoff:
    ref = ArtifactReportRef(
        artifact_id=record.artifact_id,
        artifact_type=record.artifact_type,
        domain_owner=record.domain_owner,
        uri=research_artifact_uri(record.artifact_type, record.artifact_id),
        metadata={
            "payload_sha256": json_payload_hash(record.payload),
            "revision": brief.revision,
            "brief_id": brief.brief_id,
        },
    )
    return HypothesisBriefHandoff(
        brief_ref=ref,
        brief_id=brief.brief_id,
        revision=brief.revision,
        decision_rules=brief.decision_rules,
    )


def _authorized_actor(actor: str) -> bool:
    return _human_actor(actor) or actor in {
        HYPOTHESIS_AGENT_OWNER,
        EXPERIMENT_DESIGN_AGENT_OWNER,
    }


def _human_actor(actor: str) -> bool:
    normalized = actor.strip().lower()
    return normalized.startswith("operator:") or normalized.startswith("human:")


def _ordered_timestamps(start: str, end: str) -> None:
    try:
        start_value = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_value = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("hypothesis scope start/end must be ISO-8601 timestamps") from exc
    if start_value.tzinfo is None or end_value.tzinfo is None:
        raise ValueError("hypothesis scope start/end must include a timezone")
    if end_value <= start_value:
        raise ValueError("hypothesis scope end must be after start")


def _normalize_symbols(value: Sequence[str], label: str) -> tuple[str, ...]:
    symbols = _text_sequence(value, label)
    for symbol in symbols:
        _required_text(symbol, label)
    normalized = tuple(dict.fromkeys(item.upper() for item in symbols))
    return normalized


def _normalize_data_requirements(value: object) -> tuple[DataRequirement, ...]:
    """Parse and validate the bounded market-data requirements in a brief."""
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("hypothesis data_requirements must be a sequence")
    requirements: list[DataRequirement] = []
    for item in value:
        if isinstance(item, DataRequirement):
            requirement = item
        elif isinstance(item, Mapping):
            requirement = DataRequirement.from_dict(item)
        else:
            raise ValueError(
                "hypothesis data_requirements entries must be DataRequirement mappings"
            )
        for symbol in requirement.symbols:
            _required_text(symbol, "hypothesis data requirement symbol")
        _required_text(requirement.asset_class, "hypothesis data requirement asset_class")
        _required_text(requirement.timeframe, "hypothesis data requirement timeframe")
        _required_text(requirement.start, "hypothesis data requirement start")
        _required_text(requirement.end, "hypothesis data requirement end")
        _ordered_timestamps(requirement.start, requirement.end)
        if requirement.source is not None:
            _required_text(requirement.source, "hypothesis data requirement source")
        requirements.append(requirement)
    return tuple(requirements)


def _required_text(value: str, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} is required")
    return text


def _required_text_sequence(value: Sequence[str], label: str) -> None:
    if not value:
        raise ValueError(f"{label} are required")
    for item in value:
        _required_text(str(item), label)


def _text_sequence(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a sequence")
    return tuple(str(item) for item in value)


def _string_mapping(value: object, label: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return {str(key): str(item) for key, item in value.items()}


def _normalized_decision_rules(value: object) -> dict[str, str]:
    """Normalize and validate outcome rules carried by a downstream handoff."""
    rules = _string_mapping(value, "hypothesis handoff decision_rules")
    return {
        _required_text(outcome, "hypothesis handoff decision outcome"): _required_text(
            decision,
            "hypothesis handoff decision rule",
        )
        for outcome, decision in rules.items()
    }


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("hypothesis scope must be a mapping")
    return value


def _reject_unknown_fields(
    payload: Mapping[str, Any],
    allowed: set[str],
    label: str,
) -> None:
    unknown = sorted(set(payload).difference(allowed))
    if unknown:
        raise ValueError(f"{label} has unknown fields: {', '.join(unknown)}")
