"""Search and compare maintained and admitted research implementations.

The catalogue is a deterministic discovery boundary over maintained template
metadata and canonical implementation/admission records. Search results are
bounded navigation evidence: only an exact implementation version with a passed
validation report is eligible for direct reuse.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import re
from typing import Any

from trader_research.foundation import (
    ApplicationResult,
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    error_result,
    load_artifact_ref,
    parse_research_artifact_uri,
    stable_research_id,
    success_result,
)
from trader_research.governance.artifacts import (
    IMPLEMENTATION_VALIDATION_REPORT,
    IMPLEMENTATION_VERSION,
)

from .domain import IMPLEMENTATION_KINDS, ImplementationVersion
from .templates import list_risk_manager_templates, list_strategy_templates


RESEARCH_SEARCH_IMPLEMENTATIONS = "research_search_implementations"
RESEARCH_GET_IMPLEMENTATION = "research_get_implementation"
RESEARCH_COMPARE_IMPLEMENTATION = "research_compare_implementation"

_SEARCHABLE_KINDS = frozenset({"strategy", "risk_manager"})
_TOKEN_PATTERN = re.compile(r"[a-z0-9_]+")


@dataclass(frozen=True)
class ImplementationSearchRequest:
    """Normalized request for bounded implementation-catalogue discovery.

    Attributes:
        query: Optional lexical description used to rank matching records.
        implementation_kinds: Eligible implementation kinds.
        capabilities: Required capability labels.
        runtime_contract: Optional exact Trader runtime contract.
        include_unadmitted: Whether audit-only unadmitted versions are visible.
        limit: Maximum number of returned catalogue rows.
    """

    query: str = ""
    implementation_kinds: tuple[str, ...] = ("strategy", "risk_manager")
    capabilities: tuple[str, ...] = ()
    runtime_contract: str | None = None
    include_unadmitted: bool = False
    limit: int = 20

    def __post_init__(self) -> None:
        """Validate and normalize the public search contract."""
        normalized_kinds = _normalized_strings(self.implementation_kinds)
        if not normalized_kinds:
            raise ValueError("implementation_kinds must not be empty")
        unsupported = set(normalized_kinds) - _SEARCHABLE_KINDS
        if unsupported:
            raise ValueError(
                "unsupported searchable implementation kinds: "
                + ", ".join(sorted(unsupported))
            )
        if not 1 <= int(self.limit) <= 50:
            raise ValueError("limit must be between 1 and 50")
        object.__setattr__(self, "query", str(self.query or "").strip())
        object.__setattr__(self, "implementation_kinds", normalized_kinds)
        object.__setattr__(self, "capabilities", _normalized_strings(self.capabilities))
        object.__setattr__(
            self,
            "runtime_contract",
            str(self.runtime_contract or "").strip() or None,
        )
        object.__setattr__(self, "limit", int(self.limit))

    def to_dict(self) -> dict[str, Any]:
        """Return the normalized JSON-native search identity."""
        return {
            "query": self.query,
            "implementation_kinds": list(self.implementation_kinds),
            "capabilities": list(self.capabilities),
            "runtime_contract": self.runtime_contract,
            "include_unadmitted": self.include_unadmitted,
            "limit": self.limit,
        }


@dataclass(frozen=True)
class ImplementationComparisonRequest:
    """Request a deterministic field comparison against one build contract.

    Attributes:
        implementation_ref: Exact implementation-version ID or canonical URI.
        build_contract: Normalized operator- or source-authorized build contract.
    """

    implementation_ref: str
    build_contract: Mapping[str, Any]

    def __post_init__(self) -> None:
        """Require an exact reference and a minimally typed build contract."""
        reference = str(self.implementation_ref or "").strip()
        if not reference:
            raise ValueError("implementation_ref is required")
        kind = str(self.build_contract.get("implementation_kind") or "").strip()
        if kind not in IMPLEMENTATION_KINDS:
            raise ValueError("build_contract.implementation_kind is unsupported")
        object.__setattr__(self, "implementation_ref", reference)
        object.__setattr__(self, "build_contract", dict(self.build_contract))


def search_implementations(
    artifact_store: ResearchArtifactStore,
    request: ImplementationSearchRequest,
) -> ApplicationResult:
    """Search maintained metadata and canonical implementation versions.

    The operation performs no persistence. Passed validation reports determine
    direct-reuse eligibility; search score and maintained status never confer
    admission. Complete source is excluded from result rows.

    Args:
        artifact_store: Canonical implementation and validation reader.
        request: Normalized bounded search request.

    Returns:
        Ranked catalogue rows and a reproducible catalogue/search identity.
    """
    try:
        admitted = _passed_validation_by_implementation(artifact_store)
        rows = [
            *_maintained_rows(request),
            *_canonical_rows(artifact_store, request, admitted),
        ]
    except ResearchArtifactStoreError as exc:
        return error_result(
            command=RESEARCH_SEARCH_IMPLEMENTATIONS,
            code="implementation_catalog_unavailable",
            message=str(exc),
        )
    ranked = sorted(
        (row for row in rows if _row_matches(row, request)),
        key=lambda row: (-_search_score(row, request), str(row["catalogue_ref"])),
    )[: request.limit]
    catalogue_id = stable_research_id(
        "implementation_catalog_search",
        {
            "request": request.to_dict(),
            "results": [
                {
                    "catalogue_ref": row["catalogue_ref"],
                    "source_hash": row.get("source_hash"),
                    "validation_ref": row.get("validation_ref"),
                }
                for row in ranked
            ],
        },
    )
    return success_result(
        command=RESEARCH_SEARCH_IMPLEMENTATIONS,
        data={
            "catalogue_id": catalogue_id,
            "request": request.to_dict(),
            "result_count": len(ranked),
            "implementations": ranked,
        },
    )


def get_implementation(
    artifact_store: ResearchArtifactStore,
    implementation_ref: str,
    *,
    include_source: bool = False,
) -> ApplicationResult:
    """Resolve one exact canonical implementation and its admission evidence.

    Args:
        artifact_store: Canonical implementation and validation reader.
        implementation_ref: Exact implementation-version ID or URI.
        include_source: Whether bounded source is included for an authorized
            coding context.

    Returns:
        Exact implementation metadata, trust tier, eligibility, and matching
        passed validation reference when present.
    """
    try:
        payload = load_artifact_ref(
            artifact_store,
            IMPLEMENTATION_VERSION,
            implementation_ref,
        )
        implementation = ImplementationVersion.from_dict(payload)
        admitted = _passed_validation_by_implementation(artifact_store)
    except (ValueError, ResearchArtifactStoreError) as exc:
        return error_result(
            command=RESEARCH_GET_IMPLEMENTATION,
            code="implementation_resolution_failed",
            message=str(exc),
        )
    row = _canonical_catalogue_row(implementation, admitted.get(implementation.implementation_version_id))
    if include_source:
        row["source_code"] = implementation.source_code
    artifacts = {
        "implementation_version": _implementation_reference(
            artifact_store,
            implementation,
        )
    }
    validation_uri = row.get("validation_ref")
    if validation_uri:
        validation_type, validation_id = parse_research_artifact_uri(
            str(validation_uri)
        )
        validation_record = artifact_store.load_artifact_record(
            validation_type,
            validation_id,
        )
        artifacts["implementation_validation_report"] = (
            validation_record.reference().to_dict()
        )
    return success_result(
        command=RESEARCH_GET_IMPLEMENTATION,
        data={"implementation": row},
        artifacts=artifacts,
    )


def compare_implementation(
    artifact_store: ResearchArtifactStore,
    request: ImplementationComparisonRequest,
) -> ApplicationResult:
    """Compare one exact implementation with typed build-contract fields.

    The comparison is deterministic support for a Strategy Engineering model
    decision. It records matches, differences, and unknowns but never declares
    semantic equivalence or trading efficacy.

    Args:
        artifact_store: Canonical implementation and validation reader.
        request: Exact version and build contract to compare.

    Returns:
        Field-level comparison evidence and direct-reuse eligibility.
    """
    resolved = get_implementation(
        artifact_store,
        request.implementation_ref,
        include_source=False,
    )
    if not resolved.ok:
        return error_result(
            command=RESEARCH_COMPARE_IMPLEMENTATION,
            code=str(resolved.errors[0].get("code") or "implementation_resolution_failed"),
            message=str(resolved.errors[0].get("message") or "Implementation resolution failed."),
        )
    implementation = dict(resolved.data["implementation"])
    fields = _comparison_fields(request.build_contract, implementation)
    has_difference = any(field["status"] == "different" for field in fields)
    has_unknown = any(field["status"] == "unknown" for field in fields)
    direct_reuse_eligible = bool(
        implementation["direct_reuse_eligible"] and not has_difference and not has_unknown
    )
    comparison_id = stable_research_id(
        "implementation_compatibility",
        {
            "implementation_version_id": implementation["implementation_version_id"],
            "build_contract": dict(request.build_contract),
            "fields": fields,
        },
    )
    return success_result(
        command=RESEARCH_COMPARE_IMPLEMENTATION,
        data={
            "comparison_id": comparison_id,
            "implementation_version_id": implementation["implementation_version_id"],
            "validation_ref": implementation.get("validation_ref"),
            "fields": fields,
            "direct_reuse_eligible": direct_reuse_eligible,
            "decision_authority": "strategy_engineering_agent",
            "limitations": [
                "This deterministic comparison does not establish semantic equivalence or efficacy."
            ],
        },
        artifacts=resolved.artifacts,
    )


def _passed_validation_by_implementation(
    artifact_store: ResearchArtifactStore,
) -> dict[str, Mapping[str, Any]]:
    passed: dict[str, Mapping[str, Any]] = {}
    records = artifact_store.list_artifacts(artifact_type=IMPLEMENTATION_VALIDATION_REPORT)
    for record in sorted(records, key=lambda item: (item.updated_at, item.artifact_id)):
        payload = record.payload
        if (
            payload.get("status") == "passed"
            and payload.get("valid") is True
            and not payload.get("blockers")
        ):
            implementation_id = str(payload.get("implementation_version_id") or "")
            if implementation_id:
                passed[implementation_id] = {
                    "uri": record.uri,
                    "validation_id": record.artifact_id,
                    "source_hash": payload.get("source_hash"),
                }
    return passed


def _canonical_rows(
    artifact_store: ResearchArtifactStore,
    request: ImplementationSearchRequest,
    admitted: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in artifact_store.list_artifacts(artifact_type=IMPLEMENTATION_VERSION):
        try:
            implementation = ImplementationVersion.from_dict(record.payload)
        except ValueError:
            continue
        validation = admitted.get(implementation.implementation_version_id)
        if validation is None and not request.include_unadmitted:
            continue
        rows.append(_canonical_catalogue_row(implementation, validation))
    return rows


def _canonical_catalogue_row(
    implementation: ImplementationVersion,
    validation: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "catalogue_ref": f"implementation:{implementation.implementation_version_id}",
        "catalogue_tier": "admitted" if validation is not None else "unadmitted",
        "implementation_version_id": implementation.implementation_version_id,
        "implementation_uri": (
            f"research://postgres/{IMPLEMENTATION_VERSION}/"
            f"{implementation.implementation_version_id}"
        ),
        "implementation_kind": implementation.implementation_kind,
        "name": implementation.name,
        "version": implementation.version,
        "description": str(implementation.metadata.get("description") or ""),
        "runtime_contract": implementation.entrypoint.get("runtime_contract"),
        "factory_name": implementation.entrypoint.get("factory_name"),
        "class_name": implementation.entrypoint.get("class_name"),
        "parameter_schema": dict(implementation.parameter_schema),
        "capabilities": list(implementation.capabilities),
        "runtime_requirements": dict(implementation.runtime_requirements),
        "metadata": dict(implementation.metadata),
        "source_hash": implementation.source_hash,
        "validation_ref": validation.get("uri") if validation is not None else None,
        "trust_tier": "admitted" if validation is not None else "untrusted_reference",
        "direct_reuse_eligible": validation is not None,
    }


def _maintained_rows(request: ImplementationSearchRequest) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if "strategy" in request.implementation_kinds:
        result = list_strategy_templates()
        if result.ok:
            rows.extend(_maintained_catalogue_row(item) for item in result.data["templates"])
    if "risk_manager" in request.implementation_kinds:
        result = list_risk_manager_templates()
        if result.ok:
            rows.extend(_maintained_catalogue_row(item) for item in result.data["templates"])
    return rows


def _maintained_catalogue_row(template: Mapping[str, Any]) -> dict[str, Any]:
    template_id = str(template["template_id"])
    return {
        "catalogue_ref": f"maintained:{template_id}",
        "catalogue_tier": "maintained_metadata",
        "implementation_version_id": None,
        "implementation_uri": None,
        "implementation_kind": template["implementation_kind"],
        "name": template.get("display_name") or template_id,
        "version": None,
        "description": template.get("description") or "",
        "runtime_contract": template.get("runtime_contract"),
        "factory_name": None,
        "class_name": None,
        "parameter_schema": {
            str(item["name"]): dict(item) for item in template.get("parameters") or []
        },
        "capabilities": sorted(
            {
                *_tokenize(template.get("behavior")),
                *_tokenize(template.get("portfolio_mode")),
            }
        ),
        "runtime_requirements": _maintained_runtime_requirements(
            template.get("runtime_context")
        ),
        "metadata": {
            "maintained_entrypoint": template.get("maintained_entrypoint"),
            "portfolio_mode": template.get("portfolio_mode"),
            "behavior": dict(template.get("behavior") or {}),
        },
        "source_hash": None,
        "validation_ref": None,
        "trust_tier": "maintained_metadata",
        "direct_reuse_eligible": False,
    }


def _row_matches(row: Mapping[str, Any], request: ImplementationSearchRequest) -> bool:
    if row.get("implementation_kind") not in request.implementation_kinds:
        return False
    if request.runtime_contract and row.get("runtime_contract") != request.runtime_contract:
        return False
    row_capabilities = set(_normalized_strings(row.get("capabilities") or ()))
    if set(request.capabilities) - row_capabilities:
        return False
    if not request.query:
        return True
    return bool(_tokenize(request.query) & _tokenize(row))


def _search_score(row: Mapping[str, Any], request: ImplementationSearchRequest) -> int:
    score = 0
    if row.get("direct_reuse_eligible"):
        score += 100
    if row.get("catalogue_tier") == "maintained_metadata":
        score += 20
    score += 10 * len(set(request.capabilities) & set(row.get("capabilities") or ()))
    score += 5 * len(_tokenize(request.query) & _tokenize(row))
    return score


def _comparison_fields(
    build_contract: Mapping[str, Any],
    implementation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    requested_capabilities = set(
        _normalized_strings(build_contract.get("required_capabilities") or ())
    )
    available_capabilities = set(
        _normalized_strings(implementation.get("capabilities") or ())
    )
    checks = (
        (
            "implementation_kind",
            build_contract.get("implementation_kind"),
            implementation.get("implementation_kind"),
        ),
        (
            "runtime_contract",
            build_contract.get("runtime_contract"),
            implementation.get("runtime_contract"),
        ),
        (
            "portfolio_mode",
            build_contract.get("portfolio_mode"),
            _mapping(implementation.get("metadata")).get("portfolio_mode"),
        ),
        (
            "required_capabilities",
            sorted(requested_capabilities),
            sorted(available_capabilities),
        ),
    )
    fields: list[dict[str, Any]] = []
    for field_name, required, actual in checks:
        if required in (None, "", [], ()):
            status = "unknown"
        elif field_name == "required_capabilities":
            status = "match" if requested_capabilities <= available_capabilities else "different"
        else:
            status = "match" if required == actual else "different"
        fields.append(
            {
                "field": field_name,
                "required": required,
                "actual": actual,
                "status": status,
            }
        )
    requested_parameters = _mapping(build_contract.get("parameters"))
    available_parameters = _mapping(implementation.get("parameter_schema"))
    for parameter_name in sorted(requested_parameters):
        fields.append(
            {
                "field": f"parameters.{parameter_name}",
                "required": requested_parameters[parameter_name],
                "actual": available_parameters.get(parameter_name),
                "status": "match" if parameter_name in available_parameters else "different",
            }
        )
    return fields


def _implementation_reference(
    artifact_store: ResearchArtifactStore,
    implementation: ImplementationVersion,
) -> Mapping[str, Any]:
    record = artifact_store.load_artifact_record(
        IMPLEMENTATION_VERSION,
        implementation.implementation_version_id,
    )
    return record.reference().to_dict()


def _normalized_strings(values: Sequence[object]) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in normalized:
            normalized.append(text)
    return tuple(normalized)


def _tokenize(value: object) -> set[str]:
    return set(_TOKEN_PATTERN.findall(str(value).lower()))


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _maintained_runtime_requirements(value: object) -> dict[str, Any]:
    """Normalize maintained template context into a stable mapping."""
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return {"required_context": list(_normalized_strings(value))}
    return {}
