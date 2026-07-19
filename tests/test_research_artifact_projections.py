from __future__ import annotations

from typing import Any

import pytest

from trader_research.foundation.artifacts import build_artifact_record
from trader_research.infrastructure.postgres.projections import (
    combine_projection_writers,
    default_projection_registry,
)


def _record(artifact_type: str = "demo_artifact"):
    return build_artifact_record(
        artifact_type=artifact_type,
        artifact_id="demo_1",
        agent_owner="Test Owner",
        payload={"status": "passed"},
    )


def test_projection_registry_dispatches_only_registered_artifact_type() -> None:
    calls: list[tuple[Any, str, Any]] = []

    def writer(connection: Any, record: Any, json_value: Any) -> None:
        calls.append((connection, record.artifact_id, json_value))

    registry = combine_projection_writers({"demo_artifact": writer})
    connection = object()

    def json_value(value: Any) -> Any:
        return value

    registry.write(connection, _record(), json_value=json_value)
    registry.write(
        connection,
        _record("canonical_only_artifact"),
        json_value=json_value,
    )

    assert calls == [(connection, "demo_1", json_value)]


def test_projection_registry_rejects_duplicate_context_ownership() -> None:
    def writer(connection: Any, record: Any, json_value: Any) -> None:
        del connection, record, json_value

    with pytest.raises(ValueError, match="duplicate projection writers: demo_artifact"):
        combine_projection_writers(
            {"demo_artifact": writer},
            {"demo_artifact": writer},
        )


def test_default_projection_registry_is_partitioned_by_context() -> None:
    projected = set(default_projection_registry().writers)

    assert "methodology_candidate" in projected
    assert "implementation_version" in projected
    assert "backtest_run" in projected
    assert "parameter_optimization_evaluation_report" in projected
    assert "parameter_optimization_robustness_report" in projected
