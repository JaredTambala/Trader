"""Contracts for methodology field extraction and candidate validation.

Subject: Evidence-backed field extraction, lineage validation, and fail-closed readiness reports.
Level: Offline application workflow contract.
Collaborators: Knowledge stores, evidence packets, candidate artifacts, and deterministic embeddings.
Guarantees: Reports preserve lineage and reject stale, missing, misattributed, or invalid evidence.
Non-goals: Candidate discovery quality, method-card publication, computational fixtures, or Postgres.
"""

from __future__ import annotations

from pathlib import Path

from trader_research.foundation.artifacts import InMemoryResearchArtifactStore
from trader_research.governance.artifacts import (
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    METHODOLOGY_CANDIDATE,
    METHODOLOGY_CANDIDATE_VALIDATION_REPORT,
    METHODOLOGY_EVIDENCE_PACKET,
    METHODOLOGY_FIELD_EXTRACTION_REPORT,
)
from trader_research.knowledge.domain import (
    EvidenceBackedField,
    EvidenceReference,
    MethodologyCandidate,
)
from trader_research.knowledge.embeddings import DeterministicEmbeddingProvider
from trader_research.knowledge.evidence_assembly import assemble_methodology_evidence
from trader_research.knowledge.index import index_chunks
from trader_research.knowledge.methodology_candidates import (
    discover_methodology_candidates,
)
from trader_research.knowledge.methodology_extraction import extract_methodology_fields
from trader_research.knowledge.methodology_validation import (
    validate_methodology_candidate,
)
from tests.trader_research.knowledge.methodology_candidate_fixtures import (
    _store_with_adjacent_indicator_units,
    _store_with_pairs_chunks,
)


def test_validation_blocks_candidate_extracted_without_evidence_packet(
    tmp_path: Path,
) -> None:
    """Validation rejects extracted candidates that bypass evidence-packet assembly."""
    artifact_root, store, source, _ = _store_with_pairs_chunks(tmp_path)
    artifact_store = InMemoryResearchArtifactStore()
    discovered = discover_methodology_candidates(
        artifact_root=artifact_root,
        source_ids=(source.source_id,),
        method_families=("statistical_arbitrage",),
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    candidate_id = discovered.data["methodology_candidates"][0][
        "methodology_candidate_id"
    ]

    extracted = extract_methodology_fields(
        artifact_root=artifact_root,
        methodology_candidate_id=candidate_id,
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    extraction_report = extracted.data["methodology_field_extraction_report"]
    validated = validate_methodology_candidate(
        artifact_root=artifact_root,
        extraction_report_id=extraction_report["extraction_id"],
        knowledge_store=store,
        artifact_store=artifact_store,
    )

    assert extracted.ok is True
    candidate = extracted.data["methodology_candidate"]
    assert candidate["status"] == "extracted"
    assert candidate["extension_fields"]["statistical_arbitrage"]["cointegration_test"][
        "evidence_refs"
    ]
    assert "options_derivatives" not in candidate["extension_fields"]
    assert extraction_report["artifact_type"] == METHODOLOGY_FIELD_EXTRACTION_REPORT
    assert validated.ok is False
    report = validated.data["methodology_candidate_validation_report"]
    assert report["status"] == "blocked"
    assert "methodology_evidence_packet lineage" in "\n".join(report["blockers"])
    assert (
        artifact_store.load_artifact_record(
            METHODOLOGY_CANDIDATE_VALIDATION_REPORT,
            report["validation_id"],
        ).status
        == "blocked"
    )


def test_packet_grounded_extraction_and_validation_report_readiness(
    tmp_path: Path,
) -> None:
    """Packet-grounded extraction yields a passed report with explicit readiness evidence."""
    artifact_root, store, source, _ = _store_with_pairs_chunks(tmp_path)
    artifact_store = InMemoryResearchArtifactStore()
    discovered = discover_methodology_candidates(
        artifact_root=artifact_root,
        source_ids=(source.source_id,),
        method_families=("statistical_arbitrage",),
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    assembled = assemble_methodology_evidence(
        artifact_root=artifact_root,
        methodology_candidate_id=discovered.data["methodology_candidates"][0][
            "methodology_candidate_id"
        ],
        readiness_goal="signal",
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    packet_id = assembled.data["methodology_evidence_packet"]["evidence_packet_id"]

    extracted = extract_methodology_fields(
        artifact_root=artifact_root,
        evidence_packet_id=packet_id,
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    validated = validate_methodology_candidate(
        artifact_root=artifact_root,
        extraction_report_id=extracted.data["methodology_field_extraction_report"][
            "extraction_id"
        ],
        knowledge_store=store,
        artifact_store=artifact_store,
    )

    assert extracted.ok is True
    candidate = extracted.data["methodology_candidate"]
    assert candidate["lineage"]["evidence_packet_id"] == packet_id
    spread = candidate["extension_fields"]["statistical_arbitrage"]["spread_definition"]
    assert spread["quality"] == "role_evidence:spread_definition"
    assert "source-backed spread definition evidence" not in spread["value"]
    assert validated.ok is True
    readiness = validated.data["methodology_candidate_validation_report"][
        "readiness_summary"
    ]
    assert readiness["signal"]["status"] == "passed"
    assert readiness["strategy_template"]["status"] == "blocked"


def test_validation_blocks_stale_packet_evidence_unit_hashes(tmp_path: Path) -> None:
    """Validation rejects candidates when cited evidence-unit content has changed."""
    artifact_root, store, source, _ = _store_with_pairs_chunks(tmp_path)
    artifact_store = InMemoryResearchArtifactStore()
    discovered = discover_methodology_candidates(
        artifact_root=artifact_root,
        source_ids=(source.source_id,),
        method_families=("statistical_arbitrage",),
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    assembled = assemble_methodology_evidence(
        artifact_root=artifact_root,
        methodology_candidate_id=discovered.data["methodology_candidates"][0][
            "methodology_candidate_id"
        ],
        readiness_goal="signal",
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    packet = assembled.data["methodology_evidence_packet"]
    extracted = extract_methodology_fields(
        artifact_root=artifact_root,
        evidence_packet_id=packet["evidence_packet_id"],
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    tampered_roles = []
    tampered = False
    for role in packet["role_evidence"]:
        role_copy = dict(role)
        chunks_copy = []
        for chunk_ref in role.get("chunks", ()):
            ref_copy = dict(chunk_ref)
            if not tampered:
                ref_copy["text_hash"] = "stale_hash"
                tampered = True
            chunks_copy.append(ref_copy)
        role_copy["chunks"] = chunks_copy
        tampered_roles.append(role_copy)
    artifact_store.save_artifact(
        domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[METHODOLOGY_EVIDENCE_PACKET],
        producer_tool="test_methodology_fixture",
        artifact_type=METHODOLOGY_EVIDENCE_PACKET,
        artifact_id=packet["evidence_packet_id"],
        payload={**packet, "role_evidence": tampered_roles},
        status=packet["status"],
    )

    validated = validate_methodology_candidate(
        artifact_root=artifact_root,
        extraction_report_id=extracted.data["methodology_field_extraction_report"][
            "extraction_id"
        ],
        knowledge_store=store,
        artifact_store=artifact_store,
    )

    assert validated.ok is False
    blockers = "\n".join(
        validated.data["methodology_candidate_validation_report"]["blockers"]
    )
    assert "stale text_hash" in blockers


def test_validation_blocks_fields_sourced_from_rejected_competing_method(
    tmp_path: Path,
) -> None:
    """Validation rejects fields whose claims belong to a competing method."""
    artifact_root, store, source, chunks = _store_with_adjacent_indicator_units(
        tmp_path
    )
    artifact_store = InMemoryResearchArtifactStore()
    index_chunks(
        store,
        store.load_chunks(source.source_id),
        provider=DeterministicEmbeddingProvider(),
    )
    discovered = discover_methodology_candidates(
        artifact_root=artifact_root,
        query="exponentially weighted average EWA",
        source_ids=(source.source_id,),
        method_families=("technical_indicators",),
        neighbor_radius=1,
        max_candidates=10,
        knowledge_store=store,
        artifact_store=artifact_store,
        embedding_provider=DeterministicEmbeddingProvider(),
    )
    ewa = next(
        item
        for item in discovered.data["methodology_candidates"]
        if item["title"] == "Exponentially Weighted Average"
    )
    ewa_chunk = next(
        chunk
        for chunk in chunks
        if "Exponentially Weighted Average" in chunk.detected_labels
    )
    bollinger_chunk = next(
        chunk for chunk in chunks if "Bollinger Bands" in chunk.detected_labels
    )
    assembled = assemble_methodology_evidence(
        artifact_root=artifact_root,
        methodology_candidate_id=ewa["methodology_candidate_id"],
        readiness_goal="signal",
        neighbor_radius=1,
        max_chunks_per_role=10,
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    packet = assembled.data["methodology_evidence_packet"]
    ewa_ref = EvidenceReference(
        source_id=source.source_id,
        chunk_id=ewa_chunk.chunk_id,
        locator=ewa_chunk.locator,
        claim="role evidence supports formula algorithm; evidence_role=formula_algorithm",
    )
    bollinger_ref = EvidenceReference(
        source_id=source.source_id,
        chunk_id=bollinger_chunk.chunk_id,
        locator=bollinger_chunk.locator,
        claim="role evidence supports signal logic; evidence_role=signal_logic",
    )
    candidate = MethodologyCandidate(
        methodology_candidate_id="methodology_candidate_contaminated_ewa",
        title="Exponentially Weighted Average",
        families=("technical_indicators",),
        status="extracted",
        source_ids=(source.source_id,),
        chunk_ids=(ewa_chunk.chunk_id, bollinger_chunk.chunk_id),
        method_identity=ewa["method_identity"],
        core_fields={
            "identity": {
                "method_name": EvidenceBackedField(
                    value="Exponentially Weighted Average", evidence_refs=(ewa_ref,)
                ),
            },
            "data_requirements": {
                "required_inputs": EvidenceBackedField(
                    value=("ordered price series",), evidence_refs=(ewa_ref,)
                ),
            },
            "signal_decision_logic": {
                "signal_definition": EvidenceBackedField(
                    value="Bollinger band crossing signal",
                    evidence_refs=(bollinger_ref,),
                    quality="role_evidence:signal_logic",
                ),
            },
        },
        extension_fields={
            "technical_indicators": {
                "indicator_formula": EvidenceBackedField(
                    value="EWA weighted moving average formula",
                    evidence_refs=(ewa_ref,),
                    quality="role_evidence:formula_algorithm",
                )
            }
        },
        lineage={
            "evidence_packet_id": packet["evidence_packet_id"],
            "readiness_goal": "signal",
        },
    )

    validated = validate_methodology_candidate(
        artifact_root=artifact_root,
        methodology_candidate=candidate.to_dict(),
        knowledge_store=store,
        artifact_store=artifact_store,
    )

    assert validated.ok is False
    blockers = "\n".join(
        validated.data["methodology_candidate_validation_report"]["blockers"]
    )
    assert "must include claim_span" in blockers
    assert "must cite a target-bound claim span" in blockers


def test_extraction_rejects_invalid_refs_and_blocks_missing_chunks(
    tmp_path: Path,
) -> None:
    """Extraction rejects wrong artifact types and reports unavailable evidence units."""
    artifact_root, store, source, _ = _store_with_pairs_chunks(tmp_path)
    artifact_store = InMemoryResearchArtifactStore()
    bad_type = extract_methodology_fields(
        artifact_root=artifact_root,
        methodology_candidate={
            "artifact_type": "method_card",
            "methodology_candidate_id": "bad",
        },
        knowledge_store=store,
        artifact_store=artifact_store,
    )
    missing_chunk_candidate = MethodologyCandidate(
        methodology_candidate_id="methodology_candidate_missing_chunk",
        title="Missing chunk",
        families=("statistical_arbitrage",),
        source_ids=(source.source_id,),
        chunk_ids=("missing_chunk",),
    )
    artifact_store.save_artifact(
        domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[METHODOLOGY_CANDIDATE],
        producer_tool="test_methodology_fixture",
        artifact_type=METHODOLOGY_CANDIDATE,
        artifact_id=missing_chunk_candidate.methodology_candidate_id,
        payload=missing_chunk_candidate.to_dict(),
        status=missing_chunk_candidate.status,
    )
    missing = extract_methodology_fields(
        artifact_root=artifact_root,
        methodology_candidate_id=missing_chunk_candidate.methodology_candidate_id,
        knowledge_store=store,
        artifact_store=artifact_store,
    )

    assert bad_type.ok is False
    assert missing.ok is False
    assert missing.data["methodology_field_extraction_report"]["status"] == "blocked"


def test_validation_blocks_bad_evidence_and_family_minimum_failures(
    tmp_path: Path,
) -> None:
    """Validation reports locator, quotation, source-type, and family-coverage failures."""
    artifact_root, store, source, chunks = _store_with_pairs_chunks(
        tmp_path, source_type="internal_note"
    )
    artifact_store = InMemoryResearchArtifactStore()
    bad_locator_ref = EvidenceReference(
        source_id=source.source_id,
        chunk_id=chunks[1].chunk_id,
        locator={"heading": "Wrong Heading"},
        claim="bad locator",
    )
    candidate = MethodologyCandidate(
        methodology_candidate_id="methodology_candidate_invalid",
        title="Invalid textbook-derived pairs method",
        families=("statistical_arbitrage",),
        source_ids=(source.source_id,),
        chunk_ids=(chunks[1].chunk_id,),
        core_fields={
            "identity": {
                "method_name": EvidenceBackedField(
                    value="Invalid pairs method", evidence_refs=(bad_locator_ref,)
                ),
            },
            "data_requirements": {
                "required_inputs": EvidenceBackedField(
                    value=("price series",), evidence_refs=(bad_locator_ref,)
                ),
            },
        },
        extension_fields={
            "statistical_arbitrage": {
                "spread_definition": EvidenceBackedField(
                    value="x " * 100,
                    evidence_refs=(bad_locator_ref,),
                )
            }
        },
        lineage={"discovery": {"source_types": ["method_textbook"]}},
    )

    result = validate_methodology_candidate(
        artifact_root=artifact_root,
        methodology_candidate=candidate.to_dict(),
        knowledge_store=store,
        artifact_store=artifact_store,
    )

    assert result.ok is False
    report = result.data["methodology_candidate_validation_report"]
    blockers = "\n".join(report["blockers"])
    assert "locator mismatch" in blockers
    assert "statistical_arbitrage requires" in blockers
    assert "excessive direct quotation" in blockers
    assert "internal_note" in blockers
