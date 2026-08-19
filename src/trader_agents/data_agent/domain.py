"""Define strict requests and task construction for the Data specialist.

The values in this module normalize market-data scope before any MCP call. They
describe provider context and optional idempotent sample loading, but never carry
tool names, transport responses, credentials, or executable arguments.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from trader_research.foundation import DATA_DOMAIN_OWNER, stable_research_id
from trader_research.governance import (
    DATASET_MANIFEST,
    DATA_QUALITY_REPORT,
    ArtifactCardinality,
    ArtifactSlot,
    CapabilitySideEffect,
    DataRequirement,
    ResearchObjective,
    ResearchObjectiveStatus,
)

from trader_agents.specialists import SpecialistTask


DATA_SPECIALIST_AUTHORITY = "data_agent"
"""Registered decision authority used by the Data specialist."""

DATASET_MANIFEST_TASK_SLOT = "dataset_manifest"
"""Task output slot containing one canonical dataset manifest."""

DATA_QUALITY_REPORT_TASK_SLOT = "data_quality_report"
"""Task output slot containing one canonical data-quality report."""

ALLOW_SAMPLE_DATA_LOADING_GATE = "allow_sample_data_loading"
"""Policy gate required before the specialist may load checked-in sample data."""

_DISCOVERY_SOURCES = frozenset(
    {"local", "configured", "configured_source", "provider", "merged"}
)


class DataLoadingMode(str, Enum):
    """Loading modes whose exact replay behavior is safe for specialist use."""

    SAMPLE = "sample"


@dataclass(frozen=True)
class DataLoadingIntent:
    """Explicit request to load data before canonical evidence is captured.

    Only checked-in sample loading is supported because its event writes are
    idempotent. Arbitrary provider backfills remain outside this specialist until
    their replay contract is proven.

    Attributes:
        mode: Proven idempotent loading mode requested by the caller.
    """

    mode: DataLoadingMode

    def __post_init__(self) -> None:
        """Reject loading modes that bypass the closed replay-safe enum."""
        if not isinstance(self.mode, DataLoadingMode):
            raise ValueError("Data specialist loading mode must be sample")

    def to_dict(self) -> dict[str, str]:
        """Serialize the loading intent into its strict public shape."""
        return {"mode": self.mode.value}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DataLoadingIntent":
        """Parse a loading intent and reject unsupported or unknown fields."""
        _reject_unknown_fields(payload, {"mode"}, "data loading intent")
        try:
            mode = DataLoadingMode(str(payload.get("mode") or ""))
        except ValueError as exc:
            raise ValueError("Data specialist loading mode must be sample") from exc
        return cls(mode=mode)


@dataclass(frozen=True)
class DataSpecialistRequest:
    """Normalized market-data scope assigned to the Data specialist.

    Attributes:
        data_requirement: Bounded symbols, storage asset class, timeframe, and
            inclusive UTC window.
        provider: Optional requested market-data provider.
        instrument_type: Optional provider-scoped instrument type.
        bar_type: Optional provider-scoped bar type.
        discovery_source: Approved discovery source passed to symbol validation.
        loading_intent: Optional proven-idempotent loading request.
    """

    data_requirement: DataRequirement
    provider: str | None = None
    instrument_type: str | None = None
    bar_type: str | None = None
    discovery_source: str = "configured_source"
    loading_intent: DataLoadingIntent | None = None

    def __post_init__(self) -> None:
        """Normalize scope identity and reject invalid discovery context."""
        if not isinstance(self.data_requirement, DataRequirement):
            raise ValueError("data_requirement must be a DataRequirement")
        if self.loading_intent is not None and not isinstance(
            self.loading_intent, DataLoadingIntent
        ):
            raise ValueError("loading_intent must be a DataLoadingIntent")
        requirement = _normalize_requirement(self.data_requirement)
        object.__setattr__(self, "data_requirement", requirement)
        object.__setattr__(self, "provider", _optional_selector(self.provider))
        object.__setattr__(
            self,
            "instrument_type",
            _optional_selector(self.instrument_type),
        )
        object.__setattr__(self, "bar_type", _optional_selector(self.bar_type))
        discovery_source = str(self.discovery_source or "").strip().lower()
        if discovery_source not in _DISCOVERY_SOURCES:
            raise ValueError(
                "Data specialist discovery_source must be one of: "
                + ", ".join(sorted(_DISCOVERY_SOURCES))
            )
        object.__setattr__(self, "discovery_source", discovery_source)
        if discovery_source == "provider" and self.provider is None:
            raise ValueError("provider discovery requires an explicit provider")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the normalized Data specialist request."""
        return {
            "data_requirement": self.data_requirement.to_dict(),
            "provider": self.provider,
            "instrument_type": self.instrument_type,
            "bar_type": self.bar_type,
            "discovery_source": self.discovery_source,
            "loading_intent": (
                self.loading_intent.to_dict()
                if self.loading_intent is not None
                else None
            ),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DataSpecialistRequest":
        """Parse a strict Data specialist request from plain data.

        Args:
            payload: Complete role-specific request mapping.

        Returns:
            Validated and normalized request.

        Raises:
            ValueError: If the request is unbounded, contradictory, or contains
                unknown fields or an unsupported loading mode.
        """
        _reject_unknown_fields(
            payload,
            {
                "data_requirement",
                "provider",
                "instrument_type",
                "bar_type",
                "discovery_source",
                "loading_intent",
            },
            "Data specialist request",
        )
        raw_requirement = _mapping(
            payload.get("data_requirement"),
            "data_requirement",
        )
        _reject_unknown_fields(
            raw_requirement,
            {"symbols", "asset_class", "timeframe", "start", "end", "source"},
            "data requirement",
        )
        raw_loading = payload.get("loading_intent")
        loading_intent = (
            None
            if raw_loading is None
            else DataLoadingIntent.from_dict(_mapping(raw_loading, "loading_intent"))
        )
        return cls(
            data_requirement=DataRequirement.from_dict(raw_requirement),
            provider=_optional_text(payload.get("provider")),
            instrument_type=_optional_text(payload.get("instrument_type")),
            bar_type=_optional_text(payload.get("bar_type")),
            discovery_source=str(
                payload.get("discovery_source") or "configured_source"
            ),
            loading_intent=loading_intent,
        )


def build_data_specialist_task(
    *,
    request: DataSpecialistRequest,
    objective: ResearchObjective,
    requested_by: str,
    actor: str,
    permit_local_mutation: bool,
    approve_sample_loading: bool = False,
) -> SpecialistTask:
    """Build one stable specialist task for market-data fitness evidence.

    Local mutation permission covers canonical snapshot persistence as well as
    optional sample loading. Loading approval is a separate policy gate and may
    be granted only when the request actually contains a loading intent.

    Args:
        request: Strict Data-specific market-data scope.
        objective: Approved operator-owned research objective.
        requested_by: Workflow or request requiring the Data evidence.
        actor: Identity routing the task to the Data specialist.
        permit_local_mutation: Whether local persistence actions are permitted.
        approve_sample_loading: Whether checked-in sample loading is approved.

    Returns:
        Stable generic specialist task with two exact Data output slots.

    Raises:
        ValueError: If the objective is not approved or policy input conflicts
            with the requested loading behavior.
    """
    if objective.status is not ResearchObjectiveStatus.APPROVED:
        raise ValueError("Data specialist tasks require an approved objective")
    if not isinstance(permit_local_mutation, bool):
        raise ValueError("permit_local_mutation must be a boolean")
    if not isinstance(approve_sample_loading, bool):
        raise ValueError("approve_sample_loading must be a boolean")
    if approve_sample_loading and request.loading_intent is None:
        raise ValueError("sample loading approval requires an explicit loading intent")
    permitted_side_effects = [CapabilitySideEffect.READ_ONLY]
    if permit_local_mutation:
        permitted_side_effects.append(CapabilitySideEffect.LOCAL_MUTATING)
    policy_gates = (ALLOW_SAMPLE_DATA_LOADING_GATE,) if approve_sample_loading else ()
    identity = {
        "objective_id": objective.objective_id,
        "request": request.to_dict(),
        "requested_by": _required_text(requested_by, "requested_by"),
        "actor": _required_text(actor, "actor"),
        "permit_local_mutation": permit_local_mutation,
        "approve_sample_loading": approve_sample_loading,
    }
    return SpecialistTask(
        task_id=stable_research_id("data_specialist_task", identity),
        authority_key=DATA_SPECIALIST_AUTHORITY,
        objective=objective,
        requested_outputs=(
            _output_slot(DATASET_MANIFEST_TASK_SLOT, DATASET_MANIFEST),
            _output_slot(DATA_QUALITY_REPORT_TASK_SLOT, DATA_QUALITY_REPORT),
        ),
        input_refs=(),
        requested_by=str(identity["requested_by"]),
        actor=str(identity["actor"]),
        permitted_side_effects=tuple(permitted_side_effects),
        approved_policy_gates=policy_gates,
        specialist_input=request.to_dict(),
    )


def data_request_from_task(task: SpecialistTask) -> DataSpecialistRequest:
    """Parse and validate the role-specific request held by a Data task."""
    if task.authority_key != DATA_SPECIALIST_AUTHORITY:
        raise ValueError("specialist task is not addressed to the Data Agent")
    expected_slots = {
        DATASET_MANIFEST_TASK_SLOT: DATASET_MANIFEST,
        DATA_QUALITY_REPORT_TASK_SLOT: DATA_QUALITY_REPORT,
    }
    observed_slots = {slot.slot_id: slot for slot in task.requested_outputs}
    if set(observed_slots) != set(expected_slots) or any(
        slot.artifact_type != expected_slots[slot_id]
        or slot.domain_owner != DATA_DOMAIN_OWNER
        or slot.cardinality is not ArtifactCardinality.EXACTLY_ONE
        or not slot.required
        for slot_id, slot in observed_slots.items()
    ):
        raise ValueError(
            "Data specialist tasks require exact manifest and quality output slots"
        )
    if set(task.approved_policy_gates) - {ALLOW_SAMPLE_DATA_LOADING_GATE}:
        raise ValueError("Data specialist task contains an unknown policy gate")
    return DataSpecialistRequest.from_dict(task.specialist_input)


def _output_slot(slot_id: str, artifact_type: str) -> ArtifactSlot:
    return ArtifactSlot(
        slot_id=slot_id,
        artifact_type=artifact_type,
        domain_owner=DATA_DOMAIN_OWNER,
        cardinality=ArtifactCardinality.EXACTLY_ONE,
        required=True,
    )


def _normalize_requirement(requirement: DataRequirement) -> DataRequirement:
    symbols = tuple(str(symbol).strip().upper() for symbol in requirement.symbols)
    if any(not symbol for symbol in symbols):
        raise ValueError("data requirement symbols must be non-empty")
    if len(symbols) != len(set(symbols)):
        raise ValueError("data requirement symbols must be unique")
    start = _bounded_timestamp(requirement.start, "data requirement start")
    end = _bounded_timestamp(requirement.end, "data requirement end")
    start_value = datetime.fromisoformat(start)
    end_value = datetime.fromisoformat(end)
    if end_value < start_value:
        raise ValueError("data requirement end must not precede start")
    return DataRequirement(
        symbols=symbols,
        asset_class=_required_text(
            requirement.asset_class,
            "data requirement asset_class",
        ).lower(),
        timeframe=_required_text(
            requirement.timeframe,
            "data requirement timeframe",
        ),
        start=start,
        end=end,
        source=_optional_text(requirement.source),
    )


def _bounded_timestamp(value: object, label: str) -> str:
    text = _required_text(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def _reject_unknown_fields(
    payload: Mapping[str, Any],
    allowed: set[str],
    label: str,
) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"{label} has unknown fields: {', '.join(unknown)}")


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


def _required_text(value: object, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} is required")
    return text


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_selector(value: object) -> str | None:
    text = _optional_text(value)
    return text.lower().replace("-", "_") if text is not None else None
