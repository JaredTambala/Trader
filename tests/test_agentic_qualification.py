"""Contract tests for frozen first-slice agentic qualification evidence."""

from __future__ import annotations

from dataclasses import replace
import hashlib
from typing import Any, Mapping

import pytest

from tests.support.agentic_qualification import (
    AgenticScenarioResult,
    agentic_evaluation_digest,
    build_agentic_identity_manifest,
    evaluate_agentic_campaign,
    load_agentic_evaluation_contract,
)
from trader_agents.profiles import (
    DEVELOPMENT_MODEL_PROFILE_ID,
    OLLAMA_QWEN35_9B_DIGEST,
)


def test_agentic_identity_manifest_pins_model_program_tools_fixture_and_image() -> None:
    """Build one credential-free immutable qualification identity."""
    manifest = build_agentic_identity_manifest(
        {
            "TRADER_AGENTS_MODEL_PROFILE_ID": DEVELOPMENT_MODEL_PROFILE_ID,
            "TRADER_MCP_CODING_CONTAINER_IMAGE": (
                "ghcr.io/trader/agent-sandbox@sha256:" + "c" * 64
            ),
            "TRADER_AGENTS_MLFLOW_TRACKING_URI": (
                "postgresql://trace:supersecret@localhost/traces"
            ),
            "TRADER_AGENTS_MLFLOW_EXPERIMENT": "agentic-freeze",
        }
    )

    profiles = manifest["runtime"]["model_profiles"]["profiles"]
    programs = manifest["runtime"]["agent_programs"]["programs"]
    assert manifest["selected_model_profile_id"] == DEVELOPMENT_MODEL_PROFILE_ID
    assert profiles == [
        {
            "profile_id": DEVELOPMENT_MODEL_PROFILE_ID,
            "provider": "ollama",
            "model": "qwen3.5:9b",
            "model_revision": OLLAMA_QWEN35_9B_DIGEST,
            "base_url": "http://127.0.0.1:11434",
            "temperature": 0.0,
            "max_output_tokens": 900,
            "timeout_seconds": 120.0,
            "thinking": False,
        }
    ]
    assert {item["program_id"] for item in programs} == {
        "research-coordinator-v4",
        "data-research-v4",
        "strategy-engineering-v4",
    }
    assert manifest["evaluation_dataset_digest"] == agentic_evaluation_digest()
    assert set(manifest["evaluation_component_digests"]) == {
        "charter_sha256",
        "session_inputs_sha256",
    }
    assert manifest["sandbox_image"].endswith("c" * 64)
    assert manifest["trace"] == {
        "enabled": True,
        "experiment": "agentic-freeze",
    }
    assert "supersecret" not in str(manifest)
    assert len(manifest["identity_digest"]) == 64


def test_complete_campaign_passes_only_with_every_repetition_and_obligation() -> None:
    """Accept all 12 scenarios only after all 36 bounded results pass."""
    results = _complete_results()

    verdict = evaluate_agentic_campaign(results)

    assert verdict["status"] == "passed"
    assert verdict["scenario_count"] == 12
    assert verdict["repetitions_per_scenario"] == 3
    assert verdict["result_count"] == 36
    assert len(verdict["trace_ids"]) == 36
    assert verdict["blockers"] == []


def test_campaign_fails_closed_for_missing_duplicate_or_unsafe_result() -> None:
    """Reject incomplete campaigns and deterministic safety violations."""
    results = list(_complete_results())
    omitted = results.pop()
    duplicate = results[0]
    unsafe = replace(
        results[1],
        forbidden_tool_calls=1,
        deterministic_invariants={
            **results[1].deterministic_invariants,
            "no_forbidden_tool_dispatch": False,
        },
    )
    results[1] = unsafe
    results.append(duplicate)

    verdict = evaluate_agentic_campaign(results)

    assert verdict["status"] == "blocked"
    assert verdict["totals"]["forbidden_tool_calls"] == 1
    assert any("duplicate result" in item for item in verdict["blockers"])
    assert any(omitted.scenario_id in item for item in verdict["blockers"])
    assert any(
        "failed deterministic invariants" in item for item in verdict["blockers"]
    )


def test_persisted_result_contract_rejects_unknown_or_missing_fields() -> None:
    """Do not silently accept raw or future fields in canonical evidence."""
    result = _complete_results()[0]
    payload = result.to_dict()
    payload["raw_prompt"] = "do not persist me"

    with pytest.raises(ValueError, match="closed contract"):
        AgenticScenarioResult.from_dict(payload)

    payload = result.to_dict()
    del payload["trace_ids"]
    with pytest.raises(ValueError, match="closed contract"):
        AgenticScenarioResult.from_dict(payload)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("model_calls", True, "must be an integer"),
        ("duration_seconds", "1.0", "must be a number"),
        ("schema_valid", 1, "must be a boolean"),
        ("scenario_id", 123, "must be a string"),
        ("trace_ids", [], "at least one lifecycle trace"),
        ("trace_ids", ["tr-not-a-real-id"], "MLflow trace identities"),
    ],
)
def test_persisted_result_contract_rejects_permissive_coercion(
    field: str,
    value: object,
    message: str,
) -> None:
    """Persisted evidence must retain exact public JSON types and trace IDs."""
    payload = _complete_results()[0].to_dict()
    payload[field] = value

    with pytest.raises(ValueError, match=message):
        AgenticScenarioResult.from_dict(payload)


def test_identity_manifest_requires_trace_and_digest_pinned_sandbox() -> None:
    """Fail before a campaign can use mutable images or absent traces."""
    base = {
        "TRADER_AGENTS_MODEL_PROFILE_ID": DEVELOPMENT_MODEL_PROFILE_ID,
        "TRADER_AGENTS_MLFLOW_TRACKING_URI": "sqlite:///traces.db",
    }
    with pytest.raises(ValueError, match="repository@sha256"):
        build_agentic_identity_manifest(
            {
                **base,
                "TRADER_MCP_CODING_CONTAINER_IMAGE": "sandbox:latest",
            }
        )
    with pytest.raises(ValueError, match="MLFLOW_TRACKING_URI"):
        build_agentic_identity_manifest(
            {"TRADER_MCP_CODING_CONTAINER_IMAGE": ("sandbox@sha256:" + "d" * 64)}
        )


def _complete_results() -> tuple[AgenticScenarioResult, ...]:
    """Build one complete passing campaign from the frozen fixture."""
    contract = load_agentic_evaluation_contract()
    repetitions = int(
        contract["provisional_promotion_thresholds"]["repetitions_per_scenario"]
    )
    results = []
    for scenario in contract["scenarios"]:
        for repetition in range(1, repetitions + 1):
            results.append(_result(scenario, repetition, contract))
    return tuple(results)


def _result(
    scenario: Mapping[str, Any],
    repetition: int,
    contract: Mapping[str, Any],
) -> AgenticScenarioResult:
    """Build one internally consistent passing result."""
    scenario_id = str(scenario["scenario_id"])
    digest = hashlib.sha256(f"{scenario_id}:{repetition}".encode()).hexdigest()
    roles = tuple(str(item) for item in scenario["required_delegations"])
    evidence_types = tuple(str(item) for item in scenario["required_evidence"])
    return AgenticScenarioResult(
        scenario_id=scenario_id,
        repetition=repetition,
        status="passed",
        terminal_actions=(str(scenario["expected_terminal_actions"][0]),),
        delegated_roles=roles,
        evidence_types=evidence_types,
        evidence_refs=tuple(
            f"research://postgres/{item}/{digest}" for item in evidence_types
        ),
        mutations=tuple(str(item) for item in scenario["permitted_mutations"]),
        trajectory_assertions={
            str(item): True for item in scenario["trajectory_assertions"]
        },
        deterministic_invariants={
            str(item): True for item in contract["required_deterministic_invariants"]
        },
        schema_valid=True,
        grounded_decision=True,
        required_role_coverage=1.0,
        forbidden_tool_calls=0,
        unapproved_mutations=0,
        lost_canonical_receipts=0,
        replayed_accepted_mutations=0,
        model_calls=2,
        tool_calls=2,
        total_tokens=200,
        duration_seconds=1.0,
        revisions=0,
        peak_concurrency=1,
        trace_ids=(f"tr-{digest[:32]}",),
    )
