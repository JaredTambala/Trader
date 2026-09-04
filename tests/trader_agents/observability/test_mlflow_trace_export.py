"""Local-adapter test for redacted Agent trace export to MLflow.

Subject: Agent-owned MLflow trace sink configuration and public correlation projection.
Level: Local adapter integration.
Collaborators: Real MLflow tracing against a temporary local SQLite store; no Agent graph or remote service.
Guarantees: Exported spans retain approved identities while excluding credentials and raw model or tool content.
Non-goals: Runtime trajectory assessment, provider execution, durable product records, and remote MLflow availability."""

from __future__ import annotations
from collections.abc import Sequence
import json
from pathlib import Path
from typing import Any
from uuid import uuid4
import pytest
from trader_agents import MlflowTraceSink, first_slice_tool_catalogue


def test_mlflow_trace_sink_persists_only_public_correlation(
    tmp_path: Path,
) -> None:
    """A real local MLflow store receives queryable redacted span metadata."""
    import mlflow
    from mlflow import MlflowClient

    previous_uri = mlflow.get_tracking_uri()
    tracking_uri = f"sqlite:///{tmp_path / 'agent-traces.db'}"
    experiment_name = f"agent-trace-{uuid4().hex}"
    sink = MlflowTraceSink(
        tracking_uri=tracking_uri,
        experiment_name=experiment_name,
    )
    public_attributes = {
        "trader.session_id": "session-trace",
        "trader.branch_id": "branch-trace",
        "trader.program_id": "data-research-v6",
        "trader.tool_name": "data_get_inventory",
        "trader.result_ok": True,
    }
    root_attributes = {
        "trader.session_id": "session-trace",
        "trader.branch_id": "branch-trace",
        "trader.program_id": "research-coordinator-v7",
        "trader.model_profile_id": "ollama-lfm25-8b-json-v1",
        "trader.tool_catalog_id": first_slice_tool_catalogue().catalogue_id,
        "trader.lifecycle_operation": "start",
    }
    stored_traces: Sequence[Any] = ()
    try:
        with sink.span(
            "agent.session.start",
            span_type="CHAIN",
            attributes=root_attributes,
        ):
            with sink.span(
                "agent.mcp_result.data_get_inventory",
                span_type="CHAIN",
                attributes=public_attributes,
            ):
                pass
        with pytest.raises(ValueError, match="not allowed"):
            with sink.span(
                "agent.invalid",
                span_type="CHAIN",
                attributes={"trader.source_code": "do not persist"},
            ):
                pass
        client = MlflowClient(tracking_uri=tracking_uri)
        experiment = client.get_experiment_by_name(experiment_name)
        assert experiment is not None
        stored_traces = client.search_traces(
            locations=[experiment.experiment_id],
            include_spans=True,
            flush=True,
        )
    finally:
        mlflow.set_tracking_uri(previous_uri)

    assert len(stored_traces) == 1
    spans = stored_traces[0].data.spans
    assert len(spans) == 2
    by_name = {span.name: span for span in spans}
    assert set(by_name) == {
        "agent.session.start",
        "agent.mcp_result.data_get_inventory",
    }
    span = by_name["agent.mcp_result.data_get_inventory"]
    assert span.name == "agent.mcp_result.data_get_inventory"
    assert {
        key: value
        for key, value in span.attributes.items()
        if key.startswith("trader.")
    } == public_attributes
    assert "source_code" not in json.dumps(span.attributes)
