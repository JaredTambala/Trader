"""Workflow test for evidence-backed method-card construction through MCP.

Subject: Open-world methodology discovery, extraction, validation, drafting, and publication adapters.
Level: Adapter integration and local workflow.
Collaborators: Real MCP and research services with deterministic embeddings and JSON persistence.
Guarantees: Multiple source methods produce bounded cards while weak or contaminated evidence fails closed.
Non-goals: Model reasoning quality, Postgres or pgvector, remote embeddings, or strategy execution.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

import anyio

from trader_mcp.catalogue.definitions import (
    KNOWLEDGE_ASSEMBLE_METHODOLOGY_EVIDENCE_TOOL,
    KNOWLEDGE_CREATE_METHOD_CARD_DRAFT_TOOL,
    KNOWLEDGE_DISCOVER_METHODOLOGY_CANDIDATES_TOOL,
    KNOWLEDGE_EXTRACT_METHODOLOGY_FIELDS_TOOL,
    KNOWLEDGE_GET_METHOD_CARD_SET_TOOL,
    KNOWLEDGE_INGEST_DOCUMENTS_TOOL,
    KNOWLEDGE_LIST_METHOD_CARD_SETS_TOOL,
    KNOWLEDGE_PUBLISH_METHOD_CARD_TOOL,
    KNOWLEDGE_REGISTER_SOURCE_TOOL,
    KNOWLEDGE_VALIDATE_METHODOLOGY_CANDIDATE_TOOL,
)
from trader_mcp.catalogue.policy import load_local_environment
from trader_mcp.runtime.server import create_server
from trader_research.foundation.artifacts import InMemoryResearchArtifactStore
from trader_research.knowledge.embeddings import DeterministicEmbeddingProvider
from trader_research.knowledge.store import JsonKnowledgeStore


TECHNICAL_METHOD = "Aurora Pulse Oscillator"
ADJACENT_METHOD = "Boreal Envelope Trigger"
INCOMPLETE_METHOD = "Drift Prism Index"
STAT_ARB_METHOD = "Lattice Residual Coupling"


def test_mcp_open_world_methods_materialize_canonical_cards_and_fail_closed(
    tmp_path: Path,
) -> None:
    """Materialize distinct canonical cards and reject insufficient or cross-method evidence."""
    artifact_root = tmp_path / "artifacts"
    source_dir = artifact_root / "knowledge_sources"
    source_dir.mkdir(parents=True)
    source_path = source_dir / "open_world_methods.txt"
    source_path.write_text(_open_world_source(), encoding="utf-8")

    knowledge_store = JsonKnowledgeStore(artifact_root)
    artifact_store = InMemoryResearchArtifactStore()
    environment = replace(
        load_local_environment("env.template"), artifact_root=artifact_root
    )
    server = create_server(
        environment,
        knowledge_embedding_provider=DeterministicEmbeddingProvider(),
        knowledge_store_provider=lambda: knowledge_store,
        research_artifact_store_provider=lambda: artifact_store,
    )

    async def _run() -> None:
        registered = await server.call_tool(
            KNOWLEDGE_REGISTER_SOURCE_TOOL,
            {
                "path": str(source_path),
                "title": "Open World Quantitative Methods",
                "source_type": "method_textbook",
                "canonical_citation": "Open World Quantitative Methods, deterministic acceptance fixture",
                "topics": ["technical indicators", "statistical arbitrage"],
                "method_families": ["technical_indicators", "statistical_arbitrage"],
            },
        )
        assert registered.isError is False
        source_id = registered.structuredContent["data"]["knowledge_source_manifest"][
            "source_id"
        ]

        ingested = await server.call_tool(
            KNOWLEDGE_INGEST_DOCUMENTS_TOOL, {"source_ids": [source_id]}
        )
        assert ingested.isError is False

        technical_candidates = await _discover_by_family(
            server, source_id, "technical_indicators"
        )
        statistical_candidates = await _discover_by_family(
            server, source_id, "statistical_arbitrage"
        )
        assert {TECHNICAL_METHOD, ADJACENT_METHOD, INCOMPLETE_METHOD} <= set(
            technical_candidates
        )
        assert STAT_ARB_METHOD in statistical_candidates

        technical = await _materialize_card(
            server,
            candidate_uri=technical_candidates[TECHNICAL_METHOD],
            readiness_goal="implementation",
            approved_method_card_id="method_card_aurora_pulse_oscillator_v1",
        )
        stat_arb = await _materialize_card(
            server,
            candidate_uri=statistical_candidates[STAT_ARB_METHOD],
            readiness_goal="strategy_template",
            approved_method_card_id="method_card_lattice_residual_coupling_v1",
        )

        _assert_specific_technical_fields(technical["candidate"])
        _assert_specific_stat_arb_fields(stat_arb["candidate"])
        _assert_adjacent_method_rejected(technical["packet"])
        await _assert_set_lineage(server, technical["published_card"])
        await _assert_set_lineage(server, stat_arb["published_card"])

        await _assert_missing_formula_role(
            server, technical_candidates[INCOMPLETE_METHOD]
        )
        await _assert_cross_method_contamination_rejected(
            server, technical["candidate"], technical["packet"]
        )

    anyio.run(_run)


async def _discover_by_family(
    server: Any, source_id: str, family: str
) -> dict[str, str]:
    discovered = await server.call_tool(
        KNOWLEDGE_DISCOVER_METHODOLOGY_CANDIDATES_TOOL,
        {
            "source_ids": [source_id],
            "method_families": [family],
            "neighbor_radius": 1,
            "max_candidates": 10,
        },
    )
    assert discovered.isError is False
    candidates = discovered.structuredContent["data"]["methodology_candidates"]
    refs = discovered.structuredContent["artifacts"]["methodology_candidates"]
    return {
        candidate["method_identity"]["canonical_name"]: ref["uri"]
        for candidate, ref in zip(candidates, refs, strict=True)
    }


async def _materialize_card(
    server: Any,
    *,
    candidate_uri: str,
    readiness_goal: str,
    approved_method_card_id: str,
) -> dict[str, Any]:
    assembled = await server.call_tool(
        KNOWLEDGE_ASSEMBLE_METHODOLOGY_EVIDENCE_TOOL,
        {"methodology_candidate_uri": candidate_uri, "readiness_goal": readiness_goal},
    )
    assert assembled.isError is False
    packet = assembled.structuredContent["data"]["methodology_evidence_packet"]
    packet_ref = assembled.structuredContent["artifacts"]["methodology_evidence_packet"]

    extracted = await server.call_tool(
        KNOWLEDGE_EXTRACT_METHODOLOGY_FIELDS_TOOL,
        {"evidence_packet_uri": packet_ref["uri"]},
    )
    assert extracted.isError is False
    candidate = extracted.structuredContent["data"]["methodology_candidate"]
    extraction_ref = extracted.structuredContent["artifacts"][
        "methodology_field_extraction_report"
    ]

    validated = await server.call_tool(
        KNOWLEDGE_VALIDATE_METHODOLOGY_CANDIDATE_TOOL,
        {"extraction_report_uri": extraction_ref["uri"]},
    )
    assert validated.isError is False
    report = validated.structuredContent["data"][
        "methodology_candidate_validation_report"
    ]
    assert report["status"] == "passed"
    assert report["readiness_summary"][readiness_goal]["status"] == "passed"
    validation_ref = validated.structuredContent["artifacts"][
        "methodology_candidate_validation_report"
    ]

    drafted = await server.call_tool(
        KNOWLEDGE_CREATE_METHOD_CARD_DRAFT_TOOL,
        {"methodology_candidate_validation_uri": validation_ref["uri"]},
    )
    assert drafted.isError is False
    draft = drafted.structuredContent["data"]["method_card_draft"]
    assert "card_format" not in draft
    assert (
        draft["source_methodology_candidate_id"]
        == candidate["methodology_candidate_id"]
    )
    assert draft["method_card_set_id"]

    published = await server.call_tool(
        KNOWLEDGE_PUBLISH_METHOD_CARD_TOOL,
        {
            "draft_method_card_id": draft["method_card_id"],
            "approved_method_card_id": approved_method_card_id,
            "approved_by": "open-world-regression",
            "approval_note": "packet-backed open-world methodology evidence reviewed",
            "approve": True,
        },
    )
    assert published.isError is False
    published_card = published.structuredContent["data"]["method_card"]
    assert published_card["status"] == "approved"
    assert published_card["method_card_set_id"] == draft["method_card_set_id"]
    return {
        "packet": packet,
        "candidate": candidate,
        "draft": draft,
        "published_card": published_card,
    }


def _assert_specific_technical_fields(candidate: dict[str, Any]) -> None:
    formula = candidate["extension_fields"]["technical_indicators"]["indicator_formula"]
    inputs = candidate["extension_fields"]["technical_indicators"]["input_series"]
    assert TECHNICAL_METHOD in formula["value"]
    assert formula["evidence_refs"][0]["chunk_id"]
    assert inputs["value"] == ["ordered price series"]
    assert candidate["core_fields"]["signal_decision_logic"]["signal_definition"][
        "value"
    ]
    assert candidate["core_fields"]["risk_validation"]["failure_modes"]["value"]


def _assert_specific_stat_arb_fields(candidate: dict[str, Any]) -> None:
    fields = candidate["extension_fields"]["statistical_arbitrage"]
    assert STAT_ARB_METHOD in fields["spread_definition"]["value"]
    assert STAT_ARB_METHOD in fields["hedge_ratio_method"]["value"]
    assert fields["cointegration_test"]["evidence_refs"][0]["chunk_id"]
    assert candidate["core_fields"]["signal_decision_logic"]["entry_rules"]["value"]
    assert candidate["core_fields"]["signal_decision_logic"]["exit_rules"]["value"]


def _assert_adjacent_method_rejected(packet: dict[str, Any]) -> None:
    rejected = [
        ref
        for role in packet["role_evidence"]
        for ref in role["rejected_chunks"]
        if ADJACENT_METHOD in ref.get("competing_method_labels", [])
    ]
    assert rejected
    assert all(ref["accepted_target_binding"] is False for ref in rejected)


async def _assert_set_lineage(server: Any, published_card: dict[str, Any]) -> None:
    method_card_set_id = published_card["method_card_set_id"]
    listed = await server.call_tool(
        KNOWLEDGE_LIST_METHOD_CARD_SETS_TOOL,
        {"method_id": published_card["method_id"], "include_retired": True},
    )
    assert listed.isError is False
    assert [
        item["method_card_set_id"]
        for item in listed.structuredContent["data"]["method_card_sets"]
    ] == [method_card_set_id]

    detail = await server.call_tool(
        KNOWLEDGE_GET_METHOD_CARD_SET_TOOL,
        {"method_card_set_id": method_card_set_id},
    )
    assert detail.isError is False
    data = detail.structuredContent["data"]
    assert (
        data["method_card_set"]["current_approved_method_card_id"]
        == published_card["method_card_id"]
    )
    assert data["revision_count"] == 2
    assert {item["status"] for item in data["revision_history"]} == {
        "draft",
        "approved",
    }


async def _assert_missing_formula_role(server: Any, candidate_uri: str) -> None:
    assembled = await server.call_tool(
        KNOWLEDGE_ASSEMBLE_METHODOLOGY_EVIDENCE_TOOL,
        {
            "methodology_candidate_uri": candidate_uri,
            "readiness_goal": "implementation",
        },
    )
    assert assembled.isError is True
    packet = assembled.structuredContent["data"]["methodology_evidence_packet"]
    assert packet["status"] == "blocked"
    assert "formula_algorithm" in packet["missing_roles"]
    assert (
        "missing required evidence role for implementation: formula_algorithm"
        in packet["blockers"]
    )


async def _assert_cross_method_contamination_rejected(
    server: Any,
    technical_candidate: dict[str, Any],
    packet: dict[str, Any],
) -> None:
    rejected_ref = next(
        ref
        for role in packet["role_evidence"]
        for ref in role["rejected_chunks"]
        if ADJACENT_METHOD in ref.get("competing_method_labels", [])
    )
    contaminated = deepcopy(technical_candidate)
    contaminated["core_fields"]["signal_decision_logic"]["signal_definition"] = {
        "value": f"Use the adjacent {ADJACENT_METHOD} signal.",
        "evidence_refs": [
            {
                "source_id": rejected_ref["source_id"],
                "chunk_id": rejected_ref["chunk_id"],
                "locator": rejected_ref["locator"],
                "claim": "adjacent method signal incorrectly attributed to target",
            }
        ],
        "confidence": 0.9,
        "quality": "role_evidence:signal_logic",
    }
    validated = await server.call_tool(
        KNOWLEDGE_VALIDATE_METHODOLOGY_CANDIDATE_TOOL,
        {"methodology_candidate": contaminated},
    )
    assert validated.isError is True
    report = validated.structuredContent["data"][
        "methodology_candidate_validation_report"
    ]
    assert report["status"] == "blocked"
    assert any(
        "claim span" in blocker or "claim_span" in blocker
        for blocker in report["blockers"]
    )


def _open_world_source() -> str:
    return "\n".join(
        (
            "Aurora Pulse Oscillator (APO): The APO method is a technical indicator defined to measure short-horizon price impulse.",
            "Aurora Pulse Oscillator (APO): APO uses an ordered closing price series as its input data.",
            "Aurora Pulse Oscillator (APO): The formula computes the average of signed price changes over a 12-period lookback window.",
            "Aurora Pulse Oscillator (APO): A positive threshold crossing is a long entry signal and a negative crossing is an exit signal.",
            "Aurora Pulse Oscillator (APO): Its assumption can fail through noise and whipsaw in a range-bound regime.",
            "Boreal Envelope Trigger (BET): The BET signal buys when price crosses the upper band and sells when price crosses the lower band.",
            "Boreal Envelope Trigger (BET): BET computes upper and lower bands from a moving average of closing prices.",
            "Drift Prism Index (DPI): The DPI method is a technical indicator defined from an ordered closing price series.",
            "Drift Prism Index (DPI): DPI has a whipsaw limitation in noisy markets.",
            "Lattice Residual Coupling (LRC): The LRC method is a statistical arbitrage pairs method for related assets.",
            "Lattice Residual Coupling (LRC): LRC forms a spread as the residual difference between two aligned asset price series.",
            "Lattice Residual Coupling (LRC): LRC estimates the hedge ratio coefficient with rolling regression.",
            "Lattice Residual Coupling (LRC): LRC tests the residual spread for cointegration and stationarity before trading.",
            "Lattice Residual Coupling (LRC): LRC enters long and short pair legs when the spread z-score crosses an entry threshold.",
            "Lattice Residual Coupling (LRC): LRC exits and closes both legs when the spread mean reverts toward zero.",
            "Lattice Residual Coupling (LRC): Its assumption can fail after a structural break in the relationship.",
        )
    )
