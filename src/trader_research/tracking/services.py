"""Explicit non-authoritative experiment-tracking projection services."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from trader_research.artifact_store import (
    ResearchArtifactNotFound,
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    json_payload_hash,
)
from trader_research.contracts import SCHEMA_VERSION, SideEffect, ToolEnvelope, error_envelope, success_envelope
from trader_research.domain import (
    EXPERIMENT_TRACKING_PROJECTION_REPORT,
    PARAMETER_OPTIMIZATION_RUN,
    stable_research_id,
)
from trader_research.optimization.contracts import ExperimentTrackingSink
from trader_research.optimization.services import load_validated_parameter_optimization_run


RESEARCH_PROJECT_EXPERIMENT_TRACKING = "research_project_experiment_tracking"


class ExperimentTrackingSinkRegistry:
    """Configured optional analytical tracking sinks."""

    def __init__(self, sinks: Sequence[ExperimentTrackingSink] | None = None) -> None:
        self._sinks = {
            str(sink.profile().get("profile_name") or ""): sink
            for sink in (sinks or ())
            if str(sink.profile().get("profile_name") or "")
        }

    def profiles(self) -> tuple[Mapping[str, Any], ...]:
        """Return non-secret sink metadata."""
        return tuple(dict(self._sinks[name].profile()) for name in sorted(self._sinks))

    def get(self, profile_name: str) -> ExperimentTrackingSink:
        """Resolve one configured sink or fail closed."""
        try:
            return self._sinks[str(profile_name)]
        except KeyError as exc:
            raise ValueError(f"unknown experiment tracking profile: {profile_name}") from exc


def project_experiment_tracking(
    *,
    canonical_run_ref: str,
    tracking_profile: str,
    artifact_store: ResearchArtifactStore | None,
    sink_registry: ExperimentTrackingSinkRegistry | None = None,
) -> ToolEnvelope:
    """Project one canonical optimization run without accepting caller metrics or tags."""
    if artifact_store is None:
        return _error("research_artifact_store_required", "A ResearchArtifactStore is required.")
    registry = sink_registry or ExperimentTrackingSinkRegistry()
    try:
        run, trials = load_validated_parameter_optimization_run(
            artifact_store, canonical_run_ref
        )
        run_id = str(run["optimization_run_id"])
        canonical_snapshot = {"parameter_optimization_run": dict(run), "trials": trials}
        sink = registry.get(tracking_profile)
        profile = dict(sink.profile())
        projection_id = stable_research_id(
            "experiment_tracking_projection",
            {
                "canonical_run_id": run_id,
                "canonical_digest": json_payload_hash(canonical_snapshot),
                "tracking_profile": profile,
            },
        )
        try:
            existing = artifact_store.load_artifact(EXPERIMENT_TRACKING_PROJECTION_REPORT, projection_id)
        except ResearchArtifactNotFound:
            existing = None
        if existing is not None:
            return _projection_envelope(existing)
        try:
            provider_refs = dict(sink.project(canonical_snapshot))
            status = "passed"
            blockers: list[str] = []
        except Exception as exc:
            provider_refs = {}
            status = "blocked"
            blockers = [str(exc)]
        report = {
            "artifact_type": EXPERIMENT_TRACKING_PROJECTION_REPORT,
            "schema_version": SCHEMA_VERSION,
            "projection_id": projection_id,
            "canonical_artifact_type": PARAMETER_OPTIMIZATION_RUN,
            "canonical_run_id": run_id,
            "canonical_digest": json_payload_hash(canonical_snapshot),
            "tracking_profile": profile,
            "status": status,
            "authoritative": False,
            "provider_refs": provider_refs,
            "warnings": [],
            "blockers": blockers,
        }
        record = artifact_store.save_artifact(
            artifact_type=EXPERIMENT_TRACKING_PROJECTION_REPORT,
            artifact_id=projection_id,
            payload=report,
            status=status,
            metadata={"canonical_run_id": run_id, "tracking_profile": tracking_profile},
        )
    except (ValueError, KeyError, ResearchArtifactStoreError) as exc:
        return _error("experiment_tracking_projection_failed", str(exc))
    return _projection_envelope(report, record_reference=record.reference().to_dict())


def _projection_envelope(
    report: Mapping[str, Any],
    *,
    record_reference: Mapping[str, Any] | None = None,
) -> ToolEnvelope:
    envelope = success_envelope(
        command=RESEARCH_PROJECT_EXPERIMENT_TRACKING,
        side_effect=SideEffect.EXTERNAL_RESEARCH_MUTATING,
        data={"experiment_tracking_projection_report": dict(report)},
        artifacts={
            "experiment_tracking_projection_report": dict(record_reference)
            if record_reference is not None
            else {
                "artifact_type": EXPERIMENT_TRACKING_PROJECTION_REPORT,
                "uri": (
                    f"research://postgres/{EXPERIMENT_TRACKING_PROJECTION_REPORT}/"
                    f"{report['projection_id']}"
                ),
                "metadata": {"status": report.get("status")},
            }
        },
    )
    if report.get("status") == "passed":
        return envelope
    blockers = list(report.get("blockers") or ["experiment tracking projection is blocked"])
    return ToolEnvelope(
        ok=False,
        command=RESEARCH_PROJECT_EXPERIMENT_TRACKING,
        agent_owner=envelope.agent_owner,
        side_effect=envelope.side_effect,
        data=envelope.data,
        artifacts=envelope.artifacts,
        errors=({"code": "experiment_tracking_projection_blocked", "message": str(blockers[0])},),
    )


def _error(code: str, message: str) -> ToolEnvelope:
    return error_envelope(
        command=RESEARCH_PROJECT_EXPERIMENT_TRACKING,
        side_effect=SideEffect.EXTERNAL_RESEARCH_MUTATING,
        code=code,
        message=message,
    )
