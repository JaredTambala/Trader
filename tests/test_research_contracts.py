from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from trader_research.foundation import ApplicationResult, error_result, success_result
from trader_research.foundation.artifacts import ArtifactReference


def test_application_result_excludes_transport_metadata() -> None:
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
    result = success_result(
        command="data_get_inventory",
        data={"symbols": ["DEMO"]},
    )

    assert result.operation == "data_get_inventory"
    assert result.to_dict()["data"] == {"symbols": ["DEMO"]}


def test_error_result_preserves_structured_errors() -> None:
    result = error_result(
        command="data_get_inventory",
        code="missing_data",
        message="No bars found for DEMO.",
        data={"symbol": "DEMO"},
    )

    payload = result.to_dict()

    assert payload["ok"] is False
    assert payload["errors"] == [{"code": "missing_data", "message": "No bars found for DEMO."}]
    assert payload["data"] == {"symbol": "DEMO"}


def test_artifact_reference_serializes_json_safe_values(tmp_path: Path) -> None:
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
