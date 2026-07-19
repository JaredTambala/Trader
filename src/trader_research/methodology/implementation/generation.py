"""Quarantined Python generation workflow for method implementations."""

from __future__ import annotations

from trader_research.foundation import ApplicationResult, error_result, success_result
from trader_research.foundation.artifacts import ArtifactReference

from pathlib import Path
from typing import Any, Mapping, Sequence

from trader_research.knowledge.approved_cards import ApprovedMethodCardReader
from trader_research.methodology.implementation.fixtures import run_indicator_fixtures, run_signal_fixtures
from trader_research.methodology.implementation.io import local_mutating_error, quarantine_source_path
from trader_research.methodology.implementation.manifest import (
    DEFAULT_ALLOWED_IMPORTS,
    INDICATOR_RUNTIME_CONTRACT,
    MATH_GENERATE_PYTHON_METHOD,
    SIGNAL_RUNTIME_CONTRACT,
    sequence,
)
from trader_research.methodology.implementation.registration import _static_safety_blockers, register_method_implementation


def generate_python_method_from_payload(
    *,
    artifact_root: str | Path,
    method_id: str,
    method_card_ids: Sequence[str],
    method_contract: Mapping[str, Any],
    llm_payload: Mapping[str, Any],
    fixtures: Sequence[Mapping[str, Any]] | None = None,
    approved_card_reader: ApprovedMethodCardReader | None = None,
) -> ApplicationResult:
    """Quarantine, statically check, register, and fixture-validate generated code.

    The workflow requires `source_code` and `class_name`, writes the source under a
    content-addressed quarantine path, blocks unsafe imports or dynamic execution,
    registers the implementation manifest, then runs indicator or signal fixtures
    based on the registered runtime contract. Each stage returns a structured
    local-mutating result so generated code never bypasses registration evidence
    or deterministic validation.
    """
    source_code = str(llm_payload.get("source_code") or "")
    class_name = str(llm_payload.get("class_name") or "").strip()
    if not source_code.strip():
        return local_mutating_error(MATH_GENERATE_PYTHON_METHOD, "generated_source_required", "LLM payload did not include source_code")
    if not class_name:
        return local_mutating_error(MATH_GENERATE_PYTHON_METHOD, "generated_class_required", "LLM payload did not include class_name")

    source_path = quarantine_source_path(artifact_root, method_id, source_code)
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(source_code, encoding="utf-8")
    blockers = _static_safety_blockers(source_path, dependency_allowlist=DEFAULT_ALLOWED_IMPORTS)
    if blockers:
        return error_result(
            command=MATH_GENERATE_PYTHON_METHOD,
            code="generated_method_safety_failed",
            message="generated Python method failed static safety checks",
            data={
                "generated_source_path": str(source_path),
                "blockers": blockers,
                "status": "blocked",
            },
        )

    register_result = register_method_implementation(
        artifact_root=artifact_root,
        method_id=method_id,
        method_card_ids=method_card_ids,
        method_contract=method_contract,
        entrypoint=f"{source_path}:{class_name}",
        source_path=source_path,
        class_name=class_name,
        implementation_kind="generated",
        approved_card_reader=approved_card_reader,
    )
    if not register_result.ok:
        return error_result(
            command=MATH_GENERATE_PYTHON_METHOD,
            code="generated_method_registration_failed",
            message="generated Python method registration failed",
            data={
                "generated_source_path": str(source_path),
                "registration": register_result.to_dict(),
                "status": "blocked",
            },
        )
    registered_manifest = register_result.data["method_implementation_manifest"]
    fixture_runner = (
        run_signal_fixtures
        if registered_manifest.get("runtime_contract") == SIGNAL_RUNTIME_CONTRACT
        else run_indicator_fixtures
    )
    fixture_result = fixture_runner(
        artifact_root=artifact_root,
        implementation_manifest=registered_manifest,
        fixtures=fixtures,
        approved_card_reader=approved_card_reader,
    )
    data = {
        "generated_source_path": str(source_path),
        "registration": register_result.data,
        "fixture_validation": fixture_result.data,
        "status": "validated" if fixture_result.ok else "blocked",
    }
    artifacts = {
        "generated_source": ArtifactReference(
            artifact_type="generated_python_method",
            path=source_path,
            metadata={"method_id": method_id, "status": data["status"]},
        ).to_dict()
    }
    if not fixture_result.ok:
        return error_result(
            command=MATH_GENERATE_PYTHON_METHOD,
            code="generated_method_fixture_validation_failed",
            message="generated Python method failed fixture validation",
            data=data,
        )
    return success_result(
        command=MATH_GENERATE_PYTHON_METHOD,
        data=data,
        artifacts=artifacts,
    )


def generation_messages(
    method_id: str,
    method_contract: Mapping[str, Any],
    method_card_ids: Sequence[str] | None = None,
) -> tuple[Mapping[str, str], ...]:
    """Build provider-neutral prompt messages for quarantined Python generation.

    The messages instruct an LLM bridge to return JSON only, subclass the requested
    Trader runtime contract, avoid side-effecting APIs, and include source-level
    documentation naming method cards, ordering, warmup, and no-lookahead behavior.
    Method-card IDs are gathered from explicit input and evidence references.
    """
    runtime_contract = str(method_contract.get("runtime_contract") or INDICATOR_RUNTIME_CONTRACT)
    runtime_name = "Signal" if runtime_contract == SIGNAL_RUNTIME_CONTRACT else "Indicator"
    resolved_method_card_ids = [str(method_card_id) for method_card_id in sequence(method_card_ids)]
    resolved_method_card_ids.extend(
        str(ref["method_card_id"])
        for ref in sequence(method_contract.get("knowledge_evidence_refs"))
        if isinstance(ref, Mapping) and ref.get("method_card_id")
    )
    resolved_method_card_ids = sorted(set(resolved_method_card_ids))
    return (
        {
            "role": "system",
            "content": (
                f"Return JSON only with source_code and class_name for one Python class that subclasses "
                f"{runtime_contract}. Do not use filesystem, network, subprocess, SQL, dynamic imports, "
                "eval, or exec. The source_code must start with a module docstring containing a Source reference "
                "section and an Implements section."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Create a quarantined Python {runtime_name} implementation for {method_id}: {dict(method_contract)}. "
                f"Approved method-card IDs: {resolved_method_card_ids}. The module docstring must name the registry "
                f"method, approved method-card IDs, generated class, Trader {runtime_name} runtime contract, exact implemented "
                "formula or algorithm, input ordering, warmup behavior, output ordering, and no-lookahead boundary."
            ),
        },
    )


def generation_response_schema() -> Mapping[str, Any]:
    """Return the JSON schema expected from the generation bridge response.

    The schema requires `class_name` and `source_code`, with optional implementation
    notes. The generation workflow validates this transport shape before writing
    quarantined source or running static safety checks.
    """
    return {
        "type": "object",
        "required": ["class_name", "source_code"],
        "properties": {
            "class_name": {"type": "string"},
            "source_code": {"type": "string"},
            "implementation_notes": {"type": "string"},
        },
    }
