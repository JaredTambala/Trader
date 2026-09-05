"""Contract tests for dependency-light research results and artifact references.

Subject: Foundation result envelopes and serialized artifact-reference values.
Level: In-process contract.
Collaborators: Real foundation value objects, a temporary filesystem path, and no external services.
Guarantees: Results remain transport-neutral, structured, and JSON-safe across success and failure paths.
Non-goals: Artifact persistence, MCP envelopes, business-context validation, or workflow decisions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from trader_research.foundation import ApplicationResult, error_result, success_result
from trader_research.foundation.artifacts import ArtifactReference


def test_application_result_excludes_transport_metadata() -> None:
    """A foundation result serializes without leaking MCP-specific transport metadata into domain data."""
    result = ApplicationResult(
        ok=True,
        operation="data_get_inventory",
        data={"dataset_id": "dataset_demo"},
    )

    payload = result.to_dict()

    assert payload == {
        "artifacts": {},
        "operation": "data_get_inventory",
        "data": {"dataset_id": "dataset_demo"},
        "errors": [],
        "ok": True,
        "schema_version": "1",
        "warnings": [],
    }


def test_success_result_preserves_operation_and_data() -> None:
    """The success helper retains the requested operation and normalized result data."""
    result = success_result(
        command="data_get_inventory",
        data={"symbols": ["DEMO"]},
    )

    assert result.operation == "data_get_inventory"
    assert result.to_dict()["data"] == {"symbols": ["DEMO"]}


def test_error_result_preserves_structured_errors() -> None:
    """The error helper exposes machine-readable failure details beside bounded contextual data."""
    result = error_result(
        command="data_get_inventory",
        code="missing_data",
        message="No bars found for DEMO.",
        data={"symbol": "DEMO"},
    )

    payload = result.to_dict()

    assert payload["ok"] is False
    assert payload["errors"] == [
        {"code": "missing_data", "message": "No bars found for DEMO."}
    ]
    assert payload["data"] == {"symbol": "DEMO"}


def test_artifact_reference_serializes_json_safe_values(tmp_path: Path) -> None:
    """Artifact references convert paths and timestamps into stable JSON-safe representations."""
    report_path = tmp_path / "dataset_manifest.json"
    reference = ArtifactReference(
        artifact_type="dataset_manifest",
        path=report_path,
        uri="file://dataset_manifest.json",
        metadata={"created_at": datetime(2026, 1, 1, tzinfo=timezone.utc)},
    )
    result = success_result(
        command="data_get_inventory",
        artifacts={"dataset_manifest": reference},
    )

    payload = result.to_dict()

    assert payload["artifacts"]["dataset_manifest"] == {
        "artifact_type": "dataset_manifest",
        "path": str(report_path),
        "uri": "file://dataset_manifest.json",
        "metadata": {"created_at": "2026-01-01T00:00:00+00:00"},
    }
