"""Execute Data specialist actions through validated MCP boundaries.

Each handler constructs arguments from ``DataSpecialistRequest``, validates the
MCP envelope, and returns only bounded summaries or canonical handoffs. Snapshot
artifacts are resolved through the injected canonical store before their refs are
accepted; raw envelopes and complete artifact payloads never enter graph state.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from trader_mcp.constants import (
    DATA_CREATE_RESEARCH_SNAPSHOT_TOOL,
    DATA_DISCOVER_SYMBOLS_TOOL,
    DATA_ENSURE_LOADED_TOOL,
)
from trader_research.foundation import (
    DATA_DOMAIN_OWNER,
    ResearchArtifactRecord,
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    json_payload_hash,
    parse_research_artifact_uri,
    stable_research_id,
)
from trader_research.governance import (
    DATASET_MANIFEST,
    DATA_QUALITY_REPORT,
    CapabilitySideEffect,
    ResearchIssue,
    SpecialistHandoff,
    agent_owner_for_tool,
)

from trader_agents.specialists import (
    SpecialistActionExecutionError,
    SpecialistActionOutcome,
    SpecialistActionStatus,
    SpecialistDecision,
    SpecialistPolicyContext,
)
from trader_agents.tool_client import McpToolClient

from .domain import DataSpecialistRequest, data_request_from_task
from .policy import (
    CAPTURE_MARKET_DATA_EVIDENCE_ACTION,
    DATA_SPECIALIST_ACTION_VERSION,
    ENSURE_MARKET_DATA_AVAILABLE_ACTION,
    VALIDATE_MARKET_DATA_SCOPE_ACTION,
)


@dataclass(frozen=True)
class _DataToolEnvelope:
    """Normalized MCP envelope used only within one handler invocation."""

    ok: bool
    command: str
    side_effect: str
    data: Mapping[str, Any]
    artifacts: Mapping[str, Any]
    warnings: tuple[ResearchIssue, ...]
    errors: tuple[ResearchIssue, ...]


class ValidateMarketDataScopeHandler:
    """Validate exact symbols and provider context through Data discovery MCP."""

    def __init__(self, tool_client: McpToolClient) -> None:
        """Store the injected MCP client without exposing it through graph state."""
        self._tool_client = tool_client

    async def run(
        self,
        *,
        context: SpecialistPolicyContext,
        decision: SpecialistDecision,
    ) -> SpecialistActionOutcome:
        """Return success only when every requested symbol is available."""
        del decision
        request = data_request_from_task(context.task)
        envelope = await _call_data_tool(
            tool_client=self._tool_client,
            tool_name=DATA_DISCOVER_SYMBOLS_TOOL,
            side_effect=CapabilitySideEffect.READ_ONLY,
            arguments=_discovery_arguments(request),
        )
        if not envelope.ok:
            return _failed_tool_outcome(
                action_id=VALIDATE_MARKET_DATA_SCOPE_ACTION,
                envelope=envelope,
            )
        report = _mapping(
            envelope.data.get("symbol_discovery_report"),
            "symbol discovery report",
        )
        _validate_discovery_scope(report, request)
        missing_symbols = tuple(
            str(item) for item in _sequence(report.get("missing_symbols"))
        )
        if report.get("all_requested_symbols_exist") is not True or missing_symbols:
            blocker = ResearchIssue(
                code="market_data_symbols_unavailable",
                message="One or more requested market-data symbols are unavailable.",
                details={"missing_symbols": list(missing_symbols)},
            )
            return SpecialistActionOutcome(
                action_id=VALIDATE_MARKET_DATA_SCOPE_ACTION,
                action_version=DATA_SPECIALIST_ACTION_VERSION,
                status=SpecialistActionStatus.BLOCKED,
                warnings=envelope.warnings,
                blockers=(blocker,),
            )
        return SpecialistActionOutcome(
            action_id=VALIDATE_MARKET_DATA_SCOPE_ACTION,
            action_version=DATA_SPECIALIST_ACTION_VERSION,
            status=SpecialistActionStatus.SUCCEEDED,
            warnings=envelope.warnings,
        )


class EnsureMarketDataAvailableHandler:
    """Run the approved, replay-safe checked-in sample loader through MCP."""

    def __init__(self, tool_client: McpToolClient) -> None:
        """Store the injected MCP client without exposing it through graph state."""
        self._tool_client = tool_client

    async def run(
        self,
        *,
        context: SpecialistPolicyContext,
        decision: SpecialistDecision,
    ) -> SpecialistActionOutcome:
        """Load sample data and retain only a bounded action summary."""
        del decision
        request = data_request_from_task(context.task)
        if request.loading_intent is None:
            raise SpecialistActionExecutionError(
                "missing_data_loading_intent",
                "Data loading action requires an explicit loading intent.",
            )
        envelope = await _call_data_tool(
            tool_client=self._tool_client,
            tool_name=DATA_ENSURE_LOADED_TOOL,
            side_effect=CapabilitySideEffect.LOCAL_MUTATING,
            arguments={
                **_scope_arguments(request),
                "mode": request.loading_intent.mode.value,
                "dry_run": False,
            },
        )
        if not envelope.ok:
            return _failed_tool_outcome(
                action_id=ENSURE_MARKET_DATA_AVAILABLE_ACTION,
                envelope=envelope,
            )
        load_result = _mapping(
            envelope.data.get("load_result"),
            "data load result",
        )
        if load_result.get("mode") != request.loading_intent.mode.value:
            raise SpecialistActionExecutionError(
                "invalid_data_load_result",
                "Data load result mode does not match the requested loading intent.",
            )
        return SpecialistActionOutcome(
            action_id=ENSURE_MARKET_DATA_AVAILABLE_ACTION,
            action_version=DATA_SPECIALIST_ACTION_VERSION,
            status=SpecialistActionStatus.SUCCEEDED,
            warnings=envelope.warnings,
        )


class CaptureMarketDataEvidenceHandler:
    """Persist and independently verify canonical manifest and quality evidence."""

    def __init__(
        self,
        *,
        tool_client: McpToolClient,
        artifact_store: ResearchArtifactStore,
    ) -> None:
        """Store the MCP and canonical artifact-store dependencies."""
        self._tool_client = tool_client
        self._artifact_store = artifact_store

    async def run(
        self,
        *,
        context: SpecialistPolicyContext,
        decision: SpecialistDecision,
    ) -> SpecialistActionOutcome:
        """Return two verified refs, blocking when final evidence is incomplete."""
        del decision
        request = data_request_from_task(context.task)
        envelope = await _call_data_tool(
            tool_client=self._tool_client,
            tool_name=DATA_CREATE_RESEARCH_SNAPSHOT_TOOL,
            side_effect=CapabilitySideEffect.LOCAL_MUTATING,
            arguments={
                **_scope_arguments(request),
                "requested_by": context.task.requested_by,
                "actor": agent_owner_for_tool(DATA_CREATE_RESEARCH_SNAPSHOT_TOOL),
            },
        )
        if not envelope.ok:
            return _failed_tool_outcome(
                action_id=CAPTURE_MARKET_DATA_EVIDENCE_ACTION,
                envelope=envelope,
            )
        refs = _snapshot_refs(envelope.artifacts)
        try:
            manifest_record = _load_verified_record(
                store=self._artifact_store,
                artifact_type=DATASET_MANIFEST,
                uri=refs[DATASET_MANIFEST],
                context=context,
                request=request,
            )
            quality_record = _load_verified_record(
                store=self._artifact_store,
                artifact_type=DATA_QUALITY_REPORT,
                uri=refs[DATA_QUALITY_REPORT],
                context=context,
                request=request,
            )
            _validate_matching_dataset(manifest_record, quality_record)
        except (ResearchArtifactStoreError, ValueError) as exc:
            raise SpecialistActionExecutionError(
                "invalid_canonical_data_evidence",
                str(exc),
            ) from exc

        manifest_handoff = _handoff(
            context=context,
            request=request,
            record=manifest_record,
        )
        quality_handoff = _handoff(
            context=context,
            request=request,
            record=quality_record,
        )
        outputs = {
            "manifest": (manifest_handoff,),
            "quality": (quality_handoff,),
        }
        blockers = _fitness_blockers(manifest_record, quality_record)
        if blockers:
            return SpecialistActionOutcome(
                action_id=CAPTURE_MARKET_DATA_EVIDENCE_ACTION,
                action_version=DATA_SPECIALIST_ACTION_VERSION,
                status=SpecialistActionStatus.BLOCKED,
                outputs=outputs,
                warnings=envelope.warnings,
                blockers=blockers,
            )
        return SpecialistActionOutcome(
            action_id=CAPTURE_MARKET_DATA_EVIDENCE_ACTION,
            action_version=DATA_SPECIALIST_ACTION_VERSION,
            status=SpecialistActionStatus.SUCCEEDED,
            outputs=outputs,
            warnings=envelope.warnings,
        )


async def _call_data_tool(
    *,
    tool_client: McpToolClient,
    tool_name: str,
    side_effect: CapabilitySideEffect,
    arguments: Mapping[str, Any],
) -> _DataToolEnvelope:
    try:
        raw_result = await tool_client.call_tool(tool_name, arguments)
    except Exception as exc:
        raise SpecialistActionExecutionError(
            "data_tool_transport_error",
            f"{tool_name} transport failed: {exc}",
        ) from exc
    envelope = _mapping(
        raw_result.get("structuredContent"),
        "MCP structuredContent",
    )
    if envelope.get("command") != tool_name:
        raise SpecialistActionExecutionError(
            "invalid_data_tool_envelope",
            f"{tool_name} returned the wrong command identity.",
        )
    if envelope.get("agent_owner") != agent_owner_for_tool(tool_name):
        raise SpecialistActionExecutionError(
            "invalid_data_tool_envelope",
            f"{tool_name} returned the wrong agent owner.",
        )
    if envelope.get("side_effect") != side_effect.value:
        raise SpecialistActionExecutionError(
            "invalid_data_tool_envelope",
            f"{tool_name} returned the wrong side-effect class.",
        )
    ok = envelope.get("ok")
    if not isinstance(ok, bool):
        raise SpecialistActionExecutionError(
            "invalid_data_tool_envelope",
            f"{tool_name} did not return a boolean success value.",
        )
    is_error = raw_result.get("isError")
    if is_error is not None and bool(is_error) is ok:
        raise SpecialistActionExecutionError(
            "invalid_data_tool_envelope",
            f"{tool_name} returned inconsistent MCP error metadata.",
        )
    return _DataToolEnvelope(
        ok=ok,
        command=tool_name,
        side_effect=side_effect.value,
        data=_mapping_or_empty(envelope.get("data")),
        artifacts=_mapping_or_empty(envelope.get("artifacts")),
        warnings=tuple(
            _issue(item, default_code="data_tool_warning")
            for item in _sequence(envelope.get("warnings"))
        ),
        errors=tuple(
            _issue(item, default_code="data_tool_error")
            for item in _sequence(envelope.get("errors"))
        ),
    )


def _failed_tool_outcome(
    *,
    action_id: str,
    envelope: _DataToolEnvelope,
) -> SpecialistActionOutcome:
    issues = envelope.errors or (
        ResearchIssue(
            code="data_tool_failed",
            message=f"{envelope.command} returned an unsuccessful envelope.",
        ),
    )
    blocking = any(_is_blocking_issue(item.code) for item in issues)
    return SpecialistActionOutcome(
        action_id=action_id,
        action_version=DATA_SPECIALIST_ACTION_VERSION,
        status=(
            SpecialistActionStatus.BLOCKED
            if blocking
            else SpecialistActionStatus.FAILED
        ),
        warnings=envelope.warnings,
        blockers=issues if blocking else (),
        errors=() if blocking else issues,
    )


def _is_blocking_issue(code: str) -> bool:
    return code.endswith(("_not_allowed", "_required", "_unavailable")) or code in {
        "data_missing",
        "provider_not_configured",
        "unsupported_provider_catalog",
    }


def _discovery_arguments(request: DataSpecialistRequest) -> dict[str, Any]:
    requirement = request.data_requirement
    return _without_none(
        {
            "symbols": list(requirement.symbols),
            "asset_class": requirement.asset_class,
            "instrument_type": request.instrument_type,
            "bar_type": request.bar_type,
            "source": request.discovery_source,
            "provider": request.provider,
            "timeframe": requirement.timeframe,
            "source_filter": requirement.source,
            "limit": max(50, len(requirement.symbols)),
            "include_local_coverage": False,
        }
    )


def _scope_arguments(request: DataSpecialistRequest) -> dict[str, Any]:
    requirement = request.data_requirement
    return _without_none(
        {
            "symbols": list(requirement.symbols),
            "asset_class": requirement.asset_class,
            "timeframe": requirement.timeframe,
            "start": requirement.start,
            "end": requirement.end,
            "source": requirement.source,
            "provider": request.provider,
            "instrument_type": request.instrument_type,
            "bar_type": request.bar_type,
        }
    )


def _validate_discovery_scope(
    report: Mapping[str, Any],
    request: DataSpecialistRequest,
) -> None:
    requirement = request.data_requirement
    if (
        tuple(str(item) for item in _sequence(report.get("requested_symbols")))
        != requirement.symbols
    ):
        raise SpecialistActionExecutionError(
            "invalid_symbol_discovery_scope",
            "Symbol discovery result does not match the requested symbols.",
        )
    if str(report.get("asset_class") or "") != requirement.asset_class:
        raise SpecialistActionExecutionError(
            "invalid_symbol_discovery_scope",
            "Symbol discovery result does not match the requested asset class.",
        )
    if str(report.get("source") or "") != request.discovery_source:
        raise SpecialistActionExecutionError(
            "invalid_symbol_discovery_scope",
            "Symbol discovery result does not match the requested discovery source.",
        )
    if (
        request.provider is not None
        and str(report.get("requested_provider") or "") != request.provider
    ):
        raise SpecialistActionExecutionError(
            "invalid_symbol_discovery_scope",
            "Symbol discovery result does not match the requested provider.",
        )
    if (
        request.instrument_type is not None
        and report.get("instrument_type") != request.instrument_type
    ):
        raise SpecialistActionExecutionError(
            "invalid_symbol_discovery_scope",
            "Symbol discovery result does not match the requested instrument type.",
        )
    if request.bar_type is not None and report.get("bar_type") != request.bar_type:
        raise SpecialistActionExecutionError(
            "invalid_symbol_discovery_scope",
            "Symbol discovery result does not match the requested bar type.",
        )
    if report.get("source_filter") != request.data_requirement.source:
        raise SpecialistActionExecutionError(
            "invalid_symbol_discovery_scope",
            "Symbol discovery result does not match the requested source filter.",
        )


def _snapshot_refs(artifacts: Mapping[str, Any]) -> dict[str, str]:
    expected = {
        "dataset_manifest": DATASET_MANIFEST,
        "data_quality_report": DATA_QUALITY_REPORT,
    }
    if set(artifacts) != set(expected):
        raise SpecialistActionExecutionError(
            "invalid_data_snapshot_refs",
            "Data snapshot must return exactly one manifest and quality reference.",
        )
    refs: dict[str, str] = {}
    for key, artifact_type in expected.items():
        raw_ref = _mapping(artifacts.get(key), f"{key} artifact reference")
        uri = str(raw_ref.get("uri") or "")
        declared_type = str(raw_ref.get("artifact_type") or "")
        try:
            parsed_type, _ = parse_research_artifact_uri(uri)
        except ResearchArtifactStoreError as exc:
            raise SpecialistActionExecutionError(
                "invalid_data_snapshot_refs",
                str(exc),
            ) from exc
        if declared_type != artifact_type or parsed_type != artifact_type:
            raise SpecialistActionExecutionError(
                "invalid_data_snapshot_refs",
                f"{key} reference has the wrong artifact type.",
            )
        refs[artifact_type] = uri
    return refs


def _load_verified_record(
    *,
    store: ResearchArtifactStore,
    artifact_type: str,
    uri: str,
    context: SpecialistPolicyContext,
    request: DataSpecialistRequest,
) -> ResearchArtifactRecord:
    parsed_type, artifact_id = parse_research_artifact_uri(uri)
    if parsed_type != artifact_type:
        raise ValueError(f"canonical Data ref has wrong type: {uri}")
    record = store.load_artifact_record(artifact_type, artifact_id)
    expected_actor = agent_owner_for_tool(DATA_CREATE_RESEARCH_SNAPSHOT_TOOL)
    if record.artifact_type != artifact_type or record.uri != uri:
        raise ValueError(f"canonical Data record identity mismatch: {uri}")
    if record.domain_owner != DATA_DOMAIN_OWNER:
        raise ValueError(f"canonical Data record has wrong owner: {uri}")
    if record.producer_tool != DATA_CREATE_RESEARCH_SNAPSHOT_TOOL:
        raise ValueError(f"canonical Data record has wrong producer: {uri}")
    if record.requested_by != context.task.requested_by:
        raise ValueError(f"canonical Data record has wrong requester: {uri}")
    if record.actor != expected_actor:
        raise ValueError(f"canonical Data record has wrong actor: {uri}")
    if record.status != "captured":
        raise ValueError(f"canonical Data record is not captured: {uri}")
    payload = record.payload
    if payload.get("artifact_type") != artifact_type:
        raise ValueError(f"canonical Data payload has wrong artifact type: {uri}")
    if payload.get("status") != "captured":
        raise ValueError(f"canonical Data payload is not captured: {uri}")
    if payload.get("snapshot_request_id") != context.task.requested_by:
        raise ValueError(f"canonical Data payload has wrong requester: {uri}")
    if payload.get("snapshot_actor") != expected_actor:
        raise ValueError(f"canonical Data payload has wrong actor: {uri}")
    _validate_artifact_scope(payload, request, uri=uri)
    return record


def _validate_artifact_scope(
    payload: Mapping[str, Any],
    request: DataSpecialistRequest,
    *,
    uri: str,
) -> None:
    requirement = request.data_requirement
    if (
        tuple(str(item) for item in _sequence(payload.get("symbols")))
        != requirement.symbols
    ):
        raise ValueError(f"canonical Data symbols do not match task: {uri}")
    for key, expected in (
        ("asset_class", requirement.asset_class),
        ("timeframe", requirement.timeframe),
        ("source_filter", requirement.source),
    ):
        if payload.get(key) != expected:
            raise ValueError(f"canonical Data {key} does not match task: {uri}")
    raw_window = payload.get("requested_window")
    if not isinstance(raw_window, Mapping):
        raise ValueError(f"canonical Data requested_window is invalid: {uri}")
    window = raw_window
    if not _timestamps_equal(window.get("start"), requirement.start):
        raise ValueError(f"canonical Data start does not match task: {uri}")
    if not _timestamps_equal(window.get("end"), requirement.end):
        raise ValueError(f"canonical Data end does not match task: {uri}")
    provider_context = _mapping_or_empty(payload.get("provider_context"))
    if (
        request.provider is not None
        and provider_context.get("requested_provider") != request.provider
    ):
        raise ValueError(f"canonical Data provider does not match task: {uri}")
    if (
        request.instrument_type is not None
        and payload.get("instrument_type") != request.instrument_type
    ):
        raise ValueError(f"canonical Data instrument type does not match task: {uri}")
    if request.bar_type is not None and payload.get("bar_type") != request.bar_type:
        raise ValueError(f"canonical Data bar type does not match task: {uri}")


def _validate_matching_dataset(
    manifest: ResearchArtifactRecord,
    quality: ResearchArtifactRecord,
) -> None:
    manifest_dataset_id = str(manifest.payload.get("dataset_id") or "")
    quality_dataset_id = str(quality.payload.get("dataset_id") or "")
    if not manifest_dataset_id or manifest_dataset_id != quality_dataset_id:
        raise ValueError(
            "canonical manifest and quality report do not identify the same dataset"
        )
    manifest_id = quality.metadata.get("dataset_manifest_artifact_id")
    if manifest_id != manifest.artifact_id:
        raise ValueError(
            "canonical quality report does not reference the matching manifest"
        )


def _handoff(
    *,
    context: SpecialistPolicyContext,
    request: DataSpecialistRequest,
    record: ResearchArtifactRecord,
) -> SpecialistHandoff:
    payload_digest = json_payload_hash(record.payload)
    return SpecialistHandoff(
        handoff_id=stable_research_id(
            "data_specialist_handoff",
            {
                "task_id": context.task.task_id,
                "artifact_uri": record.uri,
                "payload_sha256": payload_digest,
            },
        ),
        domain_owner=record.domain_owner,
        producer_tool=record.producer_tool,
        requested_by=context.task.requested_by,
        actor=agent_owner_for_tool(DATA_CREATE_RESEARCH_SNAPSHOT_TOOL),
        artifact_type=record.artifact_type,
        artifact_uri=record.uri,
        source_request=request.to_dict(),
        provenance_refs={
            "task_id": context.task.task_id,
            "payload_sha256": payload_digest,
            "dataset_id": record.payload.get("dataset_id"),
        },
    )


def _fitness_blockers(
    manifest: ResearchArtifactRecord,
    quality: ResearchArtifactRecord,
) -> tuple[ResearchIssue, ...]:
    blockers: list[ResearchIssue] = []
    if manifest.payload.get("complete") is not True:
        blockers.append(
            ResearchIssue(
                code="dataset_manifest_incomplete",
                message="The captured dataset manifest is incomplete.",
                details={"artifact_uri": manifest.uri},
            )
        )
    if quality.payload.get("complete") is not True:
        blockers.append(
            ResearchIssue(
                code="data_quality_incomplete",
                message="The captured data-quality report is incomplete.",
                details={"artifact_uri": quality.uri},
            )
        )
    return tuple(blockers)


def _timestamps_equal(left: object, right: object) -> bool:
    try:
        left_value = datetime.fromisoformat(str(left).replace("Z", "+00:00"))
        right_value = datetime.fromisoformat(str(right).replace("Z", "+00:00"))
    except ValueError:
        return False
    if left_value.tzinfo is None or right_value.tzinfo is None:
        return False
    return left_value.astimezone(timezone.utc) == right_value.astimezone(timezone.utc)


def _issue(value: object, *, default_code: str) -> ResearchIssue:
    if isinstance(value, Mapping):
        return ResearchIssue(
            code=str(value.get("code") or default_code),
            message=str(value.get("message") or value),
            details=_mapping_or_empty(value.get("details")),
        )
    return ResearchIssue(code=default_code, message=str(value))


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SpecialistActionExecutionError(
            "invalid_data_tool_payload",
            f"{label} must be a mapping.",
        )
    return value


def _mapping_or_empty(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value
    return ()


def _without_none(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}
