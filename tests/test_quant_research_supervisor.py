from __future__ import annotations

from typing import Any

import anyio

from trader_agents.quant_research import build_quant_research_supervisor_graph
from trader_agents.state import build_quant_research_supervisor_initial_state
from trader_research.domain import DATA_QUALITY_REPORT, DATASET_MANIFEST


def _state(**overrides: object) -> dict[str, Any]:
    payload = {
        "objective": "Evaluate AMD trend following.",
        "symbols": ("AMD",),
        "asset_class": "stocks",
        "timeframe": "1Day",
        "start": "2025-05-28T00:00:00Z",
        "end": "2026-05-28T00:00:00Z",
    }
    payload.update(overrides)
    return build_quant_research_supervisor_initial_state(**payload)


def test_supervisor_initial_state_contains_identity_and_request() -> None:
    state = _state()

    assert state["identity"]["agent_key"] == "quant_research_supervisor"
    assert state["identity"]["display_name"] == "Quant Research Supervisor Agent"
    assert state["status"] == "ready"
    assert state["research_request"]["data_requirement"]["symbols"] == ["AMD"]


def test_supervisor_graph_blocks_on_missing_required_specialist_artifacts() -> None:
    graph = build_quant_research_supervisor_graph()

    async def _run() -> None:
        output = await graph.ainvoke(_state())

        blocker_codes = {blocker["code"] for blocker in output["blockers"]}
        assert output["status"] == "blocked"
        assert output["public_status"] == "blocked_missing_evidence"
        assert output["called_tools"] == []
        assert "missing_dataset_manifest" in blocker_codes
        assert "missing_data_quality_report" in blocker_codes
        assert "missing_indicator_metadata" in blocker_codes
        assert "missing_hypothesis_card" in blocker_codes
        assert "missing_evaluation_report" in blocker_codes
        assert "missing_robustness_report" in blocker_codes
        assert "missing_feature_dataset_manifest" in blocker_codes
        assert output["artifact_slots"][DATASET_MANIFEST]["status"] == "blocked"

    anyio.run(_run)


def test_supervisor_can_make_ml_artifacts_optional() -> None:
    graph = build_quant_research_supervisor_graph()

    async def _run() -> None:
        output = await graph.ainvoke(_state(require_ml=False))

        blocker_codes = {blocker["code"] for blocker in output["blockers"]}
        assert "missing_feature_dataset_manifest" not in blocker_codes
        assert output["artifact_slots"]["feature_dataset_manifest"]["status"] == "optional_missing"
        assert output["artifact_slots"]["model_card"]["required"] is False

    anyio.run(_run)


def test_supervisor_rejects_forged_data_agent_owner() -> None:
    graph = build_quant_research_supervisor_graph()
    state = _state(
        incoming_handoffs=[
            {
                "handoff_id": "handoff_forged",
                "agent_owner": "Quant Research Supervisor Agent",
                "artifact_type": DATASET_MANIFEST,
                "payload": {"dataset_id": "dataset_demo", "complete": True},
                "source_request": {
                    "symbols": ["AMD"],
                    "asset_class": "stocks",
                    "timeframe": "1Day",
                    "start": "2025-05-28T00:00:00Z",
                    "end": "2026-05-28T00:00:00Z",
                },
            }
        ]
    )

    async def _run() -> None:
        output = await graph.ainvoke(state)

        assert output["status"] == "failed"
        assert output["errors"][0]["code"] == "invalid_handoff"
        assert "must be owned by Data Agent" in output["errors"][0]["message"]
        assert output["called_tools"] == []

    anyio.run(_run)


def test_supervisor_rejects_mismatched_data_handoff_window() -> None:
    graph = build_quant_research_supervisor_graph()
    state = _state(
        incoming_handoffs=[
            {
                "handoff_id": "handoff_manifest",
                "agent_owner": "Data Agent",
                "artifact_type": DATASET_MANIFEST,
                "payload": {"dataset_id": "dataset_demo", "complete": True},
                "source_request": {
                    "symbols": ["MSFT"],
                    "asset_class": "stocks",
                    "timeframe": "1Day",
                    "start": "2025-05-28T00:00:00Z",
                    "end": "2026-05-28T00:00:00Z",
                },
            }
        ]
    )

    async def _run() -> None:
        output = await graph.ainvoke(state)

        assert output["status"] == "failed"
        assert output["errors"][0]["code"] == "invalid_handoff"
        assert "symbols do not match" in output["errors"][0]["message"]

    anyio.run(_run)


def test_supervisor_accepts_data_handoffs_and_preserves_missing_specialist_blockers() -> None:
    graph = build_quant_research_supervisor_graph()
    request = {
        "symbols": ["AMD"],
        "asset_class": "stocks",
        "timeframe": "1Day",
        "start": "2025-05-28T00:00:00Z",
        "end": "2026-05-28T00:00:00Z",
    }
    state = _state(
        incoming_handoffs=[
            {
                "handoff_id": "handoff_manifest",
                "agent_owner": "Data Agent",
                "artifact_type": DATASET_MANIFEST,
                "payload": {
                    "dataset_id": "dataset_amd",
                    "symbols": ["AMD"],
                    "asset_class": "stocks",
                    "timeframe": "1Day",
                    "requested_window": {"start": request["start"], "end": request["end"]},
                    "complete": True,
                },
                "source_request": request,
                "provenance_refs": {"envelope_id": "inventory_env"},
                "side_effect": "read_only",
            },
            {
                "handoff_id": "handoff_quality",
                "agent_owner": "Data Agent",
                "artifact_type": DATA_QUALITY_REPORT,
                "payload": {
                    "report_id": "dq_amd",
                    "symbols": ["AMD"],
                    "asset_class": "stocks",
                    "timeframe": "1Day",
                    "requested_window": {"start": request["start"], "end": request["end"]},
                    "complete": False,
                    "missing_gap_count": 1,
                },
                "source_request": request,
                "warnings": [{"code": "data_agent_warning", "message": "Detected missing gaps.", "details": {}}],
                "provenance_refs": {"envelope_id": "quality_env"},
                "side_effect": "read_only",
            },
        ]
    )

    async def _run() -> None:
        output = await graph.ainvoke(state)

        blocker_codes = {blocker["code"] for blocker in output["blockers"]}
        assert output["status"] == "blocked"
        assert output["data_manifest"]["dataset_id"] == "dataset_amd"
        assert output["data_quality_report"]["report_id"] == "dq_amd"
        assert output["artifact_slots"][DATASET_MANIFEST]["handoff"]["agent_owner"] == "Data Agent"
        assert output["artifact_slots"][DATA_QUALITY_REPORT]["status"] == "accepted"
        assert "data_quality_incomplete" in blocker_codes
        assert "missing_hypothesis_card" in blocker_codes
        assert output["warnings"][0]["code"] == "data_agent_warning"
        assert output["called_tools"] == []

    anyio.run(_run)
